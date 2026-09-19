"""
ARBITER Base Provider Protocol and Abstractions (Module 4)
"""

from typing import Protocol, List, AsyncIterator, Union, Dict, Any, Optional
from pydantic import BaseModel, Field
from arbiter.models.schemas import (
    ChatMessage,
    ChatCompletionResponse,
    ChatCompletionChunk,
    UsageInfo
)
from arbiter.models.types import CircuitState


class HealthStatus(BaseModel):
    provider: str
    is_healthy: bool
    circuit_state: CircuitState = CircuitState.CLOSED
    latency_ms: Optional[int] = None
    rpm_used_ratio: float = 0.0
    tpm_used_ratio: float = 0.0
    error_rate_1h: float = 0.0
    message: Optional[str] = None


class BaseProvider:
    """
    Abstract base class for all LLM providers in Arbiter.
    """
    name: str
    models: List[str]

    async def complete(
        self,
        messages: List[ChatMessage],
        model: str,
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Union[ChatCompletionResponse, AsyncIterator[ChatCompletionChunk]]:
        raise NotImplementedError

    async def health_check(self) -> HealthStatus:
        raise NotImplementedError

    def estimate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        raise NotImplementedError
