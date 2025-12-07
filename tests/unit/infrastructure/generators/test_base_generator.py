"""
Base IR Generator Tests

Tests for abstract base IR generator and utility methods.
"""

from unittest.mock import MagicMock

import pytest
from src.foundation.generators.base import IRGenerator


class ConcreteGenerator(IRGenerator):
    """Concrete implementation for testing."""

    def generate(self, source, snapshot_id):
        """Stub implementation."""
        return MagicMock()


class TestIRGeneratorBasics:
    """Test basic IRGenerator functionality."""

    def test_generator_creation(self):
        """Test IRGenerator can be instantiated."""
        gen = ConcreteGenerator(repo_id="test_repo")

        assert gen is not None
        assert gen.repo_id == "test_repo"

    def test_generator_is_abstract(self):
        """Test IRGenerator cannot be instantiated directly."""
        with pytest.raises(TypeError):
            # Should fail because generate() is abstract
            IRGenerator(repo_id="test_repo")

    def test_concrete_generator_has_generate(self):
        """Test concrete generator implements generate."""
        gen = ConcreteGenerator(repo_id="test_repo")

        assert hasattr(gen, "generate")
        assert callable(gen.generate)


class TestGenerateContentHash:
    """Test content hash generation."""

    def test_generate_content_hash_basic(self):
        """Test generating content hash."""
        gen = ConcreteGenerator(repo_id="test_repo")

        hash_val = gen.generate_content_hash("def foo(): pass")

        assert hash_val.startswith("sha256:")
        assert len(hash_val) == len("sha256:") + 64  # SHA256 hex is 64 chars

    def test_generate_content_hash_strips_whitespace(self):
        """Test hash generation strips leading/trailing whitespace."""
        gen = ConcreteGenerator(repo_id="test_repo")

        hash1 = gen.generate_content_hash("def foo(): pass")
        hash2 = gen.generate_content_hash("  def foo(): pass  ")

        # Should be same after stripping
        assert hash1 == hash2

    def test_generate_content_hash_different_content(self):
        """Test different content produces different hashes."""
        gen = ConcreteGenerator(repo_id="test_repo")

        hash1 = gen.generate_content_hash("def foo(): pass")
        hash2 = gen.generate_content_hash("def bar(): pass")

        assert hash1 != hash2

    def test_generate_content_hash_deterministic(self):
        """Test hash generation is deterministic."""
        gen = ConcreteGenerator(repo_id="test_repo")

        hash1 = gen.generate_content_hash("code")
        hash2 = gen.generate_content_hash("code")

        assert hash1 == hash2

    def test_generate_content_hash_empty_string(self):
        """Test hashing empty string."""
        gen = ConcreteGenerator(repo_id="test_repo")

        hash_val = gen.generate_content_hash("")

        assert hash_val.startswith("sha256:")


class TestCalculateCyclomaticComplexity:
    """Test cyclomatic complexity calculation."""

    def test_complexity_none_node(self):
        """Test complexity returns 1 for None node."""
        gen = ConcreteGenerator(repo_id="test_repo")

        complexity = gen.calculate_cyclomatic_complexity(None, set())

        assert complexity == 1

    def test_complexity_simple_node_no_branches(self):
        """Test complexity for node without branches."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Mock simple node
        mock_node = MagicMock()
        mock_node.type = "assignment"
        mock_node.children = []

        branch_types = {"if_statement", "while_statement"}
        complexity = gen.calculate_cyclomatic_complexity(mock_node, branch_types)

        assert complexity == 1

    def test_complexity_with_single_if(self):
        """Test complexity with single if statement."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Mock if statement
        if_node = MagicMock()
        if_node.type = "if_statement"
        if_node.children = []

        branch_types = {"if_statement"}
        complexity = gen.calculate_cyclomatic_complexity(if_node, branch_types)

        assert complexity == 2  # Base 1 + 1 if

    def test_complexity_with_multiple_branches(self):
        """Test complexity with multiple branches."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Mock nested structure with branches
        if_node = MagicMock()
        if_node.type = "if_statement"
        if_node.children = []

        while_node = MagicMock()
        while_node.type = "while_statement"
        while_node.children = []

        parent = MagicMock()
        parent.type = "function"
        parent.children = [if_node, while_node]

        branch_types = {"if_statement", "while_statement"}
        complexity = gen.calculate_cyclomatic_complexity(parent, branch_types)

        assert complexity == 3  # Base 1 + 1 if + 1 while

    def test_complexity_nested_branches(self):
        """Test complexity with nested branches."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Inner if
        inner_if = MagicMock()
        inner_if.type = "if_statement"
        inner_if.children = []

        # Outer if with inner if as child
        outer_if = MagicMock()
        outer_if.type = "if_statement"
        outer_if.children = [inner_if]

        branch_types = {"if_statement"}
        complexity = gen.calculate_cyclomatic_complexity(outer_if, branch_types)

        assert complexity == 3  # Base 1 + 1 outer + 1 inner


