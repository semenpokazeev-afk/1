"""
ARBITER Google Gemini Async Provider (Module 4)
Connects to Google Gemini API (v1beta) and formats into OpenAI schemas.
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


class GeminiProvider(BaseProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.name = "gemini"
        self.api_key = api_key
        self.models = ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"]
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models"
        self.circuit_breaker = CircuitBreaker(self.name)
        self.rate_limiter = DualDimensionRateLimiter(rpm=600, tpm=500_000)

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
            raise RuntimeError("Gemini API key is not configured.")
        if not await self.circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker is OPEN for {self.name}")

        endpoint = ":streamGenerateContent?alt=sse" if stream else ":generateContent"
        url = f"{self.base_url}/{model}{endpoint}&key={self.api_key}" if "?" in endpoint else f"{self.base_url}/{model}{endpoint}?key={self.api_key}"

        # Convert messages to Gemini contents format
        contents = []
        for m in messages:
            role = "user" if m.role == "user" else "model"
            text = m.content if isinstance(m.content, str) else str(m.content)
            contents.append({
                "role": role,
                "parts": [{"text": text}]
            })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature
            }
        }
        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        est_tokens = len(str(payload)) // 4
        if not await self.rate_limiter.acquire(est_tokens):
            await self.circuit_breaker.record_failure()
            raise RuntimeError("Rate limit exceeded for Gemini (429)")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                if not stream:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 429:
                        await self.rate_limiter.record_429()
                        await self.circuit_breaker.record_failure()
                        raise RuntimeError(f"Gemini 429: {resp.text}")
                    resp.raise_for_status()
                    await self.circuit_breaker.record_success()
                    data = resp.json()

                    text = ""
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts)

                    usage_meta = data.get("usageMetadata", {})
                    prompt_toks = usage_meta.get("promptTokenCount", est_tokens)
                    comp_toks = usage_meta.get("candidatesTokenCount", len(text) // 4)
                    cached_toks = usage_meta.get("cachedContentTokenCount", 0)
                    cost = CostCalculator.calculate_actual_cost(prompt_toks, comp_toks, cached_toks, model)

                    return ChatCompletionResponse(
                        model=model,
                        choices=[
                            ChatCompletionResponseChoice(
                                message=ChatMessage(role="assistant", content=text)
                            )
                        ],
                        usage=UsageInfo(
                            prompt_tokens=prompt_toks,
                            completion_tokens=comp_toks,
                            total_tokens=prompt_toks + comp_toks,
                            cached_tokens=cached_toks,
                            estimated_cost=cost
                        )
                    )
                else:
                    return self._stream_gemini(client, url, payload, model)
            except Exception as e:
                await self.circuit_breaker.record_failure()
                raise e

    async def _stream_gemini(self, client: httpx.AsyncClient, url: str, payload: dict, model: str) -> AsyncIterator[ChatCompletionChunk]:
        async with client.stream("POST", url, json=payload) as resp:
            if resp.status_code != 200:
                await self.circuit_breaker.record_failure()
                err = await resp.aread()
                raise RuntimeError(f"Gemini streaming error {resp.status_code}: {err.decode('utf-8')}")

            await self.circuit_breaker.record_success()
            chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    try:
                        chunk_obj = json.loads(data_str)
                        candidates = chunk_obj.get("candidates", [])
                        if candidates:
                            parts = candidates[0].get("content", {}).get("parts", [])
                            text = "".join(p.get("text", "") for p in parts)
                            if text:
                                yield ChatCompletionChunk(
                                    id=chunk_id,
                                    model=model,
                                    choices=[
                                        ChatCompletionChunkChoice(
                                            index=0,
                                            delta=DeltaMessage(role="assistant", content=text)
                                        )
                                    ]
                                )
                    except Exception:
                        continue
            
            # Final chunk
            yield ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    ChatCompletionChunkChoice(index=0, delta=DeltaMessage(), finish_reason="stop")
                ]
            )
