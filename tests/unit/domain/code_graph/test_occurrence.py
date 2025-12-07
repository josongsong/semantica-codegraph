"""
Tests for Occurrence models (SCIP-compatible)

Tests:
- SymbolRole bitflags
- Occurrence creation
- OccurrenceIndex queries
- Importance scoring
"""

import pytest

from src.contexts.code_foundation.infrastructure.ir.models.core import Span
from src.contexts.code_foundation.infrastructure.ir.models.occurrence import (
    Occurrence,
    OccurrenceIndex,
    SymbolRole,
    create_definition_occurrence,
    create_reference_occurrence,
)


class TestSymbolRole:
    """Test SymbolRole bitflags"""

    def test_none(self):
        """Test NONE role"""
        role = SymbolRole.NONE
        assert role == 0
        assert str(role) == "NONE"

    def test_single_role(self):
        """Test single role"""
        role = SymbolRole.DEFINITION
        assert role & SymbolRole.DEFINITION
        assert not (role & SymbolRole.READ_ACCESS)
        assert str(role) == "DEFINITION"

    def test_combined_roles(self):
        """Test combining roles with bitwise OR"""
        role = SymbolRole.DEFINITION | SymbolRole.TEST
        assert role & SymbolRole.DEFINITION
        assert role & SymbolRole.TEST
        assert not (role & SymbolRole.WRITE_ACCESS)
        assert str(role) == "DEFINITION | TEST"

    def test_all_roles(self):
        """Test all role combinations"""
        role = SymbolRole.DEFINITION | SymbolRole.IMPORT | SymbolRole.WRITE_ACCESS | SymbolRole.READ_ACCESS
        assert role & SymbolRole.DEFINITION
        assert role & SymbolRole.IMPORT
        assert role & SymbolRole.WRITE_ACCESS
        assert role & SymbolRole.READ_ACCESS


class TestOccurrence:
    """Test Occurrence model"""

    def test_create_definition(self):
        """Test creating definition occurrence"""
        occ = Occurrence(
            id="occ:def:class:Calculator",
            symbol_id="class:Calculator",
            span=Span(10, 0, 10, 20),
            roles=SymbolRole.DEFINITION,
            file_path="src/calc.py",
            importance_score=0.9,
        )

        assert occ.is_definition()
        assert not occ.is_reference()
        assert not occ.is_write()
        assert occ.importance_score == 0.9

    def test_create_reference(self):
        """Test creating reference occurrence"""
        occ = Occurrence(
            id="occ:ref:calc_add:5",
            symbol_id="method:Calculator::add",
            span=Span(25, 8, 25, 11),
            roles=SymbolRole.READ_ACCESS,
            file_path="src/main.py",
            parent_symbol_id="function:main",
            importance_score=0.5,
        )

        assert not occ.is_definition()
        assert occ.is_reference()
        assert not occ.is_write()
        assert occ.parent_symbol_id == "function:main"

    def test_create_write(self):
        """Test creating write occurrence"""
        occ = Occurrence(
            id="occ:write:var_x:10",
            symbol_id="var:x",
            span=Span(30, 4, 30, 5),
            roles=SymbolRole.WRITE_ACCESS,
            file_path="src/main.py",
            importance_score=0.3,
        )

        assert not occ.is_definition()
        assert not occ.is_reference()
        assert occ.is_write()

    def test_create_import(self):
        """Test creating import occurrence"""
        occ = Occurrence(
            id="occ:import:Calculator:1",
            symbol_id="class:Calculator",
            span=Span(1, 0, 1, 30),
            roles=SymbolRole.IMPORT,
            file_path="src/main.py",
            importance_score=0.4,
        )

        assert occ.is_import()
        assert not occ.is_definition()

    def test_has_role(self):
        """Test has_role method"""
        occ = Occurrence(
            id="occ:test",
            symbol_id="func:test",
            span=Span(1, 0, 1, 10),
            roles=SymbolRole.DEFINITION | SymbolRole.TEST,
            file_path="tests/test_calc.py",
        )

        assert occ.has_role(SymbolRole.DEFINITION)
        assert occ.has_role(SymbolRole.TEST)
        assert not occ.has_role(SymbolRole.WRITE_ACCESS)

    def test_get_context_snippet(self):
        """Test getting context snippet"""
        occ = Occurrence(
            id="occ:test",
            symbol_id="func:test",
            span=Span(5, 0, 5, 20),
            roles=SymbolRole.DEFINITION,
            file_path="src/calc.py",
            enclosing_range=Span(5, 0, 10, 0),
        )

        source_lines = [
            "# Line 0",
            "# Line 1",
            "# Line 2",
            "# Line 3",
            "# Line 4",
            "def calculate():",  # Line 5
            "    x = 10",
            "    y = 20",
            "    return x + y",
            "    # Line 9",
            "    # Line 10",
        ]

        snippet = occ.get_context_snippet(source_lines)
        assert "def calculate():" in snippet
        assert "return x + y" in snippet


class TestCreateHelpers:
    """Test helper functions"""

    def test_create_definition_occurrence(self):
        """Test create_definition_occurrence helper"""
        occ = create_definition_occurrence(
            symbol_id="class:Calculator",
            span=Span(10, 0, 10, 20),
            file_path="src/calc.py",
            importance_score=0.8,
        )

        assert occ.is_definition()
        assert occ.symbol_id == "class:Calculator"
        assert occ.importance_score == 0.8
        assert occ.id.startswith("occ:def:")

    def test_create_reference_occurrence(self):
        """Test create_reference_occurrence helper"""
        occ = create_reference_occurrence(
            symbol_id="method:Calculator::add",
            span=Span(25, 8, 25, 11),
            file_path="src/main.py",
            parent_symbol_id="function:main",
        )

        assert occ.is_reference()
        assert not occ.is_write()
        assert occ.symbol_id == "method:Calculator::add"
        assert occ.parent_symbol_id == "function:main"

    def test_create_write_occurrence(self):
        """Test create_reference_occurrence with is_write=True"""
        occ = create_reference_occurrence(
            symbol_id="var:x",
            span=Span(30, 4, 30, 5),
            file_path="src/main.py",
            is_write=True,
        )

        assert occ.is_write()
        assert not occ.is_reference()


