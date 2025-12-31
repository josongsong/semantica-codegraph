"""
Reasoning Engine Domain Models Tests

Test Coverage:
- Hash-based impact analysis: SymbolHash, HashBasedImpactLevel, ImpactType
- Effect system: EffectType, EFFECT_HIERARCHY
- Edge cases: Validation, frozen dataclasses
"""

import pytest

from codegraph_engine.reasoning_engine.domain.models import (
    EFFECT_HIERARCHY,
    EffectType,
    HashBasedImpactLevel,
    ImpactType,
    SymbolHash,
)


class TestSymbolHash:
    """SymbolHash value object tests"""

    def test_create_symbol_hash(self):
        """Create symbol hash"""
        sh = SymbolHash(
            symbol_id="module.Class.method",
            signature_hash="abc123",
            body_hash="def456",
            impact_hash="ghi789",
        )
        assert sh.symbol_id == "module.Class.method"
        assert sh.signature_hash == "abc123"
        assert sh.body_hash == "def456"
        assert sh.impact_hash == "ghi789"

    def test_symbol_hash_immutable(self):
        """SymbolHash is frozen (immutable)"""
        sh = SymbolHash(
            symbol_id="test",
            signature_hash="a",
            body_hash="b",
            impact_hash="c",
        )
        with pytest.raises(AttributeError):
            sh.symbol_id = "changed"  # type: ignore

    def test_symbol_hash_equality(self):
        """Same values produce equal hashes"""
        sh1 = SymbolHash("id", "sig", "body", "impact")
        sh2 = SymbolHash("id", "sig", "body", "impact")
        assert sh1 == sh2

    def test_symbol_hash_hashable(self):
        """SymbolHash can be used in sets"""
        sh1 = SymbolHash("id", "sig", "body", "impact")
        sh2 = SymbolHash("id", "sig", "body", "impact")
        assert len({sh1, sh2}) == 1


class TestHashBasedImpactLevel:
    """HashBasedImpactLevel enum tests"""

    def test_all_levels_defined(self):
        """All impact levels exist"""
        assert HashBasedImpactLevel.NO_IMPACT.value == "no_impact"
        assert HashBasedImpactLevel.IR_LOCAL.value == "ir_local"
        assert HashBasedImpactLevel.SIGNATURE_CHANGE.value == "signature_change"
        assert HashBasedImpactLevel.STRUCTURAL_CHANGE.value == "structural_change"

    def test_enum_count(self):
        """Expected number of levels"""
        assert len(HashBasedImpactLevel) == 4

    def test_is_string_enum(self):
        """Levels are string enums"""
        for level in HashBasedImpactLevel:
            assert isinstance(level.value, str)


class TestImpactType:
    """ImpactType model tests"""

    def test_create_impact_type(self):
        """Create impact type"""
        impact = ImpactType(
            level=HashBasedImpactLevel.SIGNATURE_CHANGE,
            affected_symbols=["module.func", "module.class.method"],
            reason="Function signature changed",
        )
        assert impact.level == HashBasedImpactLevel.SIGNATURE_CHANGE
        assert len(impact.affected_symbols) == 2
        assert impact.confidence == 1.0  # default

    def test_impact_with_confidence(self):
        """Impact with custom confidence"""
        impact = ImpactType(
            level=HashBasedImpactLevel.IR_LOCAL,
            affected_symbols=[],
            reason="Minor change",
            confidence=0.8,
        )
        assert impact.confidence == 0.8

    def test_no_impact(self):
        """No impact scenario"""
        impact = ImpactType(
            level=HashBasedImpactLevel.NO_IMPACT,
            affected_symbols=[],
            reason="No changes detected",
        )
        assert len(impact.affected_symbols) == 0


class TestEffectType:
    """EffectType enum tests"""

    def test_pure_effects(self):
        """Pure and state effects"""
        assert EffectType.PURE.value == "pure"
        assert EffectType.READ_STATE.value == "read_state"
        assert EffectType.WRITE_STATE.value == "write_state"

    def test_io_effects(self):
        """IO-related effects"""
        assert EffectType.IO.value == "io"
        assert EffectType.LOG.value == "log"
        assert EffectType.NETWORK.value == "network"

    def test_db_effects(self):
        """Database effects"""
        assert EffectType.DB_READ.value == "db_read"
        assert EffectType.DB_WRITE.value == "db_write"

    def test_unknown_effect(self):
        """Unknown effect type"""
        assert EffectType.UNKNOWN_EFFECT.value == "unknown_effect"


class TestEffectHierarchy:
    """Effect hierarchy tests"""

    def test_io_subsumes_write_state(self):
        """IO is subtype of WRITE_STATE"""
        assert EFFECT_HIERARCHY[EffectType.IO] == EffectType.WRITE_STATE

    def test_db_write_subsumes_write_state(self):
        """DB_WRITE is subtype of WRITE_STATE"""
        assert EFFECT_HIERARCHY[EffectType.DB_WRITE] == EffectType.WRITE_STATE

    def test_db_read_subsumes_read_state(self):
        """DB_READ is subtype of READ_STATE"""
        assert EFFECT_HIERARCHY[EffectType.DB_READ] == EffectType.READ_STATE

    def test_hierarchy_completeness(self):
        """Hierarchy covers expected effects"""
        assert EffectType.IO in EFFECT_HIERARCHY
        assert EffectType.LOG in EFFECT_HIERARCHY
        assert EffectType.NETWORK in EFFECT_HIERARCHY


class TestEdgeCases:
    """Edge case tests"""

    def test_empty_affected_symbols(self):
        """Empty affected symbols list"""
        impact = ImpactType(
            level=HashBasedImpactLevel.NO_IMPACT,
            affected_symbols=[],
            reason="No symbols affected",
        )
        assert impact.affected_symbols == []

    def test_many_affected_symbols(self):
        """Many affected symbols"""
        symbols = [f"module.func_{i}" for i in range(1000)]
        impact = ImpactType(
            level=HashBasedImpactLevel.STRUCTURAL_CHANGE,
            affected_symbols=symbols,
            reason="Major refactor",
        )
        assert len(impact.affected_symbols) == 1000

    def test_unicode_in_reason(self):
        """Unicode in reason"""
        impact = ImpactType(
            level=HashBasedImpactLevel.IR_LOCAL,
            affected_symbols=[],
            reason="함수 시그니처 변경 🔄",
        )
        assert "함수" in impact.reason

    def test_confidence_bounds(self):
        """Confidence at edge values"""
        low = ImpactType(
            level=HashBasedImpactLevel.NO_IMPACT,
            affected_symbols=[],
            reason="",
            confidence=0.0,
        )
        high = ImpactType(
            level=HashBasedImpactLevel.NO_IMPACT,
            affected_symbols=[],
            reason="",
            confidence=1.0,
        )
        assert low.confidence == 0.0
        assert high.confidence == 1.0