class TestHasLoop:
    """Test loop detection."""

    def test_has_loop_none_node(self):
        """Test has_loop returns False for None."""
        gen = ConcreteGenerator(repo_id="test_repo")

        has_loop = gen.has_loop(None, {"for_statement"})

        assert has_loop is False

    def test_has_loop_no_loops(self):
        """Test has_loop returns False when no loops."""
        gen = ConcreteGenerator(repo_id="test_repo")

        mock_node = MagicMock()
        mock_node.type = "assignment"
        mock_node.children = []

        has_loop = gen.has_loop(mock_node, {"for_statement", "while_statement"})

        assert has_loop is False

    def test_has_loop_direct_loop(self):
        """Test has_loop returns True for direct loop node."""
        gen = ConcreteGenerator(repo_id="test_repo")

        mock_node = MagicMock()
        mock_node.type = "for_statement"
        mock_node.children = []

        has_loop = gen.has_loop(mock_node, {"for_statement", "while_statement"})

        assert has_loop is True

    def test_has_loop_nested_loop(self):
        """Test has_loop finds nested loops."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Nested loop
        loop_node = MagicMock()
        loop_node.type = "for_statement"
        loop_node.children = []

        # Parent
        parent = MagicMock()
        parent.type = "function"
        parent.children = [loop_node]

        has_loop = gen.has_loop(parent, {"for_statement"})

        assert has_loop is True


class TestHasTry:
    """Test try/except detection."""

    def test_has_try_none_node(self):
        """Test has_try returns False for None."""
        gen = ConcreteGenerator(repo_id="test_repo")

        has_try = gen.has_try(None, {"try_statement"})

        assert has_try is False

    def test_has_try_no_try(self):
        """Test has_try returns False when no try."""
        gen = ConcreteGenerator(repo_id="test_repo")

        mock_node = MagicMock()
        mock_node.type = "assignment"
        mock_node.children = []

        has_try = gen.has_try(mock_node, {"try_statement"})

        assert has_try is False

    def test_has_try_direct_try(self):
        """Test has_try returns True for direct try node."""
        gen = ConcreteGenerator(repo_id="test_repo")

        mock_node = MagicMock()
        mock_node.type = "try_statement"
        mock_node.children = []

        has_try = gen.has_try(mock_node, {"try_statement"})

        assert has_try is True

    def test_has_try_nested_try(self):
        """Test has_try finds nested try."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Nested try
        try_node = MagicMock()
        try_node.type = "try_statement"
        try_node.children = []

        # Parent
        parent = MagicMock()
        parent.type = "function"
        parent.children = [try_node]

        has_try = gen.has_try(parent, {"try_statement"})

        assert has_try is True


class TestCountBranches:
    """Test branch counting."""

    def test_count_branches_none_node(self):
        """Test count_branches returns 0 for None."""
        gen = ConcreteGenerator(repo_id="test_repo")

        count = gen.count_branches(None, {"if_statement"})

        assert count == 0

    def test_count_branches_no_branches(self):
        """Test counting when no branches."""
        gen = ConcreteGenerator(repo_id="test_repo")

        mock_node = MagicMock()
        mock_node.type = "assignment"
        mock_node.children = []

        count = gen.count_branches(mock_node, {"if_statement"})

        assert count == 0

    def test_count_branches_single_branch(self):
        """Test counting single branch."""
        gen = ConcreteGenerator(repo_id="test_repo")

        mock_node = MagicMock()
        mock_node.type = "if_statement"
        mock_node.children = []

        count = gen.count_branches(mock_node, {"if_statement"})

        assert count == 1

    def test_count_branches_multiple_branches(self):
        """Test counting multiple branches."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Two if statements
        if1 = MagicMock()
        if1.type = "if_statement"
        if1.children = []

        if2 = MagicMock()
        if2.type = "if_statement"
        if2.children = []

        parent = MagicMock()
        parent.type = "function"
        parent.children = [if1, if2]

        count = gen.count_branches(parent, {"if_statement"})

        assert count == 2

    def test_count_branches_nested(self):
        """Test counting nested branches."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Nested if
        inner_if = MagicMock()
        inner_if.type = "if_statement"
        inner_if.children = []

        # Outer if
        outer_if = MagicMock()
        outer_if.type = "if_statement"
        outer_if.children = [inner_if]

        count = gen.count_branches(outer_if, {"if_statement"})

        assert count == 2


