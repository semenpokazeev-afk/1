"""
ARBITER Analytics, Telemetry, and Replay API Endpoints (Module 1, 6 & Bonus 2)
"""

import math
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from arbiter.storage.metrics import (
    get_live_feed,
    get_average_cost_by_category,
    get_model_win_rates,
    get_latency_percentiles_by_model,
    get_quality_heatmap,
    detect_anomalies,
    forecast_monthly_expenses
)
from arbiter.storage.models import get_trace
from arbiter.providers import pool
from arbiter.router.mab import mab_engine
from arbiter.router.engine import router
from arbiter.models.schemas import ChatMessage
from arbiter.models.types import Strategy, TaskCategory

analytics_router = APIRouter(prefix="/v1/arbiter", tags=["Arbiter Telemetry & Analytics"])


@analytics_router.get("/analytics/summary")
async def get_analytics_summary() -> Dict[str, Any]:
    cost_by_category = await get_average_cost_by_category(hours=24)
    win_rates = await get_model_win_rates()
    latencies = await get_latency_percentiles_by_model()
    heatmap = await get_quality_heatmap()
    anomalies = await detect_anomalies()
    forecast = await forecast_monthly_expenses()

    return {
        "cost_by_category": cost_by_category,
        "win_rates": win_rates,
        "latencies": latencies,
        "quality_heatmap": heatmap,
        "anomalies": anomalies,
        "forecast": forecast
    }


@analytics_router.get("/analytics/feed")
async def get_feed(limit: int = 50) -> List[Dict[str, Any]]:
    return await get_live_feed(limit=limit)


@analytics_router.get("/analytics/bandit")
async def get_bandit_arms() -> List[Dict[str, Any]]:
    """
    Returns all Beta distributions and precomputed PDF curves for front-end rendering.
    """
    arms_data = []
    for (model, category), arm in mab_engine.arms.items():
        # Precompute 20 points of Beta(alpha, beta) PDF for front-end chart
        pdf_curve = []
        alpha, beta = max(0.5, arm.alpha), max(0.5, arm.beta)
        try:
            # Beta PDF: x^(a-1) * (1-x)^(b-1) / B(a,b)
            # Use log-gamma to avoid overflow
            lbeta = math.lgamma(alpha) + math.lgamma(beta) - math.lgamma(alpha + beta)
            for i in range(1, 20):
                x = i / 20.0
                log_pdf = (alpha - 1.0) * math.log(x) + (beta - 1.0) * math.log(1.0 - x) - lbeta
                y = math.exp(min(log_pdf, 50.0))
                pdf_curve.append({"x": round(x, 2), "y": round(y, 3)})
        except Exception:
            pdf_curve = []

        arms_data.append({
            "provider": arm.provider,
            "model": arm.model,
            "task_category": arm.task_category,
            "alpha": round(arm.alpha, 2),
            "beta": round(arm.beta, 2),
            "trials": arm.total_trials,
            "expected_win_rate": round(arm.expected_value, 4),
            "pdf_curve": pdf_curve
        })

    return arms_data


@analytics_router.get("/health")
async def get_provider_health() -> List[Dict[str, Any]]:
    statuses = await pool.get_all_health_statuses()
    return [s.model_dump() for s in statuses]


class BanditConfigRequest(BaseModel):
    exploration_rate: Optional[float] = None
    decay_half_life_hours: Optional[float] = None


@analytics_router.post("/bandit/config")
async def update_bandit_config(req: BanditConfigRequest) -> Dict[str, Any]:
    if req.exploration_rate is not None:
        mab_engine.exploration_rate = max(0.0, min(1.0, req.exploration_rate))
    if req.decay_half_life_hours is not None:
        mab_engine.decay_half_life_hours = max(1.0, req.decay_half_life_hours)
    return {
        "status": "updated",
        "exploration_rate": mab_engine.exploration_rate,
        "decay_half_life_hours": mab_engine.decay_half_life_hours
    }



class ReplayRequest(BaseModel):
    request_id: str
    override_strategy: Optional[Strategy] = None
    override_budget: Optional[float] = None


@analytics_router.post("/replay")
async def replay_request(req: ReplayRequest) -> Dict[str, Any]:
    """
    Bonus 2: Replays a past recorded request under different constraints/strategy and generates a diff.
    """
    trace = await get_trace(req.request_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"No trace found for request {req.request_id}")

    prompt_text = trace["prompt_text"]
    original_decision = trace["trace_data"].get("decision", {})

    # Re-route with overrides
    category = TaskCategory(original_decision.get("category", "conversation"))
    strategy = req.override_strategy or Strategy(original_decision.get("strategy", "auto"))
    budget = req.override_budget if req.override_budget is not None else original_decision.get("budget_limit")

    new_decision = await router.route_request(
        messages=[ChatMessage(role="user", content=prompt_text)],
        category=category,
        strategy=strategy,
        budget_limit=budget
    )

    return {
        "request_id": req.request_id,
        "prompt": prompt_text,
        "original_decision": original_decision,
        "replayed_decision": new_decision.model_dump(),
        "diff": {
            "model_changed": original_decision.get("selected_model") != new_decision.selected_model,
            "cost_difference": round(new_decision.estimated_cost - original_decision.get("estimated_cost", 0.0), 6),
            "strategy_used": strategy.value
        }
    }
