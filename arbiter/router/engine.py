"""
ARBITER Master Router Engine (Module 3)
Coordinates Task Classifier output, Constraint Solver, and Thompson Sampling MAB.
"""

from typing import List, Tuple, Optional
from arbiter.models.types import Strategy, TaskCategory, RoutingDecision
from arbiter.models.schemas import ChatMessage
from arbiter.providers import pool
from arbiter.providers.cost_calculator import CostCalculator
from arbiter.router.mab import mab_engine
from arbiter.router.constraints import ConstraintSolver


class RouterEngine:
    def __init__(self):
        self.mab = mab_engine
        self.constraints = ConstraintSolver()

    def _get_available_candidates(self) -> List[Tuple[str, str]]:
        candidates = []
        for p_name, p in pool.providers.items():
            if p_name == "mock" or getattr(p, "api_key", None):
                for m in p.models:
                    candidates.append((p_name, m))
        if not candidates:
            candidates.append(("mock", "mock-gpt-4o"))
        return candidates

    async def route_request(
        self,
        messages: List[ChatMessage],
        category: TaskCategory,
        strategy: Strategy = Strategy.AUTO,
        budget_limit: Optional[float] = None
    ) -> RoutingDecision:
        """
        Computes optimal provider and model based on category, strategy, and constraints.
        """
        # 1. Estimate prompt tokens
        full_text = " ".join([m.content if isinstance(m.content, str) else "" for m in messages])
        input_tokens = max(10, len(full_text) // 4)

        # 2. Gather candidates
        raw_candidates = self._get_available_candidates()

        # 3. Apply constraints (budget, circuit breaker)
        valid_candidates = await self.constraints.filter_candidates(
            raw_candidates,
            estimated_input_tokens=input_tokens,
            budget_limit=budget_limit
        )

        # 4. Apply strategy filtering
        filtered_candidates = self.constraints.apply_strategy(
            valid_candidates,
            strategy=strategy,
            category=category,
            input_tokens=input_tokens
        )

        # 5. Handle Strategy specifics
        if strategy == Strategy.CONSENSUS:
            # Top 3 diverse candidates
            top_candidates = filtered_candidates[:3]
            est_cost = sum(
                CostCalculator.estimate_cost(input_tokens, 300, m)
                for _, m in top_candidates
            )
            return RoutingDecision(
                selected_provider=top_candidates[0][0],
                selected_model=top_candidates[0][1],
                category=category,
                strategy=strategy,
                estimated_cost=est_cost,
                candidate_models=[m for _, m in top_candidates],
                reasoning=f"Consensus mode: Parallel query to top {len(top_candidates)} models"
            )

        if strategy in (Strategy.CHEAPEST, Strategy.FASTEST):
            chosen_p, chosen_m = filtered_candidates[0]
            est_cost = CostCalculator.estimate_cost(input_tokens, 200, chosen_m)
            return RoutingDecision(
                selected_provider=chosen_p,
                selected_model=chosen_m,
                category=category,
                strategy=strategy,
                estimated_cost=est_cost,
                exploration=False,
                reasoning=f"Strategy deterministic selection: {strategy.value}"
            )

        # AUTO / QUALITY: Thompson Sampling MAB
        chosen_p, chosen_m, was_explore = self.mab.select_best_arm(
            filtered_candidates,
            category=category
        )
        est_cost = CostCalculator.estimate_cost(input_tokens, 200, chosen_m)

        arm = self.mab.get_or_create_arm(chosen_p, chosen_m, category)
        reasoning = (
            f"Thompson Sampling (Beta({arm.alpha:.2f}, {arm.beta:.2f})) "
            f"with expected win-rate {arm.expected_value*100:.1f}%. "
            f"{'Exploration step.' if was_explore else 'Exploitation step.'}"
        )

        return RoutingDecision(
            selected_provider=chosen_p,
            selected_model=chosen_m,
            category=category,
            strategy=strategy,
            estimated_cost=est_cost,
            exploration=was_explore,
            candidate_models=[m for _, m in filtered_candidates],
            reasoning=reasoning
        )


router = RouterEngine()
