"""
ARBITER Stream Multiplexer for Consensus Mode (Module 4)
Runs N providers in parallel with adaptive latency timeouts and buffers completed candidates for merging.
"""

import time
import asyncio
import logging
from typing import List, Dict, Any, Tuple, Optional, Union, AsyncIterator
from arbiter.providers.base import BaseProvider
from arbiter.models.schemas import (
    ChatMessage,
    ChatCompletionResponse,
    ChatCompletionChunk,
    UsageInfo,
    ChatCompletionResponseChoice
)

logger = logging.getLogger(__name__)


class CandidateResult:
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        self.text: str = ""
        self.latency_ms: int = 0
        self.usage: Optional[UsageInfo] = None
        self.error: Optional[str] = None
        self.is_finished: bool = False


class StreamMultiplexer:
    """
    Manages parallel queries across N providers for Consensus mode.
    Implements adaptive timeout: once the fastest candidate finishes,
    subsequent candidates receive a bounded grace period.
    """

    def __init__(
        self,
        min_timeout: float = 3.0,
        max_timeout: float = 20.0,
        grace_multiplier: float = 1.8
    ):
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        self.grace_multiplier = grace_multiplier

    async def execute_consensus(
        self,
        targets: List[Tuple[BaseProvider, str]],
        messages: List[ChatMessage],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> List[CandidateResult]:
        """
        Queries all target (provider, model) pairs in parallel.
        Returns a list of successfully completed CandidateResult objects.
        """
        tasks = []
        candidates = [CandidateResult(p.name, m) for p, m in targets]

        for (provider, model), cand in zip(targets, candidates):
            tasks.append(
                asyncio.create_task(
                    self._query_candidate(provider, model, messages, temperature, max_tokens, cand)
                )
            )

        start_time = time.monotonic()
        fastest_time: Optional[float] = None
        cutoff_time = start_time + self.max_timeout

        # Monitor tasks completion with adaptive timeout
        pending = set(tasks)
        while pending and time.monotonic() < cutoff_time:
            done, pending = await asyncio.wait(
                pending,
                timeout=0.1,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Check if at least one candidate succeeded
            if fastest_time is None:
                for cand in candidates:
                    if cand.is_finished and not cand.error:
                        fastest_time = time.monotonic() - start_time
                        # Compute adaptive cutoff
                        adaptive_deadline = start_time + max(
                            self.min_timeout,
                            min(self.max_timeout, fastest_time * self.grace_multiplier)
                        )
                        cutoff_time = min(cutoff_time, adaptive_deadline)
                        logger.info(
                            f"Fastest candidate '{cand.model}' finished in {fastest_time:.2f}s. "
                            f"Adaptive consensus deadline set to {cutoff_time - start_time:.2f}s"
                        )
                        break

        # Cancel any stragglers exceeding adaptive timeout
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        successful = [c for c in candidates if c.is_finished and not c.error and len(c.text.strip()) > 0]
        logger.info(f"Consensus multiplexer completed: {len(successful)}/{len(targets)} candidates succeeded.")
        return successful

    async def _query_candidate(
        self,
        provider: BaseProvider,
        model: str,
        messages: List[ChatMessage],
        temperature: float,
        max_tokens: Optional[int],
        cand: CandidateResult
    ) -> None:
        start = time.monotonic()
        try:
            resp = await provider.complete(
                messages=messages,
                model=model,
                stream=False,
                temperature=temperature,
                max_tokens=max_tokens
            )
            cand.latency_ms = int((time.monotonic() - start) * 1000)
            if isinstance(resp, ChatCompletionResponse):
                if resp.choices:
                    cand.text = str(resp.choices[0].message.content)
                cand.usage = resp.usage
                cand.is_finished = True
        except asyncio.CancelledError:
            cand.error = "Timeout / cancelled by adaptive cutoff"
            cand.latency_ms = int((time.monotonic() - start) * 1000)
            raise
        except Exception as e:
            cand.error = str(e)
            cand.latency_ms = int((time.monotonic() - start) * 1000)
            logger.warning(f"Candidate {cand.provider}/{cand.model} failed: {e}")
