"""
Tests for Circuit Breaker State Transitions (Module 4)
"""

import pytest
import asyncio
from arbiter.providers.circuit_breaker import CircuitBreaker
from arbiter.models.types import CircuitState


@pytest.mark.asyncio
async def test_circuit_breaker_flow():
    cb = CircuitBreaker(
        provider_name="test_provider",
        failure_threshold=3,
        recovery_time_seconds=0.3,
        time_window_seconds=10.0
    )

    # Initial state
    assert cb.state == CircuitState.CLOSED
    assert await cb.can_execute() is True

    # Record 2 failures (threshold is 3)
    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    # 3rd failure trips the circuit
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert await cb.can_execute() is False

    # Wait for recovery window (0.3s)
    await asyncio.sleep(0.35)
    assert cb.state == CircuitState.HALF_OPEN

    # First caller in HALF_OPEN gets a trial slot
    assert await cb.can_execute() is True
    # Subsequent caller in HALF_OPEN is blocked while trial is inflight
    assert await cb.can_execute() is False

    # Successful trial closes circuit
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert await cb.can_execute() is True