class TestGetNodeText:
    """Test node text extraction."""

    def test_get_node_text_basic(self):
        """Test extracting text from node."""
        gen = ConcreteGenerator(repo_id="test_repo")

        source = b"def foo(): pass"
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 7

        text = gen.get_node_text(mock_node, source)

        assert text == "def foo"

    def test_get_node_text_substring(self):
        """Test extracting substring from middle of source."""
        gen = ConcreteGenerator(repo_id="test_repo")

        source = b"def foo(): pass"
        mock_node = MagicMock()
        mock_node.start_byte = 4
        mock_node.end_byte = 7

        text = gen.get_node_text(mock_node, source)

        assert text == "foo"

    def test_get_node_text_unicode(self):
        """Test extracting text with unicode."""
        gen = ConcreteGenerator(repo_id="test_repo")

        source = "# 한글 주석".encode()
        mock_node = MagicMock()
        mock_node.start_byte = 2
        mock_node.end_byte = len(source)

        text = gen.get_node_text(mock_node, source)

        assert "한글" in text


class TestFindChildByType:
    """Test finding single child by type."""

    def test_find_child_by_type_found(self):
        """Test finding child when it exists."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Mock children
        child1 = MagicMock()
        child1.type = "identifier"

        child2 = MagicMock()
        child2.type = "parameters"

        parent = MagicMock()
        parent.children = [child1, child2]

        found = gen.find_child_by_type(parent, "parameters")

        assert found is child2

    def test_find_child_by_type_not_found(self):
        """Test finding child when it doesn't exist."""
        gen = ConcreteGenerator(repo_id="test_repo")

        child = MagicMock()
        child.type = "identifier"

        parent = MagicMock()
        parent.children = [child]

        found = gen.find_child_by_type(parent, "parameters")

        assert found is None

    def test_find_child_by_type_returns_first(self):
        """Test find_child_by_type returns first match."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Two matching children
        child1 = MagicMock()
        child1.type = "identifier"
        child1.name = "first"

        child2 = MagicMock()
        child2.type = "identifier"
        child2.name = "second"

        parent = MagicMock()
        parent.children = [child1, child2]

        found = gen.find_child_by_type(parent, "identifier")

        assert found is child1

    def test_find_child_by_type_no_children(self):
        """Test finding child when node has no children."""
        gen = ConcreteGenerator(repo_id="test_repo")

        parent = MagicMock()
        parent.children = []

        found = gen.find_child_by_type(parent, "identifier")

        assert found is None


class TestFindChildrenByType:
    """Test finding all children by type."""

    def test_find_children_by_type_none(self):
        """Test finding children when none match."""
        gen = ConcreteGenerator(repo_id="test_repo")

        child = MagicMock()
        child.type = "identifier"

        parent = MagicMock()
        parent.children = [child]

        found = gen.find_children_by_type(parent, "parameters")

        assert len(found) == 0

    def test_find_children_by_type_single(self):
        """Test finding single matching child."""
        gen = ConcreteGenerator(repo_id="test_repo")

        child1 = MagicMock()
        child1.type = "identifier"

        child2 = MagicMock()
        child2.type = "parameters"

        parent = MagicMock()
        parent.children = [child1, child2]

        found = gen.find_children_by_type(parent, "parameters")

        assert len(found) == 1
        assert found[0] is child2

    def test_find_children_by_type_multiple(self):
        """Test finding multiple matching children."""
        gen = ConcreteGenerator(repo_id="test_repo")

        # Three identifiers
        id1 = MagicMock()
        id1.type = "identifier"

        id2 = MagicMock()
        id2.type = "identifier"

        id3 = MagicMock()
        id3.type = "identifier"

        other = MagicMock()
        other.type = "parameters"

        parent = MagicMock()
        parent.children = [id1, other, id2, id3]

        found = gen.find_children_by_type(parent, "identifier")

        assert len(found) == 3
        assert id1 in found
        assert id2 in found
        assert id3 in found

    def test_find_children_by_type_preserves_order(self):
        """Test finding children preserves order."""
        gen = ConcreteGenerator(repo_id="test_repo")

        child1 = MagicMock()
        child1.type = "identifier"
        child1.name = "first"

        child2 = MagicMock()
        child2.type = "identifier"
        child2.name = "second"

        parent = MagicMock()
        parent.children = [child1, child2]

        found = gen.find_children_by_type(parent, "identifier")

        assert found[0] is child1
        assert found[1] is child2
