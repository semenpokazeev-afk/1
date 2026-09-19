"""
ARBITER User Feedback API Endpoint (Module 1 & Module 6)
Allows submitting 👍 (+1) / 👎 (-1) ratings to continuously train the Thompson Sampling MAB engine.
"""

import uuid
import logging
from fastapi import APIRouter, HTTPException
from arbiter.models.schemas import FeedbackRequest, FeedbackResponse
from arbiter.models.types import TaskCategory
from arbiter.storage.models import save_feedback, get_request, get_provider_calls_for_request
from arbiter.router.mab import mab_engine
from arbiter.core.events import bus

logger = logging.getLogger(__name__)

feedback_router = APIRouter(prefix="/v1/arbiter", tags=["Arbiter Feedback"])


@feedback_router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(req: FeedbackRequest):
    # 1. Fetch original request record
    db_req = await get_request(req.request_id)
    if not db_req:
        raise HTTPException(status_code=404, detail=f"Request with ID '{req.request_id}' not found.")

    # 2. Fetch calls to find which model was selected
    calls = await get_provider_calls_for_request(req.request_id)
    selected_call = next((c for c in calls if c.get("was_selected")), None)
    if not selected_call and calls:
        selected_call = calls[0]

    provider_name = selected_call["provider"] if selected_call else "mock"
    model_name = selected_call["model"] if selected_call else "mock-gpt-4o"
    category_str = db_req["task_category"]

    try:
        task_cat = TaskCategory(category_str)
    except ValueError:
        task_cat = TaskCategory.CONVERSATION

    # 3. Save feedback record
    feedback_id = f"fb-{uuid.uuid4().hex[:12]}"
    await save_feedback(
        feedback_id=feedback_id,
        request_id=req.request_id,
        rating=req.rating,
        comment=req.comment
    )

    # 4. Atomic MAB Update
    alpha, beta = await mab_engine.record_feedback(
        provider=provider_name,
        model=model_name,
        category=task_cat,
        rating=req.rating
    )

    # 5. Broadcast to real-time dashboard
    bus.publish("feedback_recorded", {
        "request_id": req.request_id,
        "rating": req.rating,
        "provider": provider_name,
        "model": model_name,
        "category": category_str,
        "alpha": alpha,
        "beta": beta
    })

    return FeedbackResponse(
        status="success",
        request_id=req.request_id,
        alpha_updated=round(alpha, 4),
        beta_updated=round(beta, 4)
    )
