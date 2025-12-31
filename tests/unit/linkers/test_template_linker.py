"""
Unit Tests for TemplateLinker (RFC-051)

Test Coverage:
- BINDS edge generation (scope priority)
- RENDERS edge generation (JSX return detection)
- ESCAPES edge generation (Sanitizer KB)
- Scope resolution accuracy
- False Positive/Negative rates

Author: Semantica Team
"""

import pytest

from codegraph_engine.code_foundation.domain.ports.template_ports import (
    EscapeMode,
    SlotContextKind,
    TemplateDocContract,
    TemplateSlotContract,
)
from codegraph_engine.code_foundation.infrastructure.ir.models import Edge, EdgeKind, IRDocument, Node, NodeKind
from codegraph_engine.code_foundation.infrastructure.linkers.template_linker import (
    SanitizerKB,
    TemplateLinker,
    create_template_linker,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def sample_ir_doc():
    """Sample IRDocument with variables and functions"""
    doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")

    doc.nodes.extend(
        [
            # Function
            Node(
                id="func:renderProfile",
                kind=NodeKind.FUNCTION,
                fqn="profile.renderProfile",
                name="renderProfile",
                file_path="profile.tsx",
                span=(10, 200),
                language="typescript",
            ),
            # Function-scoped variable
            Node(
                id="var:user_bio",
                kind=NodeKind.VARIABLE,
                fqn="profile.renderProfile.user_bio",
                name="user_bio",
                file_path="profile.tsx",
                span=(20, 30),
                language="typescript",
                parent_id="func:renderProfile",
            ),
            # Module-scoped variable
            Node(
                id="var:global_data",
                kind=NodeKind.VARIABLE,
                fqn="profile.global_data",
                name="global_data",
                file_path="profile.tsx",
                span=(5, 8),
                language="typescript",
                parent_id="file:profile.tsx",
            ),
            # Different file variable (same name)
            Node(
                id="var:user_bio_other",
                kind=NodeKind.VARIABLE,
                fqn="other.user_bio",
                name="user_bio",  # Same name!
                file_path="other.tsx",
                span=(10, 20),
                language="typescript",
                parent_id="file:other.tsx",
            ),
        ]
    )

    # CONTAINS edges
    doc.edges.extend(
        [
            Edge(
                id="e1",
                kind=EdgeKind.CONTAINS,
                source_id="func:renderProfile",
                target_id="var:user_bio",
            ),
            Edge(
                id="e2",
                kind=EdgeKind.CONTAINS,
                source_id="file:profile.tsx",
                target_id="var:global_data",
            ),
        ]
    )

    doc.build_indexes()
    return doc


@pytest.fixture
def sample_template_doc():
    """Sample TemplateDocContract with slots"""
    return TemplateDocContract(
        doc_id="template:profile.tsx",
        engine="react-jsx",
        file_path="profile.tsx",
        root_element_ids=["elem:profile.tsx:100:10"],
        slots=[
            TemplateSlotContract(
                slot_id="slot:profile.tsx:100:30",
                host_node_id="elem:profile.tsx:100:10",
                expr_raw="{user_bio}",
                expr_span=(1000, 1010),
                context_kind=SlotContextKind.RAW_HTML,
                escape_mode=EscapeMode.NONE,
                is_sink=True,
                name_hint="user_bio",  # Matches var:user_bio
            ),
            TemplateSlotContract(
                slot_id="slot:profile.tsx:120:15",
                host_node_id="elem:profile.tsx:120:5",
                expr_raw="{global_data}",
                expr_span=(1200, 1213),
                context_kind=SlotContextKind.HTML_TEXT,
                escape_mode=EscapeMode.AUTO,
                name_hint="global_data",  # Matches var:global_data
            ),
        ],
        elements=[],
    )


# ============================================================
# Sanitizer KB Tests
# ============================================================


class TestSanitizerKB:
    """Test Sanitizer Knowledge Base"""

    def test_load_library_models(self):
        """Load library_models.yaml successfully"""
        kb = SanitizerKB()

        # Should load without error
        assert kb is not None

    def test_match_dompurify(self):
        """Match DOMPurify.sanitize"""
        kb = SanitizerKB()

        model = kb.match("DOMPurify.sanitize")

        assert model is not None
        assert model["library"] == "DOMPurify"
        assert model["confidence"] == 0.95
        assert model["sanitizer_type"] == "WHITE_LIST_CLEAN"

    def test_case_insensitive_matching(self):
        """Sanitizer matching is case-insensitive"""
        kb = SanitizerKB()

        # Mixed case
        model = kb.match("dompurify.SANITIZE")
        assert model is not None

        # Lowercase
        model = kb.match("dompurify.sanitize")
        assert model is not None

    def test_is_sanitizer(self):
        """is_sanitizer() method"""
        kb = SanitizerKB()

        assert kb.is_sanitizer("DOMPurify.sanitize") is True
        assert kb.is_sanitizer("bleach.clean") is True
        assert kb.is_sanitizer("unknown_function") is False

    def test_get_confidence(self):
        """get_confidence() returns correct values"""
        kb = SanitizerKB()

        assert kb.get_confidence("DOMPurify.sanitize") == 0.95
        assert kb.get_confidence("unknown") == 0.0


# ============================================================
# BINDS Edge Generation Tests
# ============================================================


class TestBindsEdgeGeneration:
    """Test BINDS edge generation"""

    def test_link_bindings_basic(self, sample_ir_doc, sample_template_doc):
        """Basic BINDS edge generation"""
        linker = TemplateLinker()

        binds_edges = linker.link_bindings(sample_ir_doc, [sample_template_doc])

        # Should create 2 BINDS edges (user_bio, global_data)
        assert len(binds_edges) == 2

        # All edges should be BINDS kind
        assert all(e.kind == EdgeKind.BINDS for e in binds_edges)

        # Check source/target
        edge_map = {e.target_id: e.source_id for e in binds_edges}

        assert "slot:profile.tsx:100:30" in edge_map
        assert "var:user_bio" in edge_map.values()

    def test_scope_priority_function_over_module(self, sample_ir_doc, sample_template_doc):
        """Function-scoped variable prioritized over module-scoped"""
        linker = TemplateLinker()

        binds_edges = linker.link_bindings(sample_ir_doc, [sample_template_doc])

        # Find binding for user_bio slot
        user_bio_binding = next((e for e in binds_edges if "slot:profile.tsx:100:30" == e.target_id), None)

        assert user_bio_binding is not None, f"user_bio binding not found. Edges: {[e.target_id for e in binds_edges]}"
        assert user_bio_binding.source_id == "var:user_bio"  # Function-scoped
        assert user_bio_binding.attrs["match_strategy"] == "function_scope"

    def test_no_binding_for_missing_variable(self):
        """No BINDS edge if variable not found"""
        linker = TemplateLinker()

        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.build_indexes()

        template_doc = TemplateDocContract(
            doc_id="template:test.tsx",
            engine="react-jsx",
            file_path="test.tsx",
            root_element_ids=[],
            slots=[
                TemplateSlotContract(
                    slot_id="slot:test.tsx:1:1",
                    host_node_id="elem:test.tsx:1:1",
                    expr_raw="{nonexistent}",
                    expr_span=(0, 13),
                    context_kind=SlotContextKind.HTML_TEXT,
                    escape_mode=EscapeMode.AUTO,
                    name_hint="nonexistent",
                )
            ],
            elements=[],
        )

        binds_edges = linker.link_bindings(doc, [template_doc])

        # No matching variable → no edge
        assert len(binds_edges) == 0

    def test_member_expression_root_extraction(self):
        """Member expression: user.profile.name → match 'user'"""
        linker = TemplateLinker()

        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.nodes.append(
            Node(
                id="var:user",
                kind=NodeKind.VARIABLE,
                fqn="test.user",
                name="user",
                file_path="test.tsx",
                span=(10, 20),
                language="typescript",
            )
        )
        doc.build_indexes()

        template_doc = TemplateDocContract(
            doc_id="template:test.tsx",
            engine="react-jsx",
            file_path="test.tsx",
            root_element_ids=[],
            slots=[
                TemplateSlotContract(
                    slot_id="slot:test.tsx:1:1",
                    host_node_id="elem:test.tsx:1:1",
                    expr_raw="{user.profile.name}",
                    expr_span=(0, 18),
                    context_kind=SlotContextKind.HTML_TEXT,
                    escape_mode=EscapeMode.AUTO,
                    name_hint="user.profile.name",  # Nested
                )
            ],
            elements=[],
        )

        binds_edges = linker.link_bindings(doc, [template_doc])

        # Should match root 'user'
        assert len(binds_edges) == 1
        assert binds_edges[0].source_id == "var:user"


# ============================================================
# RENDERS Edge Generation Tests
# ============================================================


class TestRendersEdgeGeneration:
    """Test RENDERS edge generation"""

    def test_link_renders_basic(self, sample_ir_doc, sample_template_doc):
        """Basic RENDERS edge generation"""
        linker = TemplateLinker()

        renders_edges = linker.link_renders(sample_ir_doc, [sample_template_doc])

        # Should create RENDERS edge (func → template)
        assert len(renders_edges) >= 1

        # Check kind
        assert all(e.kind == EdgeKind.RENDERS for e in renders_edges)

        # Check source/target
        edge = renders_edges[0]
        assert edge.source_id == "func:renderProfile"
        assert edge.target_id == "template:profile.tsx"

    def test_virtual_template_no_renders(self):
        """Virtual templates don't get RENDERS edges"""
        linker = TemplateLinker()

        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.build_indexes()

        virtual_template = TemplateDocContract(
            doc_id="virtual:expr_123",
            engine="virtual-html",
            file_path="app.ts",
            root_element_ids=[],
            slots=[],
            elements=[],
            is_virtual=True,
        )

        renders_edges = linker.link_renders(doc, [virtual_template])

        # Virtual templates skipped
        assert len(renders_edges) == 0


# ============================================================
# ESCAPES Edge Generation Tests
# ============================================================


class TestEscapesEdgeGeneration:
    """Test ESCAPES edge generation"""

    def test_link_escapes_requires_expressions(self):
        """ESCAPES requires Layer 5 (expressions)"""
        linker = TemplateLinker()

        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.build_indexes()

        # No expressions → no ESCAPES edges
        escapes_edges = linker.link_escapes(doc, [])

        assert len(escapes_edges) == 0

    def test_sanitizer_kb_integration(self):
        """Sanitizer KB is used for ESCAPES"""
        kb = SanitizerKB()
        linker = TemplateLinker(sanitizer_kb=kb)

        # Verify KB loaded
        assert kb.is_sanitizer("DOMPurify.sanitize")


# ============================================================
# Edge Case Tests
# ============================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_template_docs(self, sample_ir_doc):
        """Empty template_docs list"""
        linker = TemplateLinker()

        binds_edges = linker.link_bindings(sample_ir_doc, [])
        assert len(binds_edges) == 0

    def test_empty_ir_doc(self, sample_template_doc):
        """Empty IRDocument"""
        linker = TemplateLinker()

        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.build_indexes()

        binds_edges = linker.link_bindings(doc, [sample_template_doc])

        # No variables → no bindings
        assert len(binds_edges) == 0

    def test_slot_without_name_hint(self):
        """Slot without name_hint is skipped"""
        linker = TemplateLinker()

        doc = IRDocument(repo_id="test", snapshot_id="2025-12-21")
        doc.build_indexes()

        template_doc = TemplateDocContract(
            doc_id="template:test.tsx",
            engine="react-jsx",
            file_path="test.tsx",
            root_element_ids=[],
            slots=[
                TemplateSlotContract(
                    slot_id="slot:test.tsx:1:1",
                    host_node_id="elem:test.tsx:1:1",
                    expr_raw="{complex ? expr : other}",
                    expr_span=(0, 24),
                    context_kind=SlotContextKind.HTML_TEXT,
                    escape_mode=EscapeMode.AUTO,
                    name_hint=None,  # No hint
                )
            ],
            elements=[],
        )

        binds_edges = linker.link_bindings(doc, [template_doc])

        # No name_hint → no binding
        assert len(binds_edges) == 0


# ============================================================
# Factory Function Tests
# ============================================================


class TestFactoryFunction:
    """Test create_template_linker() factory"""

    def test_create_template_linker(self):
        """create_template_linker() returns TemplateLinkPort"""
        from codegraph_engine.code_foundation.domain.ports.template_ports import TemplateLinkPort

        linker = create_template_linker()

        assert isinstance(linker, TemplateLinkPort)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
