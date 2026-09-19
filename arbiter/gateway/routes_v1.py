"""
ARBITER OpenAI-Compatible Router Endpoint (Module 1)
Supports /v1/chat/completions (streaming SSE & non-streaming), X-Arbiter headers, and Consensus mode.
"""

import json
import time
import uuid
import logging
from typing import Optional, AsyncIterator
from fastapi import APIRouter, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from arbiter.models.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatMessage,
    UsageInfo,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    DeltaMessage
)
from arbiter.models.types import Strategy, TaskCategory
from arbiter.classifier import classifier
from arbiter.router.engine import router
from arbiter.providers import pool
from arbiter.evaluator.merge_engine import MergeEngine
from arbiter.storage.models import save_request, save_provider_call, save_trace
from arbiter.core.events import bus

logger = logging.getLogger(__name__)

v1_router = APIRouter(prefix="/v1", tags=["OpenAI Proxy"])


@v1_router.get("/models")
async def list_models():
    """
    OpenAI-compatible models catalog endpoint.
    """
    models_data = [
        {"id": "arbiter-auto", "object": "model", "owned_by": "arbiter"},
        {"id": "arbiter-fastest", "object": "model", "owned_by": "arbiter"},
        {"id": "arbiter-cheapest", "object": "model", "owned_by": "arbiter"},
        {"id": "arbiter-quality", "object": "model", "owned_by": "arbiter"},
        {"id": "arbiter-consensus", "object": "model", "owned_by": "arbiter"}
    ]
    for p in pool.providers.values():
        for m in p.models:
            models_data.append({"id": m, "object": "model", "owned_by": p.name})
    return {"object": "list", "data": models_data}


