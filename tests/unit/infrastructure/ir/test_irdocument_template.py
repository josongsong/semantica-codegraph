"""
Unit Tests for IRDocument Template IR Extensions (RFC-051)

Test Coverage:
- Template slot/element storage
- Lazy index building
- O(1) query methods
- Backward compatibility (v2.2 → v2.3)
- Performance characteristics

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    EscapeMode,
    SlotContextKind,
    TemplateElementContract,
    TemplateSlotContract,
)
from codegraph_engine.code_foundation.infrastructure.ir.models.core import Edge, EdgeKind, Node, NodeKind
from codegraph_engine.code_foundation.infrastructure.ir.models.document import IRDocument


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def empty_ir_doc():
    """Empty IR document (v2.3)"""
    return IRDocument(repo_id="test_repo", snapshot_id="2025-12-21", schema_version="2.3")


@pytest.fixture
def ir_doc_with_templates():
    """IR document with template slots and elements"""
    doc = IRDocument(repo_id="test_repo", snapshot_id="2025-12-21", schema_version="2.3")

    # Add nodes (with required fqn and language)
    doc.nodes.extend(
        [
            Node(
                id="var:user_bio",
                kind=NodeKind.VARIABLE,
                fqn="profile.user_bio",
                name="user_bio",
                file_path="profile.tsx",
                span=(10, 20),
                language="typescript",
            ),
            Node(
                id="func:render_profile",
                kind=NodeKind.FUNCTION,
                fqn="profile.renderProfile",
                name="renderProfile",
                file_path="profile.tsx",
                span=(50, 200),
                language="typescript",
            ),
        ]
    )

    # Add template slots
    doc.template_slots.extend(
        [
            TemplateSlotContract(
                slot_id="slot:profile.tsx:100:30",
                host_node_id="elem:profile.tsx:100:10",
                expr_raw="{user_bio}",
                expr_span=(1000, 1010),
                context_kind=SlotContextKind.RAW_HTML,
                escape_mode=EscapeMode.NONE,
                is_sink=True,
                name_hint="user_bio",
            ),
            TemplateSlotContract(
                slot_id="slot:profile.tsx:120:15",
                host_node_id="elem:profile.tsx:120:5",
                expr_raw="{user.name}",
                expr_span=(1200, 1211),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
                is_sink=False,
                name_hint="user.name",
            ),
            TemplateSlotContract(
                slot_id="slot:link.tsx:50:25",
                host_node_id="elem:link.tsx:50:5",
                expr_raw="{redirectUrl}",
                expr_span=(500, 513),
                context_kind=SlotContextKind.URL_ATTR,
                escape_mode=EscapeMode.UNKNOWN,
                is_sink=True,
                name_hint="redirectUrl",
            ),
        ]
    )

    # Add BINDS edges
    doc.edges.extend(
        [
            Edge(
                id="edge:binds:var_bio→slot100",
                kind=EdgeKind.BINDS,
                source_id="var:user_bio",
                target_id="slot:profile.tsx:100:30",
            ),
            Edge(
                id="edge:renders:func→template",
                kind=EdgeKind.RENDERS,
                source_id="func:render_profile",
                target_id="template:profile.tsx",
            ),
        ]
    )

    return doc


# ============================================================
# Schema Version Tests
# ============================================================


class TestSchemaVersion:
    """Test schema version handling"""

    def test_default_schema_version(self, empty_ir_doc):
        """Default schema version is 2.3"""
        assert empty_ir_doc.schema_version == "2.3"

    def test_backward_compatible_fields(self, empty_ir_doc):
        """New fields have safe defaults (backward compatible)"""
        # v2.2 documents won't have these fields
        # v2.3 default_factory ensures they exist
        assert isinstance(empty_ir_doc.template_slots, list)
        assert isinstance(empty_ir_doc.template_elements, list)
        assert len(empty_ir_doc.template_slots) == 0
        assert len(empty_ir_doc.template_elements) == 0


# ============================================================
# Index Building Tests
# ============================================================


class TestTemplateIndexBuilding:
    """Test lazy index building for template IR"""

    def test_build_indexes_with_templates(self, ir_doc_with_templates):
        """build_indexes() must build template indexes"""
        doc = ir_doc_with_templates

        # Build indexes
        doc.build_indexes()

        # Verify template indexes built
        assert doc._slots_by_context is not None
        assert doc._slots_by_file is not None
        assert doc._bindings_by_slot is not None
        assert doc._bindings_by_source is not None

    def test_slots_by_context_index(self, ir_doc_with_templates):
        """_slots_by_context index correctness"""
        doc = ir_doc_with_templates
        doc.build_indexes()

        # RAW_HTML: 1 slot
        raw_html_slots = doc._slots_by_context.get(SlotContextKind.RAW_HTML, [])
        assert len(raw_html_slots) == 1
        assert raw_html_slots[0].slot_id == "slot:profile.tsx:100:30"

        # HTML_TEXT: 1 slot
        text_slots = doc._slots_by_context.get(SlotContextKind.HTML_TEXT, [])
        assert len(text_slots) == 1
        assert text_slots[0].slot_id == "slot:profile.tsx:120:15"

        # URL_ATTR: 1 slot
        url_slots = doc._slots_by_context.get(SlotContextKind.URL_ATTR, [])
        assert len(url_slots) == 1
        assert url_slots[0].slot_id == "slot:link.tsx:50:25"

    def test_slots_by_file_index(self, ir_doc_with_templates):
        """_slots_by_file index correctness"""
        doc = ir_doc_with_templates
        doc.build_indexes()

        # profile.tsx: 2 slots
        profile_slots = doc._slots_by_file.get("profile.tsx", [])
        assert len(profile_slots) == 2

        # link.tsx: 1 slot
        link_slots = doc._slots_by_file.get("link.tsx", [])
        assert len(link_slots) == 1

    def test_bindings_by_slot_index(self, ir_doc_with_templates):
        """_bindings_by_slot index correctness"""
        doc = ir_doc_with_templates
        doc.build_indexes()

        # slot:profile.tsx:100:30 has 1 BINDS edge
        bindings = doc._bindings_by_slot.get("slot:profile.tsx:100:30", [])
        assert len(bindings) == 1
        assert bindings[0].kind == EdgeKind.BINDS
        assert bindings[0].source_id == "var:user_bio"

    def test_bindings_by_source_index(self, ir_doc_with_templates):
        """_bindings_by_source index correctness"""
        doc = ir_doc_with_templates
        doc.build_indexes()

        # var:user_bio → 1 slot
        bindings = doc._bindings_by_source.get("var:user_bio", [])
        assert len(bindings) == 1
        assert bindings[0].target_id == "slot:profile.tsx:100:30"


# ============================================================
# Query Method Tests (O(1) performance)
# ============================================================


class TestTemplateQueryMethods:
    """Test IRDocument template query methods"""

    def test_get_slots_by_context(self, ir_doc_with_templates):
        """get_slots_by_context() returns correct slots"""
        doc = ir_doc_with_templates

        # RAW_HTML
        raw_slots = doc.get_slots_by_context(SlotContextKind.RAW_HTML)
        assert len(raw_slots) == 1
        assert raw_slots[0].is_sink is True

        # HTML_TEXT
        text_slots = doc.get_slots_by_context(SlotContextKind.HTML_TEXT)
        assert len(text_slots) == 1
        assert text_slots[0].is_sink is False

    def test_get_raw_html_sinks(self, ir_doc_with_templates):
        """get_raw_html_sinks() returns XSS critical sinks"""
        doc = ir_doc_with_templates

        sinks = doc.get_raw_html_sinks()
        assert len(sinks) == 1
        assert sinks[0].context_kind == SlotContextKind.RAW_HTML
        assert sinks[0].escape_mode == EscapeMode.NONE

    def test_get_url_sinks(self, ir_doc_with_templates):
        """get_url_sinks() returns SSRF sinks"""
        doc = ir_doc_with_templates

        sinks = doc.get_url_sinks()
        assert len(sinks) == 1
        assert sinks[0].context_kind == SlotContextKind.URL_ATTR

    def test_get_slot_bindings(self, ir_doc_with_templates):
        """get_slot_bindings() returns BINDS edges for slot"""
        doc = ir_doc_with_templates

        bindings = doc.get_slot_bindings("slot:profile.tsx:100:30")
        assert len(bindings) == 1
        assert bindings[0].kind == EdgeKind.BINDS
        assert bindings[0].source_id == "var:user_bio"

    def test_get_variable_slots(self, ir_doc_with_templates):
        """get_variable_slots() returns slots bound to variable"""
        doc = ir_doc_with_templates

        slots = doc.get_variable_slots("var:user_bio")
        assert len(slots) == 1
        assert slots[0].slot_id == "slot:profile.tsx:100:30"
        assert slots[0].name_hint == "user_bio"

    def test_get_slots_by_file(self, ir_doc_with_templates):
        """get_slots_by_file() returns slots in file"""
        doc = ir_doc_with_templates

        profile_slots = doc.get_slots_by_file("profile.tsx")
        assert len(profile_slots) == 2

        link_slots = doc.get_slots_by_file("link.tsx")
        assert len(link_slots) == 1

    def test_empty_results(self, empty_ir_doc):
        """Query methods return empty lists when no templates"""
        doc = empty_ir_doc

        assert doc.get_raw_html_sinks() == []
        assert doc.get_url_sinks() == []
        assert doc.get_slot_bindings("nonexistent") == []
        assert doc.get_variable_slots("nonexistent") == []


# ============================================================
# Performance Tests
# ============================================================


class TestPerformance:
    """Test O(1) performance characteristics"""

    def test_query_without_index_build(self, ir_doc_with_templates):
        """Query methods auto-build indexes (ensure_indexes)"""
        doc = ir_doc_with_templates

        # Don't call build_indexes() manually
        # Query should trigger lazy build
        sinks = doc.get_raw_html_sinks()

        # Index should be built now
        assert doc._slots_by_context is not None
        assert len(sinks) == 1

    def test_large_slot_count_performance(self):
        """Test performance with 1000 slots"""
        doc = IRDocument(repo_id="perf_test", snapshot_id="2025-12-21")

        # Generate 1000 slots
        for i in range(1000):
            context = SlotContextKind.RAW_HTML if i % 10 == 0 else SlotContextKind.HTML_TEXT

            doc.template_slots.append(
                TemplateSlotContract(
                    slot_id=f"slot:test.tsx:{i}:1",
                    host_node_id=f"elem:test.tsx:{i}:1",
                    expr_raw="{}",
                    expr_span=(i * 10, i * 10 + 2),
                    context_kind=context,
                    escape_mode=EscapeMode.AUTO,
                )
            )

        # Build indexes (should be fast < 5ms for 1000 slots)
        import time

        start = time.perf_counter()
        doc.build_indexes()
        elapsed = time.perf_counter() - start

        assert elapsed < 0.01, f"Index build too slow: {elapsed * 1000:.1f}ms"

        # Query should be O(1)
        start = time.perf_counter()
        sinks = doc.get_raw_html_sinks()
        elapsed = time.perf_counter() - start

        assert len(sinks) == 100  # 10% are sinks
        assert elapsed < 0.001, f"Query too slow: {elapsed * 1000:.1f}ms"


# ============================================================
# get_stats() Extension Tests
# ============================================================


class TestGetStatsExtension:
    """Test get_stats() includes template IR metrics"""

    def test_stats_includes_template_counts(self, ir_doc_with_templates):
        """get_stats() includes template_slots and template_elements"""
        doc = ir_doc_with_templates
        stats = doc.get_stats()

        assert "template_slots" in stats
        assert "template_elements" in stats
        assert stats["template_slots"] == 3
        assert stats["template_elements"] == 0  # No elements in fixture

    def test_stats_includes_template_breakdown(self, ir_doc_with_templates):
        """get_stats() includes template_stats with context breakdown"""
        doc = ir_doc_with_templates
        doc.build_indexes()  # Ensure indexes built
        stats = doc.get_stats()

        assert "template_stats" in stats
        template_stats = stats["template_stats"]

        assert template_stats["total_slots"] == 3
        assert template_stats["sink_count"] == 2  # RAW_HTML + URL_ATTR
        assert "context_breakdown" in template_stats

        # Verify context breakdown
        breakdown = template_stats["context_breakdown"]
        assert breakdown["RAW_HTML"] == 1
        assert breakdown["HTML_TEXT"] == 1
        assert breakdown["URL_ATTR"] == 1

    def test_stats_empty_templates(self, empty_ir_doc):
        """get_stats() handles empty templates gracefully"""
        doc = empty_ir_doc
        stats = doc.get_stats()

        assert stats["template_slots"] == 0
        assert stats["template_elements"] == 0
        assert "template_stats" not in stats  # Only present if slots exist


# ============================================================
# Integration Tests (Multi-layer)
# ============================================================


class TestTemplateIRIntegration:
    """Test template IR integration with existing IR layers"""

    def test_template_nodes_in_node_index(self):
        """Template nodes are indexed with existing nodes"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")

        # Add template node (with required fields)
        doc.nodes.append(
            Node(
                id="template_slot:test.tsx:1:1",
                kind=NodeKind.TEMPLATE_SLOT,
                fqn="test.user_name_slot",
                name="user_name_slot",
                file_path="test.tsx",
                span=(10, 20),
                language="typescript",
            )
        )

        doc.build_indexes()

        # Should be in node index
        node = doc.get_node("template_slot:test.tsx:1:1")
        assert node is not None
        assert node.kind == NodeKind.TEMPLATE_SLOT

        # Should be in kind index
        template_nodes = doc.get_nodes_by_kind(NodeKind.TEMPLATE_SLOT)
        assert len(template_nodes) == 1

    def test_renders_edge_in_edge_index(self):
        """RENDERS edges are indexed with existing edges"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")

        # Add RENDERS edge
        doc.edges.append(
            Edge(
                id="edge:renders:func→template",
                kind=EdgeKind.RENDERS,
                source_id="func:render",
                target_id="template:test.tsx",
            )
        )

        doc.build_indexes()

        # Should be in edge index
        edges = doc.get_edges_from("func:render")
        assert len(edges) == 1
        assert edges[0].kind == EdgeKind.RENDERS

    def test_coexistence_with_taint_findings(self):
        """Template IR coexists with taint_findings"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")

        # Add template slot
        doc.template_slots.append(
            TemplateSlotContract(
                slot_id="slot:test.tsx:1:1",
                host_node_id="elem:test.tsx:1:1",
                expr_raw="{}",
                expr_span=(0, 2),
                context_kind=SlotContextKind.RAW_HTML,
                escape_mode=EscapeMode.NONE,
                is_sink=True,
            )
        )

        # Mock vulnerability (simplified - real Vulnerability has complex schema)
        # In real usage, taint_findings would be populated by TaintAnalysisService
        # Here we just verify the field coexists
        class MockVulnerability:
            """Mock for testing coexistence"""

            severity = "high"

        doc.taint_findings.append(MockVulnerability())  # type: ignore

        stats = doc.get_stats()

        # Both fields coexist
        assert stats["template_slots"] == 1
        assert stats["taint_findings"] == 1
        assert "template_stats" in stats


