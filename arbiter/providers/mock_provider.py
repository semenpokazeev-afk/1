"""
ARBITER High-Fidelity Mock Provider (Module 4)
Simulates realistic latency, streaming tokens, error injection, and rate limits for offline execution & testing.
"""

import time
import asyncio
import uuid
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
from arbiter.models.types import CircuitState


class MockProvider(BaseProvider):
    def __init__(
        self,
        name: str = "mock",
        models: Optional[List[str]] = None,
        base_latency_ms: int = 120,
        failure_rate: float = 0.0
    ):
        self.name = name
        self.models = models or [
            "mock-gpt-4o",
            "mock-claude-3-5-sonnet",
            "mock-gemini-1.5-flash",
            "mock-llama-3"
        ]
        self.base_latency_ms = base_latency_ms
        self.failure_rate = failure_rate
        self.circuit_breaker = CircuitBreaker(self.name)
        self.rate_limiter = DualDimensionRateLimiter(rpm=300, tpm=200_000)

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        return CostCalculator.estimate_cost(input_tokens, output_tokens, model)

    async def health_check(self) -> HealthStatus:
        can_exec = await self.circuit_breaker.can_execute()
        return HealthStatus(
            provider=self.name,
            is_healthy=can_exec,
            circuit_state=self.circuit_breaker.state,
            latency_ms=self.base_latency_ms,
            rpm_used_ratio=self.rate_limiter.rpm_utilization,
            tpm_used_ratio=self.rate_limiter.tpm_utilization
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
        if not await self.circuit_breaker.can_execute():
            raise RuntimeError(f"CircuitBreaker OPEN for provider '{self.name}'")

        # Estimate prompt tokens
        full_text = " ".join([m.content if isinstance(m.content, str) else "" for m in messages])
        prompt_tokens = max(10, len(full_text) // 4)
        expected_output_tokens = min(max_tokens or 200, 200)

        acquired = await self.rate_limiter.acquire(prompt_tokens + expected_output_tokens)
        if not acquired:
            await self.circuit_breaker.record_failure()
            raise RuntimeError(f"Rate limit exceeded for provider '{self.name}' (429)")

        # Realistic latency
        await asyncio.sleep(self.base_latency_ms / 1000.0)

        # Failure simulation if configured
        if self.failure_rate > 0.0:
            import random
            if random.random() < self.failure_rate:
                await self.circuit_breaker.record_failure()
                raise RuntimeError(f"Simulated network failure from '{self.name}'")

        await self.circuit_breaker.record_success()

        # Generate intelligent mock response based on the prompt
        sample_response = self._generate_sample_response(full_text, model)
        completion_tokens = len(sample_response) // 4
        actual_cost = CostCalculator.calculate_actual_cost(prompt_tokens, completion_tokens, 0, model)

        if stream:
            return self._stream_generator(sample_response, model, prompt_tokens, completion_tokens, actual_cost)

        return ChatCompletionResponse(
            model=model,
            choices=[
                ChatCompletionResponseChoice(
                    message=ChatMessage(role="assistant", content=sample_response)
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated_cost=actual_cost
            )
        )

    async def _stream_generator(
        self,
        text: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        actual_cost: float
    ) -> AsyncIterator[ChatCompletionChunk]:
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        words = text.split(" ")
        for i, word in enumerate(words):
            delta_content = word + (" " if i < len(words) - 1 else "")
            yield ChatCompletionChunk(
                id=chunk_id,
                model=model,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=DeltaMessage(role="assistant" if i == 0 else None, content=delta_content)
                    )
                ]
            )
            await asyncio.sleep(0.015)  # 15ms streaming chunk cadence

        # Final chunk with finish reason and usage
        yield ChatCompletionChunk(
            id=chunk_id,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta=DeltaMessage(),
                    finish_reason="stop"
                )
            ],
            usage=UsageInfo(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated_cost=actual_cost
            )
        )

    def _generate_sample_response(self, prompt: str, model: str) -> str:
        prompt_lower = prompt.lower()
        if "код" in prompt_lower or "code" in prompt_lower or "function" in prompt_lower or "def " in prompt_lower:
            return (
                f"```python\n"
                f"# Generated solution by {model}\n"
                f"def solve(data: list[int]) -> dict[str, float]:\n"
                f"    \"\"\"High-performance data processing function.\"\"\"\n"
                f"    if not data:\n"
                f"        return {{'mean': 0.0, 'count': 0}}\n"
                f"    total = sum(data)\n"
                f"    return {{'mean': total / len(data), 'count': len(data)}}\n"
                f"```\n\n"
                f"Код полностью протестирован и оптимизирован для работы в асинхронном окружении."
            )
        elif "переведи" in prompt_lower or "translate" in prompt_lower:
            return f"Translated text generated by {model}: The system successfully operates with high precision and low latency."
        elif "summary" in prompt_lower or "суммариз" in prompt_lower or "тезис" in prompt_lower:
            return (
                f"Ключевые тезисы от {model}:\n"
                f"1. Архитектура построена на независимых модулях с асинхронным EventBus.\n"
                f"2. Маршрутизация использует сэмплирование Томпсона для минимизации задержек и стоимости.\n"
                f"3. Все метрики логируются в реальном времени."
            )
        else:
            return f"Здравствуйте! Я модель {model}. Запрос успешно обработан через интеллектуальный роутер Arbiter."
