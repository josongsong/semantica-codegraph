"""
Unit Tests for Template IR Kinds Extension (RFC-051)

Test Coverage:
- New NodeKind values (TEMPLATE_*)
- New EdgeKind values (RENDERS, BINDS, etc.)
- KindMeta registry integrity
- Enum exhaustiveness

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.ir.models.kinds import (
    EDGE_KIND_META,
    NODE_KIND_META,
    EdgeKind,
    EdgeKindMeta,
    KindMeta,
    NodeKind,
    get_edge_meta,
    get_node_meta,
    is_graph_kind,
    is_ir_kind,
    to_graph_node_kind,
)


# ============================================================
# NodeKind Tests (RFC-051 extensions)
# ============================================================


class TestTemplateNodeKind:
    """Test new template NodeKind values"""

    def test_template_node_kinds_defined(self):
        """All 4 template NodeKind values must be defined"""
        template_kinds = {
            NodeKind.TEMPLATE_DOC,
            NodeKind.TEMPLATE_ELEMENT,
            NodeKind.TEMPLATE_SLOT,
            NodeKind.TEMPLATE_DIRECTIVE,
        }

        for kind in template_kinds:
            assert kind in NodeKind, f"{kind} not in NodeKind enum"

    def test_template_node_kind_values(self):
        """Template NodeKind values match contract"""
        assert NodeKind.TEMPLATE_DOC == "TemplateDoc"
        assert NodeKind.TEMPLATE_ELEMENT == "TemplateElement"
        assert NodeKind.TEMPLATE_SLOT == "TemplateSlot"
        assert NodeKind.TEMPLATE_DIRECTIVE == "TemplateDirective"

    def test_template_node_kind_meta_registered(self):
        """All template NodeKinds have KindMeta"""
        template_kinds = [
            NodeKind.TEMPLATE_DOC,
            NodeKind.TEMPLATE_ELEMENT,
            NodeKind.TEMPLATE_SLOT,
            NodeKind.TEMPLATE_DIRECTIVE,
        ]

        for kind in template_kinds:
            meta = get_node_meta(kind)
            assert meta is not None, f"KindMeta missing for {kind}"
            assert isinstance(meta, KindMeta)

    def test_template_kinds_are_ir_only(self):
        """Template kinds are IR-only (not in graph)"""
        template_kinds = [
            NodeKind.TEMPLATE_DOC,
            NodeKind.TEMPLATE_ELEMENT,
            NodeKind.TEMPLATE_SLOT,
            NodeKind.TEMPLATE_DIRECTIVE,
        ]

        for kind in template_kinds:
            meta = get_node_meta(kind)
            assert meta.layer == "IR", f"{kind} should be IR-only"
            assert meta.graph_policy == "SKIP", f"{kind} should be SKIP in graph"

    def test_template_kinds_transform_to_none(self):
        """Template kinds transform to None in graph (SKIP)"""
        template_kinds = [
            NodeKind.TEMPLATE_DOC,
            NodeKind.TEMPLATE_ELEMENT,
            NodeKind.TEMPLATE_SLOT,
            NodeKind.TEMPLATE_DIRECTIVE,
        ]

        for kind in template_kinds:
            graph_kind = to_graph_node_kind(kind)
            assert graph_kind is None, f"{kind} should transform to None (SKIP)"


# ============================================================
# EdgeKind Tests (RFC-051 extensions)
# ============================================================


class TestTemplateEdgeKind:
    """Test new template EdgeKind values"""

    def test_template_edge_kinds_defined(self):
        """All 5 template EdgeKind values must be defined"""
        template_edges = {
            EdgeKind.RENDERS,
            EdgeKind.BINDS,
            EdgeKind.ESCAPES,
            EdgeKind.CONTAINS_SLOT,
            EdgeKind.TEMPLATE_CHILD,
        }

        for kind in template_edges:
            assert kind in EdgeKind, f"{kind} not in EdgeKind enum"

    def test_template_edge_kind_values(self):
        """Template EdgeKind values match contract"""
        assert EdgeKind.RENDERS == "RENDERS"
        assert EdgeKind.BINDS == "BINDS"
        assert EdgeKind.ESCAPES == "ESCAPES"
        assert EdgeKind.CONTAINS_SLOT == "CONTAINS_SLOT"
        assert EdgeKind.TEMPLATE_CHILD == "TEMPLATE_CHILD"

    def test_template_edge_kind_meta_registered(self):
        """All template EdgeKinds have EdgeKindMeta"""
        template_edges = [
            EdgeKind.RENDERS,
            EdgeKind.BINDS,
            EdgeKind.ESCAPES,
            EdgeKind.CONTAINS_SLOT,
            EdgeKind.TEMPLATE_CHILD,
        ]

        for kind in template_edges:
            meta = get_edge_meta(kind)
            assert meta is not None, f"EdgeKindMeta missing for {kind}"
            assert isinstance(meta, EdgeKindMeta)

    def test_template_edge_kind_families(self):
        """Verify template EdgeKind family classifications"""
        meta_renders = get_edge_meta(EdgeKind.RENDERS)
        assert meta_renders.family == "STRUCTURAL"
        assert meta_renders.layer == "IR"

        meta_binds = get_edge_meta(EdgeKind.BINDS)
        assert meta_binds.family == "CALL_USAGE"
        assert meta_binds.layer == "IR"

        meta_escapes = get_edge_meta(EdgeKind.ESCAPES)
        assert meta_escapes.family == "CALL_USAGE"

        meta_contains = get_edge_meta(EdgeKind.CONTAINS_SLOT)
        assert meta_contains.family == "STRUCTURAL"


# ============================================================
# Registry Integrity Tests
# ============================================================


class TestRegistryIntegrity:
    """Test KindMeta registry completeness"""

    def test_all_node_kinds_have_meta(self):
        """Every NodeKind must have KindMeta (fail-fast)"""
        for kind in NodeKind:
            try:
                meta = get_node_meta(kind)
                assert meta is not None
            except KeyError:
                pytest.fail(f"NodeKind.{kind.name} missing from NODE_KIND_META registry")

    def test_all_edge_kinds_have_meta(self):
        """Every EdgeKind must have EdgeKindMeta (fail-fast)"""
        for kind in EdgeKind:
            try:
                meta = get_edge_meta(kind)
                assert meta is not None
            except KeyError:
                pytest.fail(f"EdgeKind.{kind.name} missing from EDGE_KIND_META registry")

    def test_no_orphan_meta_entries(self):
        """No orphan entries in meta registries"""
        # All keys in NODE_KIND_META must be valid NodeKind
        for kind in NODE_KIND_META.keys():
            assert kind in NodeKind, f"Orphan entry in NODE_KIND_META: {kind}"

        # All keys in EDGE_KIND_META must be valid EdgeKind
        for kind in EDGE_KIND_META.keys():
            assert kind in EdgeKind, f"Orphan entry in EDGE_KIND_META: {kind}"


# ============================================================
# Semantic Tests (XSS analysis context)
# ============================================================


class TestXSSAnalysisContext:
    """Test template kinds in XSS analysis context"""

    def test_template_slot_is_ir_kind(self):
        """TEMPLATE_SLOT is IR kind (used in structural layer)"""
        assert is_ir_kind(NodeKind.TEMPLATE_SLOT)
        assert not is_graph_kind(NodeKind.TEMPLATE_SLOT)

    def test_binds_edge_for_taint_tracking(self):
        """BINDS edge is IR kind (used for taint tracking)"""
        meta = get_edge_meta(EdgeKind.BINDS)
        assert meta.layer == "IR"
        assert meta.family == "CALL_USAGE"  # Data flow

    def test_renders_edge_for_entry_point(self):
        """RENDERS edge connects code to template (entry point tracking)"""
        meta = get_edge_meta(EdgeKind.RENDERS)
        assert meta.layer == "IR"
        assert meta.family == "STRUCTURAL"  # Structural relationship


# ============================================================
# String Value Tests (JSON serialization safety)
# ============================================================


class TestEnumSerialization:
    """Test enum string values for JSON serialization"""

    def test_node_kind_str_conversion(self):
        """NodeKind enum values are valid strings"""
        # str(Enum) returns "EnumClass.VALUE", use .value for string
        assert NodeKind.TEMPLATE_SLOT.value == "TemplateSlot"
        assert isinstance(NodeKind.TEMPLATE_SLOT.value, str)

    def test_edge_kind_str_conversion(self):
        """EdgeKind enum values are valid strings"""
        # str(Enum) returns "EnumClass.VALUE", use .value for string
        assert EdgeKind.BINDS.value == "BINDS"
        assert isinstance(EdgeKind.BINDS.value, str)

    def test_enum_roundtrip(self):
        """Enum → str → Enum roundtrip"""
        kind_str = NodeKind.TEMPLATE_SLOT.value
        kind_reconstructed = NodeKind(kind_str)
        assert kind_reconstructed == NodeKind.TEMPLATE_SLOT


# ============================================================
# Parametrized Tests (Exhaustive)
# ============================================================


class TestParametrizedKinds:
    """Parametrized tests for all template kinds"""

    @pytest.mark.parametrize(
        "node_kind,expected_layer,expected_policy",
        [
            (NodeKind.TEMPLATE_DOC, "IR", "SKIP"),
            (NodeKind.TEMPLATE_ELEMENT, "IR", "SKIP"),
            (NodeKind.TEMPLATE_SLOT, "IR", "SKIP"),
            (NodeKind.TEMPLATE_DIRECTIVE, "IR", "SKIP"),
        ],
    )
    def test_template_node_meta(self, node_kind, expected_layer, expected_policy):
        """All template nodes are IR-only with SKIP policy"""
        meta = get_node_meta(node_kind)
        assert meta.layer == expected_layer
        assert meta.graph_policy == expected_policy

    @pytest.mark.parametrize(
        "edge_kind,expected_layer,expected_family",
        [
            (EdgeKind.RENDERS, "IR", "STRUCTURAL"),
            (EdgeKind.BINDS, "IR", "CALL_USAGE"),
            (EdgeKind.ESCAPES, "IR", "CALL_USAGE"),
            (EdgeKind.CONTAINS_SLOT, "IR", "STRUCTURAL"),
            (EdgeKind.TEMPLATE_CHILD, "IR", "STRUCTURAL"),
        ],
    )
    def test_template_edge_meta(self, edge_kind, expected_layer, expected_family):
        """All template edges are IR-layer with correct family"""
        meta = get_edge_meta(edge_kind)
        assert meta.layer == expected_layer
        assert meta.family == expected_family


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
