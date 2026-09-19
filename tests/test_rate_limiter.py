"""
Tests for Dual-Dimension Async Token Bucket Rate Limiter (Module 4)
"""

import pytest
import asyncio
from arbiter.providers.rate_limiter import DualDimensionRateLimiter, TokenBucket


@pytest.mark.asyncio
async def test_token_bucket_burst_and_drain():
    bucket = TokenBucket(capacity=5.0, refill_rate_per_sec=2.0)
    # Burst 5 tokens immediately
    ok = await bucket.acquire(5.0, timeout=0.1)
    assert ok is True

    # Immediate next token should fail if timeout is tiny
    ok_drain = await bucket.acquire(1.0, timeout=0.05)
    assert ok_drain is False

    # Wait 0.6 sec for refill (at 2 tok/sec => ~1.2 tokens)
    await asyncio.sleep(0.6)
    ok_refilled = await bucket.acquire(1.0, timeout=0.1)
    assert ok_refilled is True


@pytest.mark.asyncio
async def test_dual_dimension_rpm_tpm():
    limiter = DualDimensionRateLimiter(rpm=60, tpm=1000)
    # Acquire small tokens
    ok = await limiter.acquire(estimated_tokens=50, timeout=0.5)
    assert ok is True

    # Utilization should be positive
    assert limiter.rpm_utilization > 0.0
    assert limiter.tpm_utilization > 0.0


@pytest.mark.asyncio
async def test_rate_limiter_429_backoff():
    bucket = TokenBucket(capacity=10.0, refill_rate_per_sec=10.0)
    await bucket.trigger_backoff(seconds=0.4)

    # Should be locked out during backoff
    ok = await bucket.acquire(1.0, timeout=0.1)
    assert ok is False

    # Wait for backoff to expire
    await asyncio.sleep(0.45)
    ok_after = await bucket.acquire(1.0, timeout=0.5)
    assert ok_after is True
