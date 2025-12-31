"""
MCP Server Configuration

RFC-053 Tier-based tool configuration.

Usage:
    from apps.mcp.mcp.config import get_tier_config

    config = get_tier_config(tier=0)
    await asyncio.wait_for(operation(), timeout=config.timeout_seconds)
"""

from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    """
    Tool tier classification (RFC-053).

    Values:
        TIER_0: Primary entry points (1-2s, low cost)
        TIER_1: Detailed analysis (5-10s, medium cost)
        TIER_2: Heavy/async operations (30s+, high cost)
    """

    TIER_0 = 0
    TIER_1 = 1
    TIER_2 = 2


class CostHint(Enum):
    """
    Cost classification for tools.

    Values:
        FREE: No cost (status queries)
        LOW: < 1 token/request
        MEDIUM: 1-10 tokens/request
        HIGH: 10-100 tokens/request
        VERY_HIGH: > 100 tokens/request
    """

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


@dataclass(frozen=True)
class TierConfig:
    """
    Configuration for a specific tier.

    Attributes:
        tier: Tier enum
        timeout_seconds: Maximum execution time
        cost_hint: Cost classification
        max_limit: Maximum result limit
        requires_approval: Whether to require explicit approval
    """

    tier: Tier
    timeout_seconds: float
    cost_hint: CostHint
    max_limit: int
    requires_approval: bool = False

    def to_meta_dict(self, took_ms: int | None = None) -> dict:
        """
        Convert to meta dict for JSON response.

        Args:
            took_ms: Actual execution time in milliseconds

        Returns:
            Meta dict suitable for tool responses
        """
        result = {
            "timeout_seconds": self.timeout_seconds,
            "cost_hint": self.cost_hint.value,  # ENUM → String
            "tier": self.tier.value,
        }

        if took_ms is not None:
            result["took_ms"] = took_ms

        if self.requires_approval:
            result["requires_approval"] = True

        return result


# ============================================================
# Tier Configurations (Constants)
# ============================================================


TIER_0_CONFIG = TierConfig(
    tier=Tier.TIER_0,
    timeout_seconds=2.0,
    cost_hint=CostHint.LOW,
    max_limit=100,
    requires_approval=False,
)

TIER_1_CONFIG = TierConfig(
    tier=Tier.TIER_1,
    timeout_seconds=10.0,
    cost_hint=CostHint.MEDIUM,
    max_limit=500,
    requires_approval=False,
)

TIER_2_CONFIG = TierConfig(
    tier=Tier.TIER_2,
    timeout_seconds=60.0,
    cost_hint=CostHint.HIGH,
    max_limit=1000,
    requires_approval=True,
)


# ============================================================
# Tool-Specific Configurations
# ============================================================


@dataclass(frozen=True)
class SearchToolConfig:
    """
    Configuration for search tool.

    Attributes:
        chunk_timeout: Timeout for chunk search
        symbol_timeout: Timeout for symbol search
        max_limit: Maximum result limit
        default_limit: Default limit if not specified
    """

    chunk_timeout: float = 2.0
    symbol_timeout: float = 2.0
    max_limit: int = 100
    default_limit: int = 10


@dataclass(frozen=True)
class ContextToolConfig:
    """
    Configuration for get_context tool.

    Attributes:
        timeout_seconds: Total timeout
        default_max_chars: Default character budget
        default_max_items: Default item budget
        default_limit: Default result limit
        reference_fetch_multiplier: Multiplier for fetching references
        default_facets: Default facets to retrieve
    """

    timeout_seconds: float = 3.0
    default_max_chars: int = 8000
    default_max_items: int = 20
    default_limit: int = 50
    reference_fetch_multiplier: int = 10
    default_facets: list[str] = None  # type: ignore

    def __post_init__(self):
        if self.default_facets is None:
            object.__setattr__(self, "default_facets", ["definition", "usages", "callers"])


