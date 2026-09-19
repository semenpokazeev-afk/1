"""
ARBITER OpenAI-compatible DTOs and API Schemas
"""

import time
import uuid
from typing import Any, List, Optional, Union, Dict
from pydantic import BaseModel, Field
from arbiter.models.types import Strategy, TaskCategory, FeedbackRating


class ChatMessage(BaseModel):
    role: str
    content: Union[str, List[Dict[str, Any]]]
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "arbiter-auto"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 1.0
    n: Optional[int] = 1
    stream: Optional[bool] = False
    stop: Optional[Union[str, List[str]]] = None
    max_tokens: Optional[int] = None
    presence_penalty: Optional[float] = 0.0
    frequency_penalty: Optional[float] = 0.0
    user: Optional[str] = None

    # Custom Arbiter headers/fields
    strategy: Optional[Strategy] = None
    budget_limit: Optional[float] = None


class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    cached_tokens: int = 0


class ChatCompletionResponseChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: Optional[str] = "stop"


class ChatCompletionResponse(BaseModel):
    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionResponseChoice]
    usage: UsageInfo
    system_fingerprint: Optional[str] = "arbiter-router-v1"
    
    # Arbiter metadata
    arbiter_category: Optional[TaskCategory] = None
    arbiter_strategy: Optional[Strategy] = None
    arbiter_quality_score: Optional[float] = None
    arbiter_consensus_models: Optional[List[str]] = None


class DeltaMessage(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: DeltaMessage
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: List[ChatCompletionChunkChoice]
    system_fingerprint: Optional[str] = "arbiter-router-v1"
    usage: Optional[UsageInfo] = None


class FeedbackRequest(BaseModel):
    request_id: str
    rating: int = Field(..., ge=-1, le=1)  # -1, 0, 1
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    status: str = "success"
    request_id: str
    alpha_updated: float
    beta_updated: float
