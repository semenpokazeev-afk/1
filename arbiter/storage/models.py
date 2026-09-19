"""
ARBITER Storage Models and Repository Methods
"""

import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from arbiter.storage.database import get_db_connection


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def save_request(
    request_id: str,
    task_category: str,
    strategy: str,
    input_tokens: int,
    estimated_cost: float,
    budget_limit: Optional[float] = None
) -> None:
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO requests (id, timestamp, task_category, strategy, input_tokens, estimated_cost, budget_limit)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (request_id, now_utc_iso(), task_category, strategy, input_tokens, estimated_cost, budget_limit)
        )
        await conn.commit()
    finally:
        await conn.close()


async def save_provider_call(
    call_id: str,
    request_id: str,
    provider: str,
    model: str,
    status: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
    actual_cost: float,
    quality_score: float,
    was_selected: bool
) -> None:
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO provider_calls (
                id, request_id, provider, model, status, latency_ms,
                input_tokens, output_tokens, actual_cost, quality_score, was_selected
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                call_id, request_id, provider, model, status, latency_ms,
                input_tokens, output_tokens, actual_cost, quality_score, int(was_selected)
            )
        )
        await conn.commit()
    finally:
        await conn.close()


async def save_feedback(
    feedback_id: str,
    request_id: str,
    rating: int,
    comment: Optional[str] = None
) -> None:
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO feedback (id, request_id, rating, comment, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (feedback_id, request_id, rating, comment, now_utc_iso())
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_request(request_id: str) -> Optional[Dict[str, Any]]:
    conn = await get_db_connection()
    try:
        async with conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
    finally:
        await conn.close()


async def get_provider_calls_for_request(request_id: str) -> List[Dict[str, Any]]:
    conn = await get_db_connection()
    try:
        async with conn.execute("SELECT * FROM provider_calls WHERE request_id = ?", (request_id,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await conn.close()


async def load_all_bandit_states() -> List[Dict[str, Any]]:
    conn = await get_db_connection()
    try:
        async with conn.execute("SELECT * FROM bandit_state") as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await conn.close()


async def upsert_bandit_state(
    provider: str,
    model: str,
    task_category: str,
    alpha: float,
    beta: float,
    total_trials: int
) -> None:
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO bandit_state (provider, model, task_category, alpha, beta, total_trials, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(provider, model, task_category) DO UPDATE SET
                alpha = excluded.alpha,
                beta = excluded.beta,
                total_trials = excluded.total_trials,
                last_updated = excluded.last_updated
            """,
            (provider, model, task_category, alpha, beta, total_trials, now_utc_iso())
        )
        await conn.commit()
    finally:
        await conn.close()


async def save_trace(
    trace_id: str,
    request_id: str,
    prompt_text: str,
    response_text: str,
    trace_data: Dict[str, Any]
) -> None:
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            INSERT INTO traces (id, request_id, prompt_text, response_text, trace_data, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (trace_id, request_id, prompt_text, response_text, json.dumps(trace_data), now_utc_iso())
        )
        await conn.commit()
    finally:
        await conn.close()


async def get_trace(request_id: str) -> Optional[Dict[str, Any]]:
    conn = await get_db_connection()
    try:
        async with conn.execute("SELECT * FROM traces WHERE request_id = ? ORDER BY timestamp DESC LIMIT 1", (request_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d["trace_data"] = json.loads(d["trace_data"])
                return d
            return None
    finally:
        await conn.close()
