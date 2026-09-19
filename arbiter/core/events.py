"""
ARBITER Asynchronous Event Bus for Non-blocking Dashboard Telemetry
"""

import asyncio
import json
import logging
from typing import Any, Dict, Set
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EventBus:
    """
    Decoupled In-Memory Event Bus for broadcasting telemetry to WebSockets.
    Guarantees that broadcasting never blocks the primary routing and completion pipeline.
    """

    def __init__(self, max_queue_size: int = 2000):
        self._subscribers: Set[asyncio.Queue] = set()
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._worker_task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._dispatch_loop(), name="arbiter_event_bus")
        logger.info("EventBus telemetry dispatch loop started.")

    async def stop(self) -> None:
        self._running = False
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("EventBus stopped.")

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Non-blocking publish method. If the queue is full, oldest events are dropped to preserve system latency.
        """
        payload = {
            "event": event_type,
            "data": data
        }
        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                _ = self._queue.get_nowait()  # Drop oldest
                self._queue.put_nowait(payload)
            except Exception:
                pass

    async def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subscribers.add(q)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def _dispatch_loop(self) -> None:
        while self._running:
            try:
                event = await self._queue.get()
                dead_queues = set()
                for sub in list(self._subscribers):
                    try:
                        sub.put_nowait(event)
                    except asyncio.QueueFull:
                        # Client too slow, drop message
                        pass
                    except Exception:
                        dead_queues.add(sub)
                for dq in dead_queues:
                    self._subscribers.discard(dq)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in EventBus dispatch: {e}")


# Global EventBus instance
bus = EventBus()
