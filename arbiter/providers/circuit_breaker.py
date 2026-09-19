"""
ARBITER Circuit Breaker (Module 4)
States: CLOSED -> OPEN -> HALF_OPEN -> CLOSED
"""

import time
import asyncio
import logging
from typing import List
from arbiter.models.types import CircuitState

logger = logging.getLogger(__name__)


class CircuitBreakerOpenException(Exception):
    pass


class CircuitBreaker:
    """
    Protects downstream providers against cascade failures.
    """

    def __init__(
        self,
        provider_name: str,
        failure_threshold: int = 5,
        recovery_time_seconds: float = 30.0,
        time_window_seconds: float = 60.0
    ):
        self.provider_name = provider_name
        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds
        self.time_window_seconds = time_window_seconds

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_timestamps: List[float] = []
        self._last_state_change: float = time.monotonic()
        self._half_open_test_inflight: bool = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        now = time.monotonic()
        if self._state == CircuitState.OPEN:
            if now - self._last_state_change >= self.recovery_time_seconds:
                return CircuitState.HALF_OPEN
        return self._state

    async def can_execute(self) -> bool:
        """
        Determines whether a call can proceed or should be fast-failed.
        """
        async with self._lock:
            current = self.state
            if current == CircuitState.CLOSED:
                return True
            elif current == CircuitState.HALF_OPEN:
                if not self._half_open_test_inflight:
                    self._half_open_test_inflight = True
                    return True
                return False  # Wait for single trial call to finish
            else:  # OPEN
                return False

    async def record_success(self) -> None:
        async with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info(f"CircuitBreaker for '{self.provider_name}' recovered: HALF_OPEN -> CLOSED")
                self._state = CircuitState.CLOSED
                self._last_state_change = time.monotonic()
                self._failure_timestamps.clear()
            self._half_open_test_inflight = False

    async def record_failure(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._half_open_test_inflight = False

            if self._state == CircuitState.HALF_OPEN:
                # Immediate trip back to OPEN
                logger.warning(f"Trial failed for '{self.provider_name}': HALF_OPEN -> OPEN")
                self._state = CircuitState.OPEN
                self._last_state_change = now
                return

            # Filter old failures outside time window
            cutoff = now - self.time_window_seconds
            self._failure_timestamps = [t for t in self._failure_timestamps if t > cutoff]
            self._failure_timestamps.append(now)

            if len(self._failure_timestamps) >= self.failure_threshold:
                logger.error(
                    f"Failure threshold ({self.failure_threshold}) reached for '{self.provider_name}'. "
                    f"Tripping circuit: CLOSED -> OPEN for {self.recovery_time_seconds}s"
                )
                self._state = CircuitState.OPEN
                self._last_state_change = now