@v1_router.post("/chat/completions")
async def chat_completions(
    request: Request,
    req_body: ChatCompletionRequest,
    x_arbiter_strategy: Optional[str] = Header(None, alias="X-Arbiter-Strategy"),
    x_arbiter_budget: Optional[float] = Header(None, alias="X-Arbiter-Budget")
):
    request_id = f"req-{uuid.uuid4().hex[:12]}"
    start_time = time.monotonic()

    # 1. Resolve Strategy
    raw_strat = x_arbiter_strategy or (req_body.strategy.value if req_body.strategy else None)
    if not raw_strat and req_body.model and req_body.model.startswith("arbiter-"):
        raw_strat = req_body.model.replace("arbiter-", "")
    
    try:
        strategy = Strategy(raw_strat) if raw_strat else Strategy.AUTO
    except ValueError:
        strategy = Strategy.AUTO

    budget_limit = x_arbiter_budget if x_arbiter_budget is not None else req_body.budget_limit

    # 2. Fast Zero-LLM Classification with Fail-safe Fallback (< 5ms)
    try:
        class_res = classifier.classify_messages(req_body.messages)
        task_cat = class_res.category
    except Exception as e:
        logger.error(f"Classifier error (fallback to conversation): {e}")
        task_cat = TaskCategory.CONVERSATION
        class_res = None

    # 3. Route request via MAB and Constraint Solver
    decision = await router.route_request(
        messages=req_body.messages,
        category=task_cat,
        strategy=strategy,
        budget_limit=budget_limit
    )

    full_prompt_text = " ".join([m.content if isinstance(m.content, str) else "" for m in req_body.messages])
    input_tokens = max(10, len(full_prompt_text) // 4)

    # Broadcast routing decision to WebSocket dashboard
    bus.publish("request_routed", {
        "request_id": request_id,
        "category": task_cat.value,
        "strategy": strategy.value,
        "selected_provider": decision.selected_provider,
        "selected_model": decision.selected_model,
        "estimated_cost": decision.estimated_cost,
        "exploration": decision.exploration,
        "candidate_models": decision.candidate_models,
        "timestamp": time.time()
    })

    # Record initial request record in storage
    await save_request(
        request_id=request_id,
        task_category=task_cat.value,
        strategy=strategy.value,
        input_tokens=input_tokens,
        estimated_cost=decision.estimated_cost,
        budget_limit=budget_limit
    )

    # 4. Handle Consensus Mode
    if strategy == Strategy.CONSENSUS:
        return await _handle_consensus_mode(
            request_id=request_id,
            req_body=req_body,
            task_cat=task_cat,
            decision=decision,
            input_tokens=input_tokens,
            start_time=start_time,
            full_prompt_text=full_prompt_text
        )

    # 5. Handle Single Provider Route
    provider = pool.get_provider(decision.selected_provider)
    if not provider:
        provider, decision.selected_model = pool.get_provider_for_model(decision.selected_model)

    # 6. Streaming Mode
    if req_body.stream:
        return _handle_streaming_response(
            request_id=request_id,
            provider=provider,
            decision=decision,
            task_cat=task_cat,
            strategy=strategy,
            req_body=req_body,
            input_tokens=input_tokens,
            start_time=start_time,
            full_prompt_text=full_prompt_text
        )

    # 7. Non-Streaming Mode
    try:
        provider_resp = await provider.complete(
            messages=req_body.messages,
            model=decision.selected_model,
            stream=False,
            temperature=req_body.temperature or 0.7,
            max_tokens=req_body.max_tokens
        )
        latency_ms = int((time.monotonic() - start_time) * 1000)

        response_text = ""
        output_tokens = 0
        actual_cost = decision.estimated_cost
        if isinstance(provider_resp, ChatCompletionResponse):
            if provider_resp.choices:
                response_text = str(provider_resp.choices[0].message.content)
            output_tokens = provider_resp.usage.completion_tokens
            actual_cost = provider_resp.usage.estimated_cost

        # Zero-LLM Evaluation score
        quality_score, eval_details = MergeEngine.evaluate_response(full_prompt_text, response_text)

        # Update MAB with evaluation score
        await router.mab.record_evaluation_quality(
            provider=decision.selected_provider,
            model=decision.selected_model,
            category=task_cat,
            quality_score=quality_score
        )

        call_id = f"call-{uuid.uuid4().hex[:12]}"
        await save_provider_call(
            call_id=call_id,
            request_id=request_id,
            provider=decision.selected_provider,
            model=decision.selected_model,
            status="success",
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            actual_cost=actual_cost,
            quality_score=quality_score,
            was_selected=True
        )

        # Save trace for Replay & Debug
        await save_trace(
            trace_id=f"tr-{uuid.uuid4().hex[:12]}",
            request_id=request_id,
            prompt_text=full_prompt_text,
            response_text=response_text,
            trace_data={
                "decision": decision.model_dump(),
                "eval": eval_details,
                "latency_ms": latency_ms,
                "cost": actual_cost
            }
        )

        # Publish telemetry
        bus.publish("request_completed", {
            "request_id": request_id,
            "provider": decision.selected_provider,
            "model": decision.selected_model,
            "category": task_cat.value,
            "strategy": strategy.value,
            "latency_ms": latency_ms,
            "actual_cost": actual_cost,
            "quality_score": quality_score,
            "status": "success",
            "timestamp": time.time()
        })

        # Return standardized OpenAI response with Arbiter extensions
        if isinstance(provider_resp, ChatCompletionResponse):
            provider_resp.id = request_id
            provider_resp.arbiter_category = task_cat
            provider_resp.arbiter_strategy = strategy
            provider_resp.arbiter_quality_score = quality_score
            return provider_resp

        return provider_resp

    except Exception as e:
        latency_ms = int((time.monotonic() - start_time) * 1000)
        logger.error(f"Provider call failed: {e}")
        call_id = f"call-{uuid.uuid4().hex[:12]}"
        await save_provider_call(
            call_id=call_id,
            request_id=request_id,
            provider=decision.selected_provider,
            model=decision.selected_model,
            status="error",
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=0,
            actual_cost=0.0,
            quality_score=0.0,
            was_selected=False
        )
        raise HTTPException(status_code=502, detail=f"Provider call failed: {str(e)}")


async def _handle_consensus_mode(
    request_id: str,
    req_body: ChatCompletionRequest,
    task_cat: TaskCategory,
    decision,
    input_tokens: int,
    start_time: float,
    full_prompt_text: str
) -> ChatCompletionResponse:
    targets = []
    for model_name in decision.candidate_models[:3]:
        p, resolved_m = pool.get_provider_for_model(model_name)
        targets.append((p, resolved_m))

    candidates = await pool.multiplexer.execute_consensus(
        targets=targets,
        messages=req_body.messages,
        temperature=req_body.temperature or 0.7,
        max_tokens=req_body.max_tokens
    )

    if not candidates:
        raise HTTPException(status_code=502, detail="Consensus mode failed: all candidates timed out or errored.")

    merged_text, quality_score, selection_mode, candidates_meta = MergeEngine.merge_candidates(
        full_prompt_text, candidates
    )
    latency_ms = int((time.monotonic() - start_time) * 1000)

    total_cost = sum(c.usage.estimated_cost for c in candidates if c.usage)
    output_tokens = len(merged_text) // 4

    # Save provider calls
    for cand in candidates:
        call_id = f"call-{uuid.uuid4().hex[:12]}"
        was_chosen = (cand.model == candidates_meta[0]["model"])
        c_cost = cand.usage.estimated_cost if cand.usage else 0.0
        c_out = cand.usage.completion_tokens if cand.usage else 0
        await save_provider_call(
            call_id=call_id,
            request_id=request_id,
            provider=cand.provider,
            model=cand.model,
            status="success",
            latency_ms=cand.latency_ms,
            input_tokens=input_tokens,
            output_tokens=c_out,
            actual_cost=c_cost,
            quality_score=quality_score,
            was_selected=was_chosen
        )

    # Save trace
    await save_trace(
        trace_id=f"tr-{uuid.uuid4().hex[:12]}",
        request_id=request_id,
        prompt_text=full_prompt_text,
        response_text=merged_text,
        trace_data={
            "selection_mode": selection_mode,
            "candidates": candidates_meta,
            "total_cost": total_cost,
            "latency_ms": latency_ms
        }
    )

    bus.publish("request_completed", {
        "request_id": request_id,
        "provider": "consensus",
        "model": f"consensus({len(candidates)})",
        "category": task_cat.value,
        "strategy": Strategy.CONSENSUS.value,
        "latency_ms": latency_ms,
        "actual_cost": total_cost,
        "quality_score": quality_score,
        "status": "success",
        "timestamp": time.time()
    })

    return ChatCompletionResponse(
        id=request_id,
        model=f"arbiter-consensus-{selection_mode}",
        choices=[
            ChatCompletionResponseChoice(
                message=ChatMessage(role="assistant", content=merged_text)
            )
        ],
        usage=UsageInfo(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            estimated_cost=total_cost
        ),
        arbiter_category=task_cat,
        arbiter_strategy=Strategy.CONSENSUS,
        arbiter_quality_score=quality_score,
        arbiter_consensus_models=[c.model for c in candidates]
    )


def _handle_streaming_response(
    request_id: str,
    provider,
    decision,
    task_cat: TaskCategory,
    strategy: Strategy,
    req_body: ChatCompletionRequest,
    input_tokens: int,
    start_time: float,
    full_prompt_text: str
) -> EventSourceResponse:
    """
    Proxies streaming SSE chunks while rewriting chunk metadata dynamically.
    """
    async def event_generator() -> AsyncIterator[dict]:
        accumulated_text = []
        try:
            chunk_stream = await provider.complete(
                messages=req_body.messages,
                model=decision.selected_model,
                stream=True,
                temperature=req_body.temperature or 0.7,
                max_tokens=req_body.max_tokens
            )

            async for chunk in chunk_stream:
                if isinstance(chunk, ChatCompletionChunk):
                    # Rewrite chunk ID and model to Arbiter
                    chunk.id = request_id
                    if chunk.choices and chunk.choices[0].delta.content:
                        accumulated_text.append(chunk.choices[0].delta.content)
                    yield {"data": chunk.model_dump_json()}
                elif isinstance(chunk, str):
                    yield {"data": chunk}

            yield {"data": "[DONE]"}

            # Post-stream async persistence and quality evaluation
            complete_resp_text = "".join(accumulated_text)
            latency_ms = int((time.monotonic() - start_time) * 1000)
            output_tokens = len(complete_resp_text) // 4
            cost = decision.estimated_cost

            q_score, _ = MergeEngine.evaluate_response(full_prompt_text, complete_resp_text)
            call_id = f"call-{uuid.uuid4().hex[:12]}"
            await save_provider_call(
                call_id=call_id,
                request_id=request_id,
                provider=decision.selected_provider,
                model=decision.selected_model,
                status="success",
                latency_ms=latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                actual_cost=cost,
                quality_score=q_score,
                was_selected=True
            )

            bus.publish("request_completed", {
                "request_id": request_id,
                "provider": decision.selected_provider,
                "model": decision.selected_model,
                "category": task_cat.value,
                "strategy": strategy.value,
                "latency_ms": latency_ms,
                "actual_cost": cost,
                "quality_score": q_score,
                "status": "success",
                "timestamp": time.time()
            })

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield {"data": json.dumps({"error": str(e)})}
            yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())