@dataclass(frozen=True)
class SliceToolConfig:
    """
    Configuration for graph_slice tool.

    Attributes:
        timeout_seconds: Maximum execution time
        default_max_depth: Default slice depth
        default_max_lines: Default line limit
        max_depth_limit: Absolute maximum depth
    """

    timeout_seconds: float = 5.0
    default_max_depth: int = 5
    default_max_lines: int = 100
    max_depth_limit: int = 10


@dataclass(frozen=True)
class VerifyToolConfig:
    """
    Configuration for verification tools (Tier 1).

    Attributes:
        compile_timeout: Timeout for compilation check
        type_check_timeout: Timeout for type checking
        finding_verify_timeout: Timeout for finding verification
        subprocess_timeout: Timeout for subprocess execution
    """

    compile_timeout: float = 10.0
    type_check_timeout: float = 30.0
    finding_verify_timeout: float = 30.0
    subprocess_timeout: float = 15.0


@dataclass(frozen=True)
class JobToolConfig:
    """
    Configuration for job management tools.

    Attributes:
        default_limit: Default limit for job result pagination
    """

    default_limit: int = 50


@dataclass(frozen=True)
class PreviewToolConfig:
    """
    Configuration for preview tools (Tier 1).

    Attributes:
        default_limit: Default limit for preview results
        default_top_k_callers: Default top_k for preview_callers
        default_top_k_impact: Default top_k for preview_impact
        fetch_multiplier: Multiplier for fetching more results to estimate total
    """

    default_limit: int = 5
    default_top_k_callers: int = 20
    default_top_k_impact: int = 50
    fetch_multiplier: int = 2


# ============================================================
# Factory Functions
# ============================================================


def get_tier_config(tier: int | Tier) -> TierConfig:
    """
    Get configuration for a specific tier.

    Args:
        tier: Tier number (0, 1, 2) or Tier enum

    Returns:
        TierConfig instance

    Raises:
        ValueError: If tier is invalid

    Example:
        config = get_tier_config(0)
        timeout = config.timeout_seconds
    """
    if isinstance(tier, int):
        try:
            tier = Tier(tier)
        except ValueError:
            raise ValueError(f"Invalid tier: {tier}. Must be 0, 1, or 2")

    if tier == Tier.TIER_0:
        return TIER_0_CONFIG
    elif tier == Tier.TIER_1:
        return TIER_1_CONFIG
    elif tier == Tier.TIER_2:
        return TIER_2_CONFIG
    else:
        raise ValueError(f"Invalid tier: {tier}")


def get_search_config() -> SearchToolConfig:
    """Get search tool configuration."""
    return SearchToolConfig()


def get_context_config() -> ContextToolConfig:
    """Get context tool configuration."""
    return ContextToolConfig()


def get_slice_config() -> SliceToolConfig:
    """Get slice tool configuration."""
    return SliceToolConfig()


def get_verify_config() -> VerifyToolConfig:
    """Get verify tool configuration."""
    return VerifyToolConfig()


def get_job_config() -> JobToolConfig:
    """Get job tool configuration."""
    return JobToolConfig()


def get_preview_config() -> PreviewToolConfig:
    """Get preview tool configuration."""
    return PreviewToolConfig()


@dataclass(frozen=True)
class IndexStatusCacheConfig:
    """
    Configuration for index status cache.

    Big Tech L11: 상태별 다른 TTL + STALE 감지.

    Attributes:
        ttl_completed: COMPLETED 상태 TTL (초)
        ttl_in_progress: IN_PROGRESS 상태 TTL (초, 짧게 = 빠른 재체크)
        ttl_not_found: NOT_FOUND 상태 TTL (초)
        indexing_timeout: 인덱싱 타임아웃 (초, STALE 감지용)
        l1_maxsize: L1 캐시 최대 크기
    """

    ttl_completed: int = 1800  # 30분 (안정적)
    ttl_in_progress: int = 60  # 1분 (빠른 재체크)
    ttl_not_found: int = 300  # 5분
    indexing_timeout: int = 1800  # 30분 (STALE 감지)
    l1_maxsize: int = 100


def get_index_status_cache_config() -> IndexStatusCacheConfig:
    """Get index status cache configuration."""
    return IndexStatusCacheConfig()
