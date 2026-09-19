"""
ARBITER Real-Time WebSocket Telemetry Endpoint (Module 1 & Module 7)
Streams routing events, bandit state updates, and provider health to the dashboard in real-time.
"""

import json
import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from arbiter.core.events import bus
from arbiter.storage.metrics import get_live_feed
from arbiter.providers import pool

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["WebSocket"])


@ws_router.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    await websocket.accept()
    sub_queue = await bus.subscribe()
    logger.info("WebSocket client connected to /ws/dashboard")

    try:
        # 1. Send initial state snapshot to newly connected dashboard
        initial_feed = await get_live_feed(limit=25)
        health_statuses = await pool.get_all_health_statuses()

        await websocket.send_text(json.dumps({
            "event": "initial_snapshot",
            "data": {
                "feed": initial_feed,
                "health": [h.model_dump() for h in health_statuses]
            }
        }))

        # 2. Main push loop
        while True:
            # Wait for event from EventBus queue
            try:
                event = await asyncio.wait_for(sub_queue.get(), timeout=20.0)
                await websocket.send_text(json.dumps(event))
            except asyncio.TimeoutError:
                # Send periodic heartbeat ping to prevent connection timeout
                await websocket.send_text(json.dumps({"event": "ping", "data": {}}))

    except WebSocketDisconnect:
        logger.info("WebSocket dashboard client disconnected.")
    except Exception as e:
        logger.error(f"Error in WebSocket loop: {e}")
    finally:
        await bus.unsubscribe(sub_queue)
