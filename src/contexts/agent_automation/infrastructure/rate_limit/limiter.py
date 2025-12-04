"""Rate Limiter using asyncio primitives."""

import asyncio
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from src.infra.observability import get_logger

from .config import ProviderQuota, RateLimitConfig

logger = get_logger(__name__)


class RateLimiter:
    """Per-provider rate limiter with concurrent request limiting.

    Enforces:
    - Maximum concurrent requests (Semaphore)
    - Maximum RPM (requests per minute)
    - Maximum TPM (tokens per minute)
    """

    def __init__(self, provider: str = "default", quota: ProviderQuota | None = None):
        """Initialize rate limiter.

        Args:
            provider: Provider name
            quota: Custom quota (default: from config)
        """
        self.provider = provider
        self.quota = quota or RateLimitConfig.get_quota(provider)

        # Semaphore for concurrent requests
        self.semaphore = asyncio.Semaphore(self.quota.max_concurrent)

        # Sliding window for RPM tracking
        self.request_times: deque[float] = deque(maxlen=self.quota.max_rpm)

        # Token usage tracking
        self.token_times: deque[tuple[float, int]] = deque(maxlen=1000)

        self._lock = asyncio.Lock()

    async def execute(self, fn: Callable, estimated_tokens: int = 1000) -> Any:
        """Execute function with rate limiting.

        Args:
            fn: Async function to execute
            estimated_tokens: Estimated token usage

        Returns:
            Function result
        """
        # Wait for concurrent slot
        async with self.semaphore:
            # Wait for RPM limit
            await self._wait_for_rpm()

            # Wait for TPM limit
            await self._wait_for_tpm(estimated_tokens)

            # Record request
            async with self._lock:
                now = time.time()
                self.request_times.append(now)
                self.token_times.append((now, estimated_tokens))

            logger.debug(
                "rate_limited_execution",
                provider=self.provider,
                estimated_tokens=estimated_tokens,
            )

            # Execute
            return await fn()

    async def _wait_for_rpm(self) -> None:
        """Wait if RPM limit would be exceeded."""
        async with self._lock:
            if len(self.request_times) >= self.quota.max_rpm:
                # Check oldest request
                oldest = self.request_times[0]
                elapsed = time.time() - oldest

                if elapsed < 60:
                    # Need to wait
                    wait_time = 60 - elapsed
                    logger.warning(
                        "rpm_limit_reached",
                        provider=self.provider,
                        wait_seconds=wait_time,
                    )

                    # Release lock before sleeping
                    pass

        # Sleep outside lock
        if len(self.request_times) >= self.quota.max_rpm:
            oldest = self.request_times[0]
            elapsed = time.time() - oldest
            if elapsed < 60:
                await asyncio.sleep(60 - elapsed + 0.1)

    async def _wait_for_tpm(self, estimated_tokens: int) -> None:
        """Wait if TPM limit would be exceeded.

        Args:
            estimated_tokens: Tokens for this request
        """
        async with self._lock:
            # Calculate tokens in last minute
            now = time.time()
            cutoff = now - 60

            recent_tokens = sum(tokens for ts, tokens in self.token_times if ts > cutoff)

            if recent_tokens + estimated_tokens > self.quota.max_tpm:
                # Need to wait
                if self.token_times:
                    oldest_ts = self.token_times[0][0]
                    wait_time = 60 - (now - oldest_ts)

                    if wait_time > 0:
                        logger.warning(
                            "tpm_limit_reached",
                            provider=self.provider,
                            wait_seconds=wait_time,
                        )

                        # Sleep outside lock
                        pass

        # Sleep if needed
        if recent_tokens + estimated_tokens > self.quota.max_tpm:
            if self.token_times:
                oldest_ts = self.token_times[0][0]
                wait_time = 60 - (time.time() - oldest_ts)
                if wait_time > 0:
                    await asyncio.sleep(wait_time + 0.1)

    def get_stats(self) -> dict:
        """Get rate limiter statistics.

        Returns:
            Stats dict
        """
        now = time.time()
        cutoff = now - 60

        recent_requests = sum(1 for ts in self.request_times if ts > cutoff)
        recent_tokens = sum(tokens for ts, tokens in self.token_times if ts > cutoff)

        return {
            "provider": self.provider,
            "concurrent_limit": self.quota.max_concurrent,
            "rpm_limit": self.quota.max_rpm,
            "tpm_limit": self.quota.max_tpm,
            "recent_rpm": recent_requests,
            "recent_tpm": recent_tokens,
            "rpm_utilization_pct": (recent_requests / self.quota.max_rpm * 100),
            "tpm_utilization_pct": (recent_tokens / self.quota.max_tpm * 100),
        }
