"""
Unit Tests: server.mcp_server.config

Big Tech L11급 Config 테스트.

Test Coverage:
- Config 값 검증
- ENUM vs String 변환
- Tier 별 설정
- Edge cases (invalid tier, boundary values)
- Type safety
"""

import pytest

from apps.mcp.mcp.config import (
    CostHint,
    Tier,
    get_context_config,
    get_job_config,
    get_preview_config,
    get_search_config,
    get_slice_config,
    get_tier_config,
    get_verify_config,
)

# ============================================================
# Tier Config Tests
# ============================================================


class TestTierConfig:
    """Tier configuration 테스트."""

    def test_get_tier_config_tier_0_int(self):
        """Tier 0 (int) 설정 조회."""
        config = get_tier_config(0)

        assert config.tier == Tier.TIER_0
        assert config.timeout_seconds == 2.0
        assert config.cost_hint == CostHint.LOW
        assert config.max_limit == 100
        assert config.requires_approval is False

    def test_get_tier_config_tier_0_enum(self):
        """Tier 0 (enum) 설정 조회."""
        config = get_tier_config(Tier.TIER_0)

        assert config.tier == Tier.TIER_0
        assert config.timeout_seconds == 2.0

    def test_get_tier_config_tier_1(self):
        """Tier 1 설정 조회."""
        config = get_tier_config(1)

        assert config.tier == Tier.TIER_1
        assert config.timeout_seconds == 10.0
        assert config.cost_hint == CostHint.MEDIUM
        assert config.max_limit == 500

    def test_get_tier_config_tier_2(self):
        """Tier 2 설정 조회."""
        config = get_tier_config(2)

        assert config.tier == Tier.TIER_2
        assert config.timeout_seconds == 60.0
        assert config.cost_hint == CostHint.HIGH
        assert config.max_limit == 1000
        assert config.requires_approval is True

    def test_get_tier_config_invalid_tier_raises_valueerror(self):
        """Invalid tier는 ValueError."""
        with pytest.raises(ValueError, match="Invalid tier: 3"):
            get_tier_config(3)

    def test_get_tier_config_negative_tier_raises_valueerror(self):
        """Negative tier는 ValueError."""
        with pytest.raises(ValueError, match="Invalid tier: -1"):
            get_tier_config(-1)

    def test_tier_config_to_meta_dict(self):
        """to_meta_dict() 변환 테스트."""
        config = get_tier_config(0)
        meta = config.to_meta_dict()

        assert meta["timeout_seconds"] == 2.0
        assert meta["cost_hint"] == "low"  # ENUM → String
        assert meta["tier"] == 0
        assert "requires_approval" not in meta  # False는 포함 안함

    def test_tier_config_to_meta_dict_with_took_ms(self):
        """to_meta_dict() with took_ms."""
        config = get_tier_config(0)
        meta = config.to_meta_dict(took_ms=150)

        assert meta["took_ms"] == 150

    def test_tier_config_to_meta_dict_tier_2_includes_approval(self):
        """Tier 2는 requires_approval 포함."""
        config = get_tier_config(2)
        meta = config.to_meta_dict()

        assert meta["requires_approval"] is True


# ============================================================
# Tool-Specific Config Tests
# ============================================================


class TestSearchToolConfig:
    """SearchToolConfig 테스트."""

    def test_search_config_defaults(self):
        """Default 값 확인."""
        config = get_search_config()

        assert config.chunk_timeout == 2.0
        assert config.symbol_timeout == 2.0
        assert config.max_limit == 100
        assert config.default_limit == 10

    def test_search_config_default_limit_within_max(self):
        """default_limit ≤ max_limit."""
        config = get_search_config()

        assert config.default_limit <= config.max_limit


class TestContextToolConfig:
    """ContextToolConfig 테스트."""

    def test_context_config_defaults(self):
        """Default 값 확인."""
        config = get_context_config()

        assert config.timeout_seconds == 3.0
        assert config.default_max_chars == 8000
        assert config.default_max_items == 20
        assert config.default_limit == 50
        assert config.reference_fetch_multiplier == 10

    def test_context_config_default_facets(self):
        """Default facets 확인."""
        config = get_context_config()

        assert config.default_facets == ["definition", "usages", "callers"]

    def test_context_config_multiplier_positive(self):
        """Multiplier는 양수."""
        config = get_context_config()

        assert config.reference_fetch_multiplier > 0


