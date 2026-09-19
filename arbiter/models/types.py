"""
ARBITER Core Domain Enums and Data Types
"""

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class TaskCategory(str, Enum):
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    CREATIVE_WRITING = "creative_writing"
    DATA_ANALYSIS = "data_analysis"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    REASONING = "reasoning"
    CONVERSATION = "conversation"
    SYSTEM_PROMPT = "system_prompt"
    MULTIMODAL = "multimodal"


class Strategy(str, Enum):
    AUTO = "auto"
    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    QUALITY = "quality"
    CONSENSUS = "consensus"


class ProviderCallStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class FeedbackRating(int, Enum):
    NEGATIVE = -1
    NEUTRAL = 0
    POSITIVE = 1


class ClassificationResult(BaseModel):
    category: TaskCategory
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    method: str = Field(default="rule_based")  # "rule_based" | "trained_model" | "fallback"
    features: dict[str, Any] = Field(default_factory=dict)


class RoutingDecision(BaseModel):
    selected_provider: str
    selected_model: str
    category: TaskCategory
    strategy: Strategy
    estimated_cost: float
    exploration: bool = False
    candidate_models: list[str] = Field(default_factory=list)
    reasoning: str = ""
