"""
ARBITER Self-Training Loop (Module 2, Tier 3)
Retrains/adapts the classifier based on real-world request outcomes and user feedback.
"""

import asyncio
import logging
from typing import List
from arbiter.classifier.model import TrainedClassifier
from arbiter.storage.database import get_db_connection

logger = logging.getLogger(__name__)


class SelfTrainer:
    """
    Background worker that queries high-confidence samples (positive user feedback)
    and updates the trained classifier.
    """

    def __init__(self, classifier: TrainedClassifier, interval_seconds: float = 3600.0):
        self.classifier = classifier
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task | None = None
        self._running: bool = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._training_loop(), name="arbiter_self_trainer")
        logger.info("SelfTrainer background loop started.")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def run_training_cycle(self) -> int:
        """
        Gathers positively rated requests (+1 feedback) from the database and updates classifier.
        """
        conn = await get_db_connection()
        try:
            query = """
            SELECT t.prompt_text, r.task_category
            FROM feedback f
            JOIN requests r ON f.request_id = r.id
            JOIN traces t ON r.id = t.request_id
            WHERE f.rating = 1
            ORDER BY f.timestamp DESC
            LIMIT 100
            """
            async with conn.execute(query) as cursor:
                rows = await cursor.fetchall()
                if not rows:
                    return 0

                texts: List[str] = []
                labels: List[str] = []
                for row in rows:
                    prompt = row["prompt_text"]
                    cat = row["task_category"]
                    if prompt and cat:
                        texts.append(prompt)
                        labels.append(cat)

                if texts:
                    self.classifier.partial_fit(texts, labels)
                    logger.info(f"Self-training cycle updated classifier with {len(texts)} samples.")
                    return len(texts)
                return 0
        except Exception as e:
            logger.error(f"Error during self-training cycle: {e}")
            return 0
        finally:
            await conn.close()

    async def _training_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                await self.run_training_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in self-training loop: {e}")
