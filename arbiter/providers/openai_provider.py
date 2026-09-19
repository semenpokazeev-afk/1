"""
ARBITER OpenAI Async Provider (Module 4)
"""

import json
import httpx
from typing import List, AsyncIterator, Union, Optional
from arbiter.providers.base import BaseProvider, HealthStatus
from arbiter.providers.cost_calculator import CostCalculator
from arbiter.providers.circuit_breaker import CircuitBreaker
from arbiter.providers.rate_limiter import DualDimensionRateLimiter
from arbiter.models.schemas import (
    ChatMessage,
    ChatCompletionResponse,
    ChatCompletionChunk,
    UsageInfo
)


class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: Optional[str] = None):
        self.name = "openai"
        self.api_key = api_key
        self.models = ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
        self.base_url = "https://api.openai.com/v1"
        self.circuit_breaker = CircuitBreaker(self.name)
        self.rate_limiter = DualDimensionRateLimiter(rpm=500, tpm=300_000)

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
            raise RuntimeError("OpenAI API key is not configured.")
        if not await self.circuit_breaker.can_execute():
            raise RuntimeError(f"Circuit breaker is OPEN for {self.name}")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        # Acquire rate limits
        est_tokens = len(str(payload)) // 4
        if not await self.rate_limiter.acquire(est_tokens):
            await self.circuit_breaker.record_failure()
            raise RuntimeError("Rate limit exceeded for OpenAI (429)")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                if not stream:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code == 429:
                        await self.rate_limiter.record_429()
                        await self.circuit_breaker.record_failure()
                        raise RuntimeError(f"OpenAI 429 Too Many Requests: {resp.text}")
                    resp.raise_for_status()
                    await self.circuit_breaker.record_success()
                    data = resp.json()
                    return ChatCompletionResponse.model_validate(data)
                else:
                    # Return streaming generator
                    return self._stream_response(client, url, headers, payload)
            except Exception as e:
                await self.circuit_breaker.record_failure()
                raise e

    async def _stream_response(self, client: httpx.AsyncClient, url: str, headers: dict, payload: dict) -> AsyncIterator[ChatCompletionChunk]:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                await self.circuit_breaker.record_failure()
                err = await resp.aread()
                raise RuntimeError(f"OpenAI streaming error {resp.status_code}: {err.decode('utf-8')}")

            await self.circuit_breaker.record_success()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk_dict = json.loads(data_str)
                        yield ChatCompletionChunk.model_validate(chunk_dict)
                    except Exception:
                        continue