class TestJobToolConfig:
    """JobToolConfig 테스트."""

    def test_job_config_defaults(self):
        """Default 값 확인."""
        config = get_job_config()

        assert config.default_limit == 50

    def test_job_config_limit_positive(self):
        """Limit은 양수."""
        config = get_job_config()

        assert config.default_limit > 0


class TestPreviewToolConfig:
    """PreviewToolConfig 테스트."""

    def test_preview_config_defaults(self):
        """Default 값 확인."""
        config = get_preview_config()

        assert config.default_limit == 5
        assert config.default_top_k_callers == 20
        assert config.default_top_k_impact == 50
        assert config.fetch_multiplier == 2

    def test_preview_config_limits_ordered(self):
        """Preview limits 순서 확인."""
        config = get_preview_config()

        # Preview는 작은 limit
        assert config.default_limit < config.default_top_k_callers
        assert config.default_top_k_callers < config.default_top_k_impact

    def test_preview_config_multiplier_positive(self):
        """Multiplier는 양수."""
        config = get_preview_config()

        assert config.fetch_multiplier > 0


class TestSliceToolConfig:
    """SliceToolConfig 테스트."""

    def test_slice_config_defaults(self):
        """Default 값 확인."""
        config = get_slice_config()

        assert config.timeout_seconds == 5.0
        assert config.default_max_depth == 5
        assert config.default_max_lines == 100
        assert config.max_depth_limit == 10

    def test_slice_config_depth_within_limit(self):
        """default_max_depth ≤ max_depth_limit."""
        config = get_slice_config()

        assert config.default_max_depth <= config.max_depth_limit


class TestVerifyToolConfig:
    """VerifyToolConfig 테스트."""

    def test_verify_config_defaults(self):
        """Default 값 확인."""
        config = get_verify_config()

        assert config.compile_timeout == 10.0
        assert config.type_check_timeout == 30.0
        assert config.finding_verify_timeout == 30.0
        assert config.subprocess_timeout == 15.0

    def test_verify_config_timeouts_ordered(self):
        """Timeout 순서 확인 (compile < type_check)."""
        config = get_verify_config()

        assert config.compile_timeout < config.type_check_timeout
        assert config.subprocess_timeout < config.type_check_timeout


# ============================================================
# ENUM Tests (Type Safety)
# ============================================================


class TestEnums:
    """ENUM 타입 안정성 테스트."""

    def test_tier_enum_values(self):
        """Tier ENUM 값 확인."""
        assert Tier.TIER_0.value == 0
        assert Tier.TIER_1.value == 1
        assert Tier.TIER_2.value == 2

    def test_cost_hint_enum_values(self):
        """CostHint ENUM 값 확인 (외부는 String)."""
        assert CostHint.FREE.value == "free"
        assert CostHint.LOW.value == "low"
        assert CostHint.MEDIUM.value == "medium"
        assert CostHint.HIGH.value == "high"
        assert CostHint.VERY_HIGH.value == "very_high"

    def test_tier_enum_comparison(self):
        """Tier ENUM 비교."""
        assert Tier.TIER_0 != Tier.TIER_1
        assert Tier.TIER_1 != Tier.TIER_2

    def test_cost_hint_enum_comparison(self):
        """CostHint ENUM 비교."""
        assert CostHint.LOW != CostHint.MEDIUM
        assert CostHint.MEDIUM != CostHint.HIGH


# ============================================================
# Edge Cases
# ============================================================


class TestEdgeCases:
    """Edge case 테스트."""

    def test_tier_config_boundary_tier_0_max_limit(self):
        """Tier 0 max_limit 경계값."""
        config = get_tier_config(0)

        # Tier 0는 low cost이므로 limit 작음
        assert config.max_limit < get_tier_config(1).max_limit

    def test_tier_config_boundary_tier_2_max_limit(self):
        """Tier 2 max_limit 최대값."""
        config = get_tier_config(2)

        # Tier 2는 high cost이므로 limit 큼
        assert config.max_limit >= 1000

    def test_config_frozen_immutable(self):
        """Config는 frozen (불변)."""
        config = get_search_config()

        with pytest.raises(Exception):  # FrozenInstanceError
            config.default_limit = 999  # type: ignore

    def test_all_configs_callable(self):
        """모든 config factory 호출 가능."""
        configs = [
            get_search_config(),
            get_context_config(),
            get_job_config(),
            get_preview_config(),
            get_slice_config(),
            get_verify_config(),
        ]

        assert all(c is not None for c in configs)
