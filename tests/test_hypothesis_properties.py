"""
Property-based tests using Hypothesis for MAB and Rate Limiter invariants.
"""

import pytest
import math
from hypothesis import given, strategies as st
from arbiter.router.mab import BanditArm
from arbiter.providers.rate_limiter import TokenBucket


@given(
    alpha=st.floats(min_value=1.0, max_value=100.0),
    beta=st.floats(min_value=1.0, max_value=100.0),
    half_life=st.floats(min_value=1.0, max_value=200.0),
    hours_elapsed=st.floats(min_value=0.0, max_value=1000.0)
)
def test_property_mab_decay_invariants(alpha, beta, half_life, hours_elapsed):
    """
    Invariant: Exponential decay must always keep alpha and beta >= 1.0,
    and decay must monotonically move values towards 1.0 (uninformed prior).
    """
    arm = BanditArm(
        provider="mock",
        model="m",
        task_category="cat",
        alpha=alpha,
        beta=beta
    )
    arm.last_updated -= hours_elapsed * 3600.0
    arm.apply_decay(half_life_hours=half_life)

    assert arm.alpha >= 1.0
    assert arm.beta >= 1.0

    if alpha > 1.0:
        assert arm.alpha <= alpha
    if beta > 1.0:
        assert arm.beta <= beta

    # Expected value must remain bounded in [0, 1]
    assert 0.0 <= arm.expected_value <= 1.0


@given(
    capacity=st.floats(min_value=1.0, max_value=1000.0),
    refill_rate=st.floats(min_value=0.1, max_value=100.0)
)
def test_property_token_bucket_capacity_bound(capacity, refill_rate):
    """
    Invariant: Bucket tokens must never exceed its burst capacity.
    """
    bucket = TokenBucket(capacity=capacity, refill_rate_per_sec=refill_rate)
    bucket._refill()
    assert bucket.tokens <= bucket.capacity
    assert 0.0 <= bucket.utilization <= 1.0
