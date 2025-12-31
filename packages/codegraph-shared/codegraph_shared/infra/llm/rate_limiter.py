"""
Rate Limiter

Token bucket 알고리즘 기반 rate limiting.
Phase 2 Day 19-20: LLM/임베딩 API 호출 제한
"""

import asyncio
import time
from dataclasses import dataclass, field

from codegraph_shared.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class TokenBucket:
    """
    Token bucket for rate limiting.

    Algorithm:
    - Bucket holds tokens (max: capacity)
    - Tokens refill at rate tokens_per_second
    - Each request consumes tokens
    - If not enough tokens, wait until refilled
    """

    capacity: int
    tokens_per_second: float
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self):
        """Initialize bucket full."""
        self.tokens = float(self.capacity)
        self.last_refill = time.time()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        # Add tokens
        tokens_to_add = elapsed * self.tokens_per_second
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    async def acquire(self, tokens: int = 1) -> None:
        """
        Acquire tokens (wait if not available).

        Args:
            tokens: Number of tokens to consume
        """
        while True:
            self._refill()

            if self.tokens >= tokens:
                self.tokens -= tokens
                return

            # Not enough tokens, wait for refill
            tokens_needed = tokens - self.tokens
            wait_time = tokens_needed / self.tokens_per_second

            logger.debug(
                "rate_limit_waiting",
                tokens_needed=tokens_needed,
                wait_time_seconds=wait_time,
            )

            await asyncio.sleep(wait_time)

    def try_acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens (non-blocking).

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if acquired, False if not enough tokens
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False


