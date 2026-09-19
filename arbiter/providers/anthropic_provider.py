"""
ARBITER Anthropic Async Provider (Module 4)
Adapts Anthropic Messages API into OpenAI-compatible format.
"""

import json
import uuid
import httpx
from typing import List, AsyncIterator, Union, Optional
from arbiter.providers.base import BaseProvider, HealthStatus
from arbiter.providers.cost_calculator import CostCalculator
from arbiter.providers.circuit_breaker import CircuitBreaker
from arbiter.providers.rate_limiter import DualDimensionRateLimiter
from arbiter.models.schemas import (
    ChatMessage,
    ChatCompletionResponse,
    ChatCompletionResponseChoice,
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    DeltaMessage,
    UsageInfo
)


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.name = "anthropic"
        self.api_key = api_key
        self.models = ["claude-3-5-sonnet", "claude-3-5-haiku", "claude-3-opus"]
        self.base_url = "https://api.anthropic.com/v1"
        self.circuit_breaker = CircuitBreaker(self.name)
        self.rate_limiter = DualDimensionRateLimiter(rpm=200, tpm=160_000)

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        return CostCalculator.estimate_cost(input_tokens, output_tokens, model)

    async def health_check(self) -> HealthStatus:
        can_exec = await self.circuit_breaker.can_execute()
        return HealthStatus(
            provider=self.name,
            is_healthy=bool(self.api_key) and can_exec,
            circuit_state=self.circuit_breaker.state,
            rpm_used_ratio=self.rate_limiter.rpm_utilization,
            tpm_used_ratio=self.rate_limiter.tpm_utilization,
            message="Ready" if self.api_key else "Missing API key"
        )

    async def complete(
        self,
        messages: List[ChatMessage],
        model: str,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Union[ChatCompletionResponse, AsyncIterator[ChatCompletionChunk]]:
        if not self.api_key:
            raise RuntimeError("Anthropic API key is not configured.")
        if not await self.circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker is OPEN for {self.name}")

        url = f"{self.base_url}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # Convert OpenAI messages to Anthropic messages
        system_content = ""
        anthropic_msgs = []
        for m in messages:
            if m.role == "system":
                system_content += f"{m.content}\n"
            else:
                anthropic_msgs.append({
                    "role": "user" if m.role == "user" else "assistant",
                    "content": m.content if isinstance(m.content, str) else str(m.content)
                })

        payload = {
            "model": model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens or 1024,
            "temperature": temperature,
            "stream": stream
        }
        if system_content.strip():
            payload["system"] = system_content.strip()

        est_tokens = len(str(payload)) // 4
        if not await self.rate_limiter.acquire(est_tokens):
            await self.circuit_breaker.record_failure()
            raise RuntimeError("Rate limit exceeded for Anthropic (429)")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                if not stream:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 429:
                        await self.rate_limiter.record_429()
                        await self.circuit_breaker.record_failure()
                        raise RuntimeError(f"Anthropic 429: {resp.text}")
                    resp.raise_for_status()
                    await self.circuit_breaker.record_success()
                    data = resp.json()

                    # Convert to ChatCompletionResponse
                    content_text = ""
                    for block in data.get("content", []):
                        if block.get("type") == "text":
                            content_text += block.get("text", "")

                    usage_raw = data.get("usage", {})
                    input_toks = usage_raw.get("input_tokens", 0)
                    output_toks = usage_raw.get("output_tokens", 0)
                    cached_toks = usage_raw.get("cache_read_input_tokens", 0)
                    cost = CostCalculator.calculate_actual_cost(input_toks, output_toks, cached_toks, model)

                    return ChatCompletionResponse(
                        model=model,
                        choices=[
                            ChatCompletionResponseChoice(
                                message=ChatMessage(role="assistant", content=content_text)
                            )
                        ],
                        usage=UsageInfo(
                            prompt_tokens=input_toks,
                            completion_tokens=output_toks,
                            total_tokens=input_toks + output_toks,
                            cached_tokens=cached_toks,
                            estimated_cost=cost
                        )
                    )
                else:
                    return self._stream_anthropic(client, url, headers, payload)
            except Exception as e:
                await self.circuit_breaker.record_failure()
                raise e

    async def _stream_anthropic(self, client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> AsyncIterator[ChatCompletionChunk]:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                await self.circuit_breaker.record_failure()
                err = await resp.aread()
                raise RuntimeError(f"Anthropic streaming error {resp.status_code}: {err.decode('utf-8')}")

            await self.circuit_breaker.record_success()
            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "content_block_delta":
                            delta_text = event.get("delta", {}).get("text", "")
                            yield ChatCompletionChunk(
                                id=chunk_id,
                                model=payload["model"],
                                choices=[
                                    ChatCompletionChunkChoice(
                                        index=0,
                                        delta=DeltaMessage(role="assistant", content=delta_text)
                                    )
                                ]
                            )
                        elif event.get("type") == "message_stop":
                            yield ChatCompletionChunk(
                                id=chunk_id,
                                model=payload["model"],
                                choices=[
                                    ChatCompletionChunkChoice(
                                        index=0,
                                        delta=DeltaMessage(),
                                        finish_reason="stop"
                                    )
                                ]
                            )
                    except Exception:
                        continue
