"""
ARBITER Constraint Solver (Module 3)
Filters candidate models by budget limits, SLA latency, and circuit breaker availability.
"""

from typing import List, Tuple, Optional
from arbiter.models.types import Strategy, TaskCategory
from arbiter.providers import pool
from arbiter.providers.cost_calculator import CostCalculator
from arbiter.models.types import CircuitState


class ConstraintSolver:
    """
    Enforces operational constraints:
    - User budget (X-Arbiter-Budget)
    - Circuit Breaker health (excludes OPEN providers)
    - Strategy filters (fastest, cheapest, quality)
    """

    @staticmethod
    async def filter_candidates(
        candidates: List[Tuple[str, str]],  # (provider, model)
        estimated_input_tokens: int,
        budget_limit: Optional[float] = None
    ) -> List[Tuple[str, str]]:
        valid = []
        for provider_name, model_name in candidates:
            # Check provider health & circuit state
            p = pool.get_provider(provider_name)
            if p is not None and hasattr(p, "circuit_breaker"):
                if p.circuit_breaker.state == CircuitState.OPEN:
                    continue  # Fast-fail, exclude open circuit

            # Check budget constraint
            if budget_limit is not None:
                est_cost = CostCalculator.estimate_cost(
                    input_tokens=estimated_input_tokens,
                    estimated_output_tokens=300,
                    model=model_name
                )
                if est_cost > budget_limit:
                    continue  # Exceeds user request budget

            valid.append((provider_name, model_name))

        # If all candidates filtered out by budget or health, fallback to cheapest safe mock
        if not valid:
            valid.append(("mock", "mock-llama-3"))

        return valid

    @staticmethod
    def apply_strategy(
        candidates: List[Tuple[str, str]],
        strategy: Strategy,
        category: TaskCategory,
        input_tokens: int
    ) -> List[Tuple[str, str]]:
        """
        Orders or selects candidates based on the requested strategy.
        """
        if strategy == Strategy.CHEAPEST:
            return sorted(
                candidates,
                key=lambda item: CostCalculator.estimate_cost(input_tokens, 200, item[1])
            )
        elif strategy == Strategy.FASTEST:
            # Fast latency models prioritized
            fast_priority = ["mock-gemini-1.5-flash", "gemini-1.5-flash", "gpt-4o-mini", "claude-3-5-haiku"]
            return sorted(
                candidates,
                key=lambda item: 0 if item[1] in fast_priority else 1
            )
        return candidates