class RateLimiter:
    """
    Rate limiter with per-tenant and per-model limits.

    Features:
    - Global rate limit (all tenants)
    - Per-tenant rate limit
    - Per-model rate limit
    - Concurrency control (max concurrent requests)
    """

    def __init__(
        self,
        # Global limits
        global_tokens_per_minute: int = 10000,
        global_max_concurrent: int = 10,
        # Per-tenant limits
        tenant_tokens_per_minute: int = 1000,
        # Per-model limits (optional)
        model_tokens_per_minute: dict[str, int] | None = None,
    ):
        """
        Initialize rate limiter.

        Args:
            global_tokens_per_minute: Global token limit per minute
            global_max_concurrent: Maximum concurrent requests
            tenant_tokens_per_minute: Per-tenant token limit per minute
            model_tokens_per_minute: Per-model token limits (optional)
        """
        # Global bucket
        self.global_bucket = TokenBucket(
            capacity=global_tokens_per_minute,
            tokens_per_second=global_tokens_per_minute / 60.0,
        )

        # Global concurrency semaphore
        self.global_semaphore = asyncio.Semaphore(global_max_concurrent)

        # Per-tenant buckets
        self.tenant_buckets: dict[str, TokenBucket] = {}
        self.tenant_tokens_per_minute = tenant_tokens_per_minute

        # Per-model buckets
        self.model_buckets: dict[str, TokenBucket] = {}
        self.model_tokens_per_minute = model_tokens_per_minute or {}

        # Create model buckets from config
        for model, limit in self.model_tokens_per_minute.items():
            self.model_buckets[model] = TokenBucket(
                capacity=limit,
                tokens_per_second=limit / 60.0,
            )

    async def acquire(
        self,
        tokens: int,
        tenant_id: str | None = None,
        model: str | None = None,
    ) -> None:
        """
        Acquire tokens (wait if rate limit exceeded).

        Checks in order:
        1. Global concurrency limit
        2. Global token limit
        3. Tenant token limit (if tenant_id provided)
        4. Model token limit (if model provided)

        Args:
            tokens: Number of tokens to consume
            tenant_id: Optional tenant ID
            model: Optional model name
        """
        # 1. Global concurrency
        async with self.global_semaphore:
            # 2. Global token limit
            await self.global_bucket.acquire(tokens)

            # 3. Per-tenant limit
            if tenant_id:
                tenant_bucket = self._get_or_create_tenant_bucket(tenant_id)
                await tenant_bucket.acquire(tokens)

            # 4. Per-model limit
            if model and model in self.model_buckets:
                await self.model_buckets[model].acquire(tokens)

    def try_acquire(
        self,
        tokens: int,
        tenant_id: str | None = None,
        model: str | None = None,
    ) -> bool:
        """
        Try to acquire tokens (non-blocking).

        Args:
            tokens: Number of tokens to consume
            tenant_id: Optional tenant ID
            model: Optional model name

        Returns:
            True if acquired, False if rate limited
        """
        # Check global limit
        if not self.global_bucket.try_acquire(tokens):
            logger.debug("rate_limit_global", tokens=tokens)
            return False

        # Check tenant limit
        if tenant_id:
            tenant_bucket = self._get_or_create_tenant_bucket(tenant_id)
            if not tenant_bucket.try_acquire(tokens):
                logger.debug("rate_limit_tenant", tenant_id=tenant_id, tokens=tokens)
                # Refund global tokens
                self.global_bucket.tokens += tokens
                return False

        # Check model limit
        if model and model in self.model_buckets:
            if not self.model_buckets[model].try_acquire(tokens):
                logger.debug("rate_limit_model", model=model, tokens=tokens)
                # Refund tokens
                self.global_bucket.tokens += tokens
                if tenant_id:
                    tenant_bucket.tokens += tokens
                return False

        return True

    def _get_or_create_tenant_bucket(self, tenant_id: str) -> TokenBucket:
        """Get or create tenant bucket."""
        if tenant_id not in self.tenant_buckets:
            self.tenant_buckets[tenant_id] = TokenBucket(
                capacity=self.tenant_tokens_per_minute,
                tokens_per_second=self.tenant_tokens_per_minute / 60.0,
            )
        return self.tenant_buckets[tenant_id]

    def get_stats(self) -> dict:
        """Get rate limiter statistics."""
        return {
            "global": {
                "tokens_available": self.global_bucket.tokens,
                "capacity": self.global_bucket.capacity,
                "utilization_pct": (1 - self.global_bucket.tokens / self.global_bucket.capacity) * 100,
            },
            "tenants": {
                tenant_id: {
                    "tokens_available": bucket.tokens,
                    "capacity": bucket.capacity,
                }
                for tenant_id, bucket in self.tenant_buckets.items()
            },
            "models": {
                model: {
                    "tokens_available": bucket.tokens,
                    "capacity": bucket.capacity,
                }
                for model, bucket in self.model_buckets.items()
            },
        }


# Global rate limiter instance
_global_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create global rate limiter."""
    global _global_rate_limiter

    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter(
            global_tokens_per_minute=10000,
            global_max_concurrent=10,
            tenant_tokens_per_minute=1000,
            model_tokens_per_minute={
                "gpt-4": 500,  # Lower limit for expensive models
                "gpt-4o": 1000,
                "gpt-4o-mini": 5000,  # Higher limit for cheap models
            },
        )

    return _global_rate_limiter


def setup_rate_limiter(
    global_tokens_per_minute: int = 10000,
    global_max_concurrent: int = 10,
    tenant_tokens_per_minute: int = 1000,
    model_tokens_per_minute: dict[str, int] | None = None,
) -> RateLimiter:
    """Setup global rate limiter."""
    global _global_rate_limiter

    _global_rate_limiter = RateLimiter(
        global_tokens_per_minute=global_tokens_per_minute,
        global_max_concurrent=global_max_concurrent,
        tenant_tokens_per_minute=tenant_tokens_per_minute,
        model_tokens_per_minute=model_tokens_per_minute,
    )

    logger.info(
        "rate_limiter_setup",
        global_tokens_per_minute=global_tokens_per_minute,
        global_max_concurrent=global_max_concurrent,
        tenant_tokens_per_minute=tenant_tokens_per_minute,
    )

    return _global_rate_limiter
