"""
Tests for Multi-Armed Bandit (MAB) and Router Engine (Module 3)
"""

import pytest
from arbiter.models.types import TaskCategory, Strategy
from arbiter.models.schemas import ChatMessage
from arbiter.router.mab import BanditArm, MABEngine
from arbiter.router.constraints import ConstraintSolver
from arbiter.router.engine import router


@pytest.mark.asyncio
async def test_bandit_arm_updates():
    arm = BanditArm(provider="mock", model="m1", task_category="code_generation", alpha=1.0, beta=1.0)
    initial_exp = arm.expected_value
    assert initial_exp == 0.5

    # Positive update (+1.0 reward)
    await arm.update(reward=1.0, weight=2.0)
    assert arm.alpha == 3.0
    assert arm.beta == 1.0
    assert arm.expected_value == 3.0 / 4.0

    # Negative update (0.0 reward)
    await arm.update(reward=0.0, weight=2.0)
    assert arm.alpha == 3.0
    assert arm.beta == 3.0
    assert arm.expected_value == 0.5


def test_bandit_arm_decay():
    arm = BanditArm(provider="mock", model="m1", task_category="code_generation", alpha=10.0, beta=10.0)
    # Simulate time passing (e.g. 72 hours with half_life=72.0)
    arm.last_updated -= 72 * 3600
    arm.apply_decay(half_life_hours=72.0)

    # Values should decay halfway back to 1.0: (10-1)*0.5 + 1 = 5.5
    assert 5.4 <= arm.alpha <= 5.6
    assert 5.4 <= arm.beta <= 5.6


@pytest.mark.asyncio
async def test_constraint_solver_budget():
    candidates = [
        ("openai", "gpt-4-turbo"),      # High cost
        ("mock", "mock-llama-3")        # Very low cost
    ]
    # Restrict budget to $0.0001
    filtered = await ConstraintSolver.filter_candidates(
        candidates,
        estimated_input_tokens=500,
        budget_limit=0.0001
    )
    models = [m for _, m in filtered]
    assert "mock-llama-3" in models
    assert "gpt-4-turbo" not in models


@pytest.mark.asyncio
async def test_router_engine_decision():
    msgs = [ChatMessage(role="user", content="напиши функцию поиска")]
    decision = await router.route_request(
        messages=msgs,
        category=TaskCategory.CODE_GENERATION,
        strategy=Strategy.AUTO
    )

    assert decision.selected_provider is not None
    assert decision.selected_model is not None
    assert decision.category == TaskCategory.CODE_GENERATION
    assert decision.estimated_cost >= 0.0
