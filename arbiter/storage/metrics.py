"""
ARBITER Fast Analytics Queries and Aggregations (Module 6)
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
import numpy as np
from arbiter.storage.database import get_db_connection


async def get_live_feed(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Returns the most recent completed requests with their selected provider, model, latency, cost, and quality score.
    """
    conn = await get_db_connection()
    try:
        query = """
        SELECT 
            r.id,
            r.timestamp,
            r.task_category,
            r.strategy,
            r.input_tokens,
            pc.provider,
            pc.model,
            pc.latency_ms,
            pc.actual_cost,
            pc.quality_score,
            pc.status,
            f.rating as user_feedback
        FROM requests r
        LEFT JOIN provider_calls pc ON r.id = pc.request_id AND pc.was_selected = 1
        LEFT JOIN feedback f ON r.id = f.request_id
        ORDER BY r.timestamp DESC
        LIMIT ?
        """
        async with conn.execute(query, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_average_cost_by_category(hours: int = 24) -> List[Dict[str, Any]]:
    """
    Average and total cost per task category over a given time window.
    """
    conn = await get_db_connection()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        query = """
        SELECT 
            task_category,
            COUNT(*) as request_count,
            AVG(pc.actual_cost) as avg_cost,
            SUM(pc.actual_cost) as total_cost
        FROM requests r
        JOIN provider_calls pc ON r.id = pc.request_id AND pc.was_selected = 1
        WHERE r.timestamp >= ?
        GROUP BY task_category
        ORDER BY total_cost DESC
        """
        async with conn.execute(query, (cutoff,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_model_win_rates() -> List[Dict[str, Any]]:
    """
    Calculates the win rate of each model overall and by category:
    win_rate = selected_count / total_participated_count
    """
    conn = await get_db_connection()
    try:
        query = """
        SELECT 
            model,
            provider,
            COUNT(*) as total_calls,
            SUM(was_selected) as wins,
            CAST(SUM(was_selected) AS FLOAT) / COUNT(*) as win_rate,
            AVG(quality_score) as avg_quality,
            AVG(latency_ms) as avg_latency
        FROM provider_calls
        GROUP BY model, provider
        ORDER BY win_rate DESC
        """
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await conn.close()


async def get_latency_percentiles_by_model() -> Dict[str, Dict[str, float]]:
    """
    Calculates P50, P95, P99 latency in milliseconds for each active model.
    """
    conn = await get_db_connection()
    try:
        query = "SELECT model, latency_ms FROM provider_calls WHERE status = 'success'"
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()

        by_model: Dict[str, List[int]] = {}
        for r in rows:
            m = r["model"]
            by_model.setdefault(m, []).append(r["latency_ms"])

        results = {}
        for m, latencies in by_model.items():
            if not latencies:
                continue
            arr = np.array(latencies)
            results[m] = {
                "count": len(arr),
                "p50": float(np.percentile(arr, 50)),
                "p95": float(np.percentile(arr, 95)),
                "p99": float(np.percentile(arr, 99)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr))
            }
        return results
    finally:
        await conn.close()


async def get_quality_heatmap() -> List[Dict[str, Any]]:
    """
    Computes quality scores broken down by model × task_category.
    """
    conn = await get_db_connection()
    try:
        query = """
        SELECT 
            r.task_category,
            pc.model,
            AVG(pc.quality_score) as avg_quality,
            COUNT(*) as sample_count
        FROM provider_calls pc
        JOIN requests r ON pc.request_id = r.id
        WHERE pc.status = 'success'
        GROUP BY r.task_category, pc.model
        """
        async with conn.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await conn.close()


async def detect_anomalies() -> List[Dict[str, Any]]:
    """
    Detects sudden drops in quality (> 20% below model historical average) or latency spikes.
    """
    conn = await get_db_connection()
    cutoff_recent = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    try:
        query = """
        SELECT 
            model,
            AVG(CASE WHEN timestamp >= ? THEN quality_score ELSE NULL END) as recent_quality,
            AVG(CASE WHEN timestamp < ? THEN quality_score ELSE NULL END) as historical_quality,
            AVG(CASE WHEN timestamp >= ? THEN latency_ms ELSE NULL END) as recent_latency,
            AVG(CASE WHEN timestamp < ? THEN latency_ms ELSE NULL END) as historical_latency,
            SUM(CASE WHEN status != 'success' AND timestamp >= ? THEN 1 ELSE 0 END) as recent_errors
        FROM provider_calls pc
        JOIN requests r ON pc.request_id = r.id
        GROUP BY model
        HAVING recent_quality IS NOT NULL AND historical_quality IS NOT NULL
        """
        async with conn.execute(query, (cutoff_recent, cutoff_recent, cutoff_recent, cutoff_recent, cutoff_recent)) as cursor:
            rows = await cursor.fetchall()
            anomalies = []
            for r in rows:
                if r["historical_quality"] and r["recent_quality"]:
                    q_drop = (r["historical_quality"] - r["recent_quality"]) / r["historical_quality"]
                    if q_drop > 0.20:
                        anomalies.append({
                            "type": "quality_drop",
                            "model": r["model"],
                            "message": f"Quality dropped by {q_drop*100:.1f}% in the last hour"
                        })
                if r["historical_latency"] and r["recent_latency"]:
                    lat_spike = (r["recent_latency"] - r["historical_latency"]) / r["historical_latency"]
                    if lat_spike > 0.50:
                        anomalies.append({
                            "type": "latency_spike",
                            "model": r["model"],
                            "message": f"Latency increased by {lat_spike*100:.1f}% in the last hour"
                        })
            return anomalies
    finally:
        await conn.close()


async def forecast_monthly_expenses() -> Dict[str, Any]:
    """
    Projects 30-day expenses using linear usage projection based on recent requests.
    """
    conn = await get_db_connection()
    cutoff_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        query = """
        SELECT 
            COALESCE(SUM(pc.actual_cost), 0.0) as cost_24h,
            COUNT(DISTINCT r.id) as count_24h
        FROM requests r
        JOIN provider_calls pc ON r.id = pc.request_id AND pc.was_selected = 1
        WHERE r.timestamp >= ?
        """
        async with conn.execute(query, (cutoff_24h,)) as cursor:
            row = await cursor.fetchone()
            cost_24h = row["cost_24h"] if row else 0.0
            count_24h = row["count_24h"] if row else 0
            
            projected_monthly_cost = round(cost_24h * 30, 4)
            projected_monthly_requests = count_24h * 30
            
            return {
                "cost_last_24h": round(cost_24h, 4),
                "requests_last_24h": count_24h,
                "projected_monthly_cost": projected_monthly_cost,
                "projected_monthly_requests": projected_monthly_requests
            }
    finally:
        await conn.close()
