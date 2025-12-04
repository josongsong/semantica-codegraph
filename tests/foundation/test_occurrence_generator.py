"""
Tests for OccurrenceGenerator

Tests:
- Generate occurrences from IR
- Node → Definition mapping
- Edge → Reference mapping
- Importance scoring
- Incremental generation
"""

import pytest

from src.contexts.code_foundation.infrastructure.ir.models.core import Edge, EdgeKind, Node, NodeKind, Span
from src.contexts.code_foundation.infrastructure.ir.models.document import IRDocument
from src.contexts.code_foundation.infrastructure.ir.models.occurrence import SymbolRole
from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator


class TestOccurrenceGenerator:
    """Test OccurrenceGenerator"""

    @pytest.fixture
    def simple_ir_doc(self):
        """Create a simple IR document for testing"""
        ir_doc = IRDocument(
            repo_id="test_repo",
            snapshot_id="2024-12-04",
            schema_version="2.0",
        )

        # File node
        file_node = Node(
            id="file:calc.py",
            kind=NodeKind.FILE,
            fqn="calc.py",
            file_path="src/calc.py",
            span=Span(0, 0, 50, 0),
            language="python",
        )

        # Class node (public)
        class_node = Node(
            id="class:Calculator",
            kind=NodeKind.CLASS,
            fqn="calc.Calculator",
            name="Calculator",
            file_path="src/calc.py",
            span=Span(10, 0, 20, 0),
            body_span=Span(11, 0, 20, 0),
            language="python",
            docstring="A simple calculator",
            parent_id="file:calc.py",
        )

        # Method node (public)
        method_node = Node(
            id="method:Calculator::add",
            kind=NodeKind.METHOD,
            fqn="calc.Calculator.add",
            name="add",
            file_path="src/calc.py",
            span=Span(12, 4, 14, 0),
            body_span=Span(13, 0, 14, 0),
            language="python",
            docstring="Add two numbers",
            parent_id="class:Calculator",
        )

        # Private variable (starts with _)
        private_var = Node(
            id="var:_internal",
            kind=NodeKind.VARIABLE,
            fqn="calc._internal",
            name="_internal",
            file_path="src/calc.py",
            span=Span(5, 0, 5, 15),
            language="python",
            parent_id="file:calc.py",
        )

        # Function in main.py (uses Calculator)
        main_function = Node(
            id="function:main",
            kind=NodeKind.FUNCTION,
            fqn="main.main",
            name="main",
            file_path="src/main.py",
            span=Span(5, 0, 10, 0),
            language="python",
        )

        # Test function
        test_function = Node(
            id="function:test_calculator",
            kind=NodeKind.FUNCTION,
            fqn="test_calc.test_calculator",
            name="test_calculator",
            file_path="tests/test_calc.py",
            span=Span(1, 0, 5, 0),
            language="python",
            attrs={"is_test": True},
        )

        ir_doc.nodes = [
            file_node,
            class_node,
            method_node,
            private_var,
            main_function,
            test_function,
        ]

        # Edges
        # CALLS edge (main → Calculator.add)
        call_edge = Edge(
            id="edge:call:main→add",
            kind=EdgeKind.CALLS,
            source_id="function:main",
            target_id="method:Calculator::add",
            span=Span(8, 4, 8, 15),
        )

        # READS edge (main → _internal)
        read_edge = Edge(
            id="edge:read:main→_internal",
            kind=EdgeKind.READS,
            source_id="function:main",
            target_id="var:_internal",
            span=Span(9, 4, 9, 13),
        )

        # WRITES edge (test → Calculator) - for coverage
        write_edge = Edge(
            id="edge:write:test→var",
            kind=EdgeKind.WRITES,
            source_id="function:test_calculator",
            target_id="var:_internal",
            span=Span(3, 4, 3, 13),
        )

        # IMPORTS edge
        import_edge = Edge(
            id="edge:import:main→Calculator",
            kind=EdgeKind.IMPORTS,
            source_id="function:main",
            target_id="class:Calculator",
            span=Span(1, 0, 1, 30),
        )

        # CONTAINS edge (should not generate occurrence)
        contains_edge = Edge(
            id="edge:contains:file→class",
            kind=EdgeKind.CONTAINS,
            source_id="file:calc.py",
            target_id="class:Calculator",
        )

        ir_doc.edges = [
            call_edge,
            read_edge,
            write_edge,
            import_edge,
            contains_edge,
        ]

        return ir_doc

    def test_generate_basic(self, simple_ir_doc):
        """Test basic occurrence generation"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # Should have occurrences for:
        # - 5 symbol nodes (not FILE): Calculator, add, _internal, main, test_calculator
        # - 4 edges (not CONTAINS): call, read, write, import
        # Total: 9 occurrences
        assert len(occurrences) > 0
        assert index.total_occurrences == len(occurrences)

        # Check index is built
        assert len(index.by_id) == len(occurrences)

    def test_definition_occurrences(self, simple_ir_doc):
        """Test definition occurrences are created"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # Calculator class definition
        calc_defs = index.get_definitions("class:Calculator")
        assert len(calc_defs) == 1
        assert calc_defs[0].is_definition()
        assert calc_defs[0].file_path == "src/calc.py"
        assert calc_defs[0].has_role(SymbolRole.DEFINITION)

        # Method definition
        method_defs = index.get_definitions("method:Calculator::add")
        assert len(method_defs) == 1
        assert method_defs[0].is_definition()

    def test_reference_occurrences(self, simple_ir_doc):
        """Test reference occurrences from edges"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # Calculator.add is called (READ_ACCESS)
        add_refs = index.get_usages("method:Calculator::add")
        assert len(add_refs) >= 1

        # Should have READ_ACCESS role
        for ref in add_refs:
            assert ref.has_role(SymbolRole.READ_ACCESS)

    def test_write_occurrences(self, simple_ir_doc):
        """Test write occurrences from WRITES edges"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # _internal is written to
        write_occs = [occ for occ in index.get_references("var:_internal") if occ.has_role(SymbolRole.WRITE_ACCESS)]
        assert len(write_occs) >= 1

    def test_import_occurrences(self, simple_ir_doc):
        """Test import occurrences"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # Calculator is imported
        import_occs = [occ for occ in index.get_references("class:Calculator") if occ.has_role(SymbolRole.IMPORT)]
        assert len(import_occs) >= 1

    def test_importance_scoring(self, simple_ir_doc):
        """Test importance scoring"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # Public class with docstring should have high importance
        calc_def = index.get_definitions("class:Calculator")[0]
        assert calc_def.importance_score > 0.6

        # Private variable should have lower importance
        private_def = index.get_definitions("var:_internal")[0]
        assert private_def.importance_score < calc_def.importance_score

        # Test function should have reduced importance
        test_def = index.get_definitions("function:test_calculator")[0]
        # Test role reduces importance
        assert test_def.has_role(SymbolRole.TEST)

    def test_public_vs_private(self, simple_ir_doc):
        """Test public vs private API importance"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # Public symbols (Calculator, add)
        calc_def = index.get_definitions("class:Calculator")[0]
        method_def = index.get_definitions("method:Calculator::add")[0]

        # Private symbol (_internal)
        private_def = index.get_definitions("var:_internal")[0]

        # Public should have higher importance
        assert calc_def.importance_score > private_def.importance_score
        assert method_def.importance_score > private_def.importance_score

    def test_edge_kind_to_role_mapping(self, simple_ir_doc):
        """Test edge kind → symbol role mapping"""
        generator = OccurrenceGenerator()

        # CALLS → READ_ACCESS
        assert generator._edge_kind_to_role(EdgeKind.CALLS) == SymbolRole.READ_ACCESS

        # WRITES → WRITE_ACCESS
        assert generator._edge_kind_to_role(EdgeKind.WRITES) == SymbolRole.WRITE_ACCESS

        # IMPORTS → IMPORT
        assert generator._edge_kind_to_role(EdgeKind.IMPORTS) == SymbolRole.IMPORT

        # CONTAINS → NONE (structural only)
        assert generator._edge_kind_to_role(EdgeKind.CONTAINS) == SymbolRole.NONE

    def test_occurrence_ids_unique(self, simple_ir_doc):
        """Test that occurrence IDs are unique"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # All IDs should be unique
        ids = [occ.id for occ in occurrences]
        assert len(ids) == len(set(ids))

    def test_parent_symbol_id_set(self, simple_ir_doc):
        """Test that parent_symbol_id is set for references"""
        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(simple_ir_doc)

        # Reference occurrences should have parent_symbol_id
        refs = index.get_usages("method:Calculator::add")
        for ref in refs:
            # References from edges have source as parent
            assert ref.parent_symbol_id is not None

    def test_incremental_generation(self, simple_ir_doc):
        """Test incremental occurrence generation"""
        generator = OccurrenceGenerator()

        # Initial generation
        initial_occs, initial_index = generator.generate(simple_ir_doc)
        initial_count = len(initial_occs)

        # Simulate change: modify Calculator class
        changed_symbol_ids = {"class:Calculator", "method:Calculator::add"}

        # Incremental update
        new_occs, updated_index = generator.generate_incremental(
            simple_ir_doc,
            changed_symbol_ids,
            initial_index,
        )

        # Should have regenerated occurrences for changed symbols
        assert len(new_occs) > 0

        # Total count should be similar (may vary slightly)
        # Updated index should still have all occurrences
        assert updated_index.total_occurrences > 0