# ============================================================
# Error Handling Tests (Fail-fast)
# ============================================================


class TestErrorHandling:
    """Test error handling and edge cases"""

    def test_query_before_index_build(self, ir_doc_with_templates):
        """Query methods work before explicit build_indexes() (lazy)"""
        doc = ir_doc_with_templates

        # Don't call build_indexes()
        # ensure_indexes() should be called internally
        sinks = doc.get_raw_html_sinks()

        assert len(sinks) == 1  # Should work

    def test_empty_bindings_query(self, empty_ir_doc):
        """get_slot_bindings() returns empty list for nonexistent slot"""
        doc = empty_ir_doc

        bindings = doc.get_slot_bindings("nonexistent_slot")
        assert bindings == []

    def test_malformed_slot_id_in_index(self):
        """Malformed slot_id doesn't crash index building"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")

        # Add slot with malformed ID (no colons)
        class MockSlot:
            slot_id = "malformed_id"
            context_kind = SlotContextKind.HTML_TEXT

        doc.template_slots.append(MockSlot())

        # Should not crash
        doc.build_indexes()

        # Malformed slot won't be in file index
        slots = doc.get_slots_by_file("any_file")
        assert len(slots) == 0


# ============================================================
# Backward Compatibility Tests
# ============================================================


class TestBackwardCompatibility:
    """Test v2.2 → v2.3 migration safety"""

    def test_v22_document_loads_safely(self):
        """v2.2 document without template fields loads safely"""
        # Simulate v2.2 document (no template fields)
        doc = IRDocument(
            repo_id="legacy",
            snapshot_id="2024-01-01",
            schema_version="2.2",  # Old version
            # template_slots not present (v2.2)
        )

        # Should have default empty lists
        assert hasattr(doc, "template_slots")
        assert doc.template_slots == []

        # Queries should work (return empty)
        assert doc.get_raw_html_sinks() == []
        stats = doc.get_stats()
        assert stats["template_slots"] == 0

    def test_existing_queries_unaffected(self):
        """Existing query methods still work with v2.3"""
        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")

        doc.nodes.append(
            Node(
                id="func:test",
                kind=NodeKind.FUNCTION,
                fqn="test.test",
                name="test",
                file_path="test.py",
                span=(0, 10),
                language="python",
            )
        )

        doc.build_indexes()

        # Existing queries
        node = doc.get_node("func:test")
        assert node is not None

        funcs = doc.get_nodes_by_kind(NodeKind.FUNCTION)
        assert len(funcs) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--cov=src.contexts.code_foundation.infrastructure.ir.models.document"])
