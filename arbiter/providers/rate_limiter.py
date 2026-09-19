"""
ARBITER Async Token Bucket Rate Limiter (Module 4)
Supports dual-dimension limits (RPM and TPM), burst capacity, and exponential backoff on 429.
"""

import time
import asyncio
import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    Asynchronous Token Bucket implementation supporting burst and smooth refill.
    """

    def __init__(self, capacity: float, refill_rate_per_sec: float):
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.refill_rate = float(refill_rate_per_sec)
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
        self._backoff_until = 0.0

    def _refill(self) -> None:
        now = time.monotonic()
        if now < self._backoff_until:
            return  # In backoff period, no refill

        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_update = now

    async def acquire(self, amount: float = 1.0, timeout: float = 10.0) -> bool:
        start_time = time.monotonic()
        while True:
            async with self._lock:
                now = time.monotonic()
                if now < self._backoff_until:
                    sleep_time = self._backoff_until - now
                else:
                    self._refill()
                    if self.tokens >= amount:
                        self.tokens -= amount
                        return True
                    deficit = amount - self.tokens
                    sleep_time = deficit / max(self.refill_rate, 0.001)

            if (time.monotonic() - start_time) + sleep_time > timeout:
                return False

            await asyncio.sleep(min(sleep_time, 0.5))

    async def trigger_backoff(self, seconds: float = 5.0) -> None:
        async with self._lock:
            self._backoff_until = max(self._backoff_until, time.monotonic() + seconds)
            self.tokens = 0.0  # Temporarily drain bucket
            logger.warning(f"RateLimiter backoff triggered for {seconds}s")

    @property
    def utilization(self) -> float:
        """Returns 0.0 (empty) to 1.0 (fully utilized/exhausted bucket)."""
        self._refill()
        return max(0.0, min(1.0, 1.0 - (self.tokens / max(self.capacity, 1.0))))


class DualDimensionRateLimiter:
    """
    Separates Requests-Per-Minute (RPM) and Tokens-Per-Minute (TPM) per provider/model.
    """

    def __init__(
        self,
        rpm: int = 60,
        tpm: int = 40_000,
        rpm_burst_multiplier: float = 1.5,
        tpm_burst_multiplier: float = 1.2
    ):
        self.rpm = rpm
        self.tpm = tpm
        self.request_bucket = TokenBucket(
            capacity=rpm * rpm_burst_multiplier,
            refill_rate_per_sec=rpm / 60.0
        )
        self.token_bucket = TokenBucket(
            capacity=tpm * tpm_burst_multiplier,
            refill_rate_per_sec=tpm / 60.0
        )

    async def acquire(self, estimated_tokens: int, timeout: float = 10.0) -> bool:
        # Acquire 1 request slot
        req_ok = await self.request_bucket.acquire(1.0, timeout=timeout)
        if not req_ok:
            return False

        # Acquire token quota
        tok_ok = await self.token_bucket.acquire(float(estimated_tokens), timeout=timeout)
        if not tok_ok:
            # Return the 1 request slot back
            async with self.request_bucket._lock:
                self.request_bucket.tokens = min(
                    self.request_bucket.capacity,
                    self.request_bucket.tokens + 1.0
                )
            return False

        return True

    async def record_429(self, backoff_seconds: float = 5.0) -> None:
        await self.request_bucket.trigger_backoff(backoff_seconds)
        await self.token_bucket.trigger_backoff(backoff_seconds)

    @property
    def rpm_utilization(self) -> float:
        return self.request_bucket.utilization

    @property
    def tpm_utilization(self) -> float:
        return self.token_bucket.utilization