class TestOccurrenceIndex:
    """Test OccurrenceIndex"""

    @pytest.fixture
    def sample_occurrences(self):
        """Create sample occurrences for testing"""
        return [
            # Definition
            Occurrence(
                id="occ:def:Calculator",
                symbol_id="class:Calculator",
                span=Span(10, 0, 10, 20),
                roles=SymbolRole.DEFINITION,
                file_path="src/calc.py",
                importance_score=0.9,
            ),
            # Reference 1
            Occurrence(
                id="occ:ref:Calculator:1",
                symbol_id="class:Calculator",
                span=Span(25, 8, 25, 18),
                roles=SymbolRole.READ_ACCESS,
                file_path="src/main.py",
                parent_symbol_id="function:main",
                importance_score=0.5,
            ),
            # Reference 2
            Occurrence(
                id="occ:ref:Calculator:2",
                symbol_id="class:Calculator",
                span=Span(30, 4, 30, 14),
                roles=SymbolRole.READ_ACCESS,
                file_path="src/main.py",
                parent_symbol_id="function:helper",
                importance_score=0.5,
            ),
            # Write
            Occurrence(
                id="occ:write:var_x:1",
                symbol_id="var:x",
                span=Span(15, 4, 15, 5),
                roles=SymbolRole.WRITE_ACCESS,
                file_path="src/calc.py",
                importance_score=0.3,
            ),
        ]

    def test_add_and_get(self, sample_occurrences):
        """Test adding and retrieving occurrences"""
        index = OccurrenceIndex()

        for occ in sample_occurrences:
            index.add(occ)

        assert index.total_occurrences == 4
        assert index.definitions_count == 1
        assert index.references_count == 2

        # Get by ID
        occ = index.get("occ:def:Calculator")
        assert occ is not None
        assert occ.symbol_id == "class:Calculator"

    def test_get_references(self, sample_occurrences):
        """Test get_references (O(1))"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        refs = index.get_references("class:Calculator")
        assert len(refs) == 3  # 1 definition + 2 references

        # Check all are for Calculator
        for occ in refs:
            assert occ.symbol_id == "class:Calculator"

    def test_get_definitions(self, sample_occurrences):
        """Test get_definitions"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        defs = index.get_definitions("class:Calculator")
        assert len(defs) == 1
        assert defs[0].is_definition()
        assert defs[0].file_path == "src/calc.py"

    def test_get_usages(self, sample_occurrences):
        """Test get_usages (references only, no definitions)"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        usages = index.get_usages("class:Calculator")
        assert len(usages) == 2  # Only references, not definition

        for occ in usages:
            assert not occ.is_definition()
            assert occ.is_reference()

    def test_get_file_occurrences(self, sample_occurrences):
        """Test get_file_occurrences (O(1))"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        # src/calc.py has 2 occurrences
        calc_occs = index.get_file_occurrences("src/calc.py")
        assert len(calc_occs) == 2

        # src/main.py has 2 occurrences
        main_occs = index.get_file_occurrences("src/main.py")
        assert len(main_occs) == 2

    def test_get_definitions_in_file(self, sample_occurrences):
        """Test get_definitions_in_file"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        # src/calc.py has 1 definition (Calculator class)
        defs = index.get_definitions_in_file("src/calc.py")
        assert len(defs) == 1
        assert defs[0].is_definition()

        # src/main.py has no definitions
        defs = index.get_definitions_in_file("src/main.py")
        assert len(defs) == 0

    def test_get_by_role(self, sample_occurrences):
        """Test get_by_role"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        # DEFINITION
        defs = index.get_by_role(SymbolRole.DEFINITION)
        assert len(defs) == 1

        # READ_ACCESS
        reads = index.get_by_role(SymbolRole.READ_ACCESS)
        assert len(reads) == 2

        # WRITE_ACCESS
        writes = index.get_by_role(SymbolRole.WRITE_ACCESS)
        assert len(writes) == 1

    def test_get_by_importance(self, sample_occurrences):
        """Test get_by_importance"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        # High importance (>= 0.7)
        high = index.get_by_importance(min_score=0.7)
        assert len(high) == 1
        assert high[0].importance_score == 0.9

        # Medium importance (>= 0.5)
        medium = index.get_by_importance(min_score=0.5)
        assert len(medium) == 3  # 0.9, 0.5, 0.5

        # Sorted by score (descending)
        assert medium[0].importance_score >= medium[1].importance_score

    def test_get_stats(self, sample_occurrences):
        """Test get_stats"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        stats = index.get_stats()

        assert stats["total_occurrences"] == 4
        assert stats["definitions"] == 1
        assert stats["references"] == 2
        assert stats["unique_symbols"] == 2  # Calculator, var:x
        assert stats["files"] == 2  # calc.py, main.py

        # Role breakdown
        assert "SymbolRole.DEFINITION" in str(stats["role_breakdown"])

    def test_clear(self, sample_occurrences):
        """Test clear"""
        index = OccurrenceIndex()
        for occ in sample_occurrences:
            index.add(occ)

        assert index.total_occurrences == 4

        index.clear()

        assert index.total_occurrences == 0
        assert len(index.by_id) == 0
        assert len(index.by_symbol) == 0
        assert len(index.by_file) == 0
