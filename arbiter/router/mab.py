"""
ARBITER Multi-Armed Bandit Engine (Module 3)
Contextual Thompson Sampling with Beta(α, β) distributions, exponential decay, and thread-safe updates.
"""

import math
import random
import time
import asyncio
import logging
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timezone
from arbiter.core.config import settings
from arbiter.models.types import TaskCategory
from arbiter.storage.models import load_all_bandit_states, upsert_bandit_state

logger = logging.getLogger(__name__)


class BanditArm:
    """
    Represents a single model's Beta distribution for a specific task category.
    """

    def __init__(
        self,
        provider: str,
        model: str,
        task_category: str,
        alpha: float = 1.0,
        beta: float = 1.0,
        total_trials: int = 0,
        last_updated: Optional[float] = None
    ):
        self.provider = provider
        self.model = model
        self.task_category = task_category
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.total_trials = int(total_trials)
        self.last_updated = last_updated or time.time()
        self._lock = asyncio.Lock()

    def apply_decay(self, half_life_hours: float) -> None:
        """
        Applies exponential decay to avoid getting stuck on stale historical performance.
        α' = 1.0 + (α - 1.0) * exp(-λ * Δt)
        """
        now = time.time()
        elapsed_hours = (now - self.last_updated) / 3600.0
        if elapsed_hours <= 0:
            return

        decay_constant = math.log(2.0) / max(half_life_hours, 1.0)
        decay_factor = math.exp(-decay_constant * elapsed_hours)

        # Decay towards uninformed prior (1.0, 1.0)
        self.alpha = 1.0 + (self.alpha - 1.0) * decay_factor
        self.beta = 1.0 + (self.beta - 1.0) * decay_factor
        self.last_updated = now

    def sample(self) -> float:
        """
        Draws a random sample from Beta(alpha, beta) using standard random generator or scipy/numpy.
        """
        try:
            return random.betavariate(max(0.01, self.alpha), max(0.01, self.beta))
        except Exception:
            # Fallback mean
            return self.alpha / (self.alpha + self.beta)

    @property
    def expected_value(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    async def update(self, reward: float, weight: float = 1.0) -> Tuple[float, float]:
        """
        Atomic update:
        reward in [0.0, 1.0].
        Positive reward increases alpha, negative/zero increases beta.
        """
        async with self._lock:
            reward = max(0.0, min(1.0, reward))
            self.alpha += reward * weight
            self.beta += (1.0 - reward) * weight
            self.total_trials += 1
            self.last_updated = time.time()
            return self.alpha, self.beta


class MABEngine:
    """
    Contextual Multi-Armed Bandit router coordinator.
    """

    def __init__(self, half_life_hours: float = 72.0, exploration_rate: float = 0.15):
        self.half_life_hours = half_life_hours
        self.exploration_rate = exploration_rate
        # Key: (model_name, task_category_str)
        self.arms: Dict[Tuple[str, str], BanditArm] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Loads persistent bandit states from SQLite."""
        async with self._lock:
            if self._initialized:
                return
            try:
                states = await load_all_bandit_states()
                for s in states:
                    key = (s["model"], s["task_category"])
                    arm = BanditArm(
                        provider=s["provider"],
                        model=s["model"],
                        task_category=s["task_category"],
                        alpha=s["alpha"],
                        beta=s["beta"],
                        total_trials=s["total_trials"]
                    )
                    self.arms[key] = arm
                logger.info(f"Loaded {len(self.arms)} bandit arm states from database.")
            except Exception as e:
                logger.warning(f"Could not load bandit states: {e}")
            self._initialized = True

    def get_or_create_arm(self, provider: str, model: str, category: TaskCategory) -> BanditArm:
        key = (model, category.value)
        if key not in self.arms:
            arm = BanditArm(provider=provider, model=model, task_category=category.value)
            self.arms[key] = arm
        return self.arms[key]

    def select_best_arm(
        self,
        candidates: List[Tuple[str, str]],  # List of (provider, model)
        category: TaskCategory,
        force_explore: bool = False
    ) -> Tuple[str, str, bool]:
        """
        Runs Thompson Sampling across candidates.
        Returns: (selected_provider, selected_model, was_exploration)
        """
        if not candidates:
            return ("mock", "mock-gpt-4o", False)

        # Apply decay to all relevant arms
        for p, m in candidates:
            arm = self.get_or_create_arm(p, m, category)
            arm.apply_decay(self.half_life_hours)

        # Epsilon exploration (random arm) or cold start
        if force_explore or random.random() < self.exploration_rate:
            chosen_p, chosen_m = random.choice(candidates)
            return (chosen_p, chosen_m, True)

        # Thompson Sampling: sample from each arm's posterior distribution
        best_score = -1.0
        best_candidate = candidates[0]

        for p, m in candidates:
            arm = self.get_or_create_arm(p, m, category)
            sample_val = arm.sample()
            if sample_val > best_score:
                best_score = sample_val
                best_candidate = (p, m)

        return (best_candidate[0], best_candidate[1], False)

    async def record_feedback(
        self,
        provider: str,
        model: str,
        category: TaskCategory,
        rating: int  # -1, 0, 1
    ) -> Tuple[float, float]:
        """
        Converts thumbs up/down into reward:
        +1 => reward = 1.0 (strong positive)
         0 => reward = 0.5 (neutral)
        -1 => reward = 0.0 (strong negative)
        """
        reward_map = {1: 1.0, 0: 0.5, -1: 0.0}
        reward = reward_map.get(rating, 0.5)

        arm = self.get_or_create_arm(provider, model, category)
        alpha, beta = await arm.update(reward, weight=1.5)

        # Save to database
        try:
            await upsert_bandit_state(
                provider=provider,
                model=model,
                task_category=category.value,
                alpha=alpha,
                beta=beta,
                total_trials=arm.total_trials
            )
        except Exception as e:
            logger.error(f"Failed to persist bandit state: {e}")

        return alpha, beta

    async def record_evaluation_quality(
        self,
        provider: str,
        model: str,
        category: TaskCategory,
        quality_score: float  # [0.0, 1.0]
    ) -> None:
        """
        Automated reward from Zero-LLM quality evaluator (Module 5).
        """
        arm = self.get_or_create_arm(provider, model, category)
        alpha, beta = await arm.update(quality_score, weight=0.5)
        try:
            await upsert_bandit_state(
                provider=provider,
                model=model,
                task_category=category.value,
                alpha=alpha,
                beta=beta,
                total_trials=arm.total_trials
            )
        except Exception:
            pass


mab_engine = MABEngine(
    half_life_hours=settings.mab_decay_half_life_hours,
    exploration_rate=settings.mab_exploration_rate
)