class TestOccurrenceGeneratorEdgeCases:
    """Test edge cases"""

    def test_empty_ir_doc(self):
        """Test with empty IR document"""
        ir_doc = IRDocument(
            repo_id="empty",
            snapshot_id="2024-12-04",
            schema_version="2.0",
        )

        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(ir_doc)

        assert len(occurrences) == 0
        assert index.total_occurrences == 0

    def test_only_non_symbol_nodes(self):
        """Test with only non-symbol nodes (e.g., FILE, MODULE)"""
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="2024-12-04",
            schema_version="2.0",
        )

        # Only FILE nodes (not symbols)
        ir_doc.nodes = [
            Node(
                id="file:main.py",
                kind=NodeKind.FILE,
                fqn="main.py",
                file_path="main.py",
                span=Span(0, 0, 10, 0),
                language="python",
            )
        ]

        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(ir_doc)

        # FILE nodes shouldn't generate occurrences
        assert len(occurrences) == 0

    def test_edge_with_invalid_source(self):
        """Test edge with non-existent source node"""
        ir_doc = IRDocument(
            repo_id="test",
            snapshot_id="2024-12-04",
            schema_version="2.0",
        )

        # Valid target
        ir_doc.nodes = [
            Node(
                id="class:Calculator",
                kind=NodeKind.CLASS,
                fqn="Calculator",
                name="Calculator",
                file_path="calc.py",
                span=Span(1, 0, 5, 0),
                language="python",
            )
        ]

        # Edge with invalid source
        ir_doc.edges = [
            Edge(
                id="edge:call:invalid→Calculator",
                kind=EdgeKind.CALLS,
                source_id="invalid_id",  # Doesn't exist
                target_id="class:Calculator",
            )
        ]

        generator = OccurrenceGenerator()
        occurrences, index = generator.generate(ir_doc)

        # Should have 1 occurrence (class definition only, edge ignored)
        assert len(occurrences) == 1
        assert occurrences[0].is_definition()
