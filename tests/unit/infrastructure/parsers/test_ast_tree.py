"""
AST Tree Tests

Tests for Tree-sitter AST wrapper.
"""

from unittest.mock import MagicMock, patch

import pytest
from src.foundation.parsing.ast_tree import AstTree
from src.foundation.parsing.source_file import SourceFile


class TestAstTreeBasics:
    """Test basic AstTree functionality."""

    def test_ast_tree_creation(self):
        """Test AstTree can be instantiated."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)

        assert ast is not None
        assert ast.source is source
        assert ast.tree is mock_tree

    def test_root_property(self):
        """Test root property returns root node."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_root = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)

        assert ast.root is mock_root


class TestParse:
    """Test parse class method."""

    @patch("src.foundation.parsing.ast_tree.get_registry")
    def test_parse_success(self, mock_get_registry):
        """Test parsing source file successfully."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo():\n    pass",
            language="python",
        )

        # Mock parser
        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_parser.parse.return_value = mock_tree

        # Mock registry
        mock_registry = MagicMock()
        mock_registry.get_parser.return_value = mock_parser
        mock_get_registry.return_value = mock_registry

        ast = AstTree.parse(source)

        assert ast is not None
        mock_parser.parse.assert_called_once_with(b"def foo():\n    pass")

    @patch("src.foundation.parsing.ast_tree.get_registry")
    def test_parse_unsupported_language(self, mock_get_registry):
        """Test parsing unsupported language raises ValueError."""
        source = SourceFile.from_content(
            file_path="test.unknown",
            content="content",
            language="unknown",
        )

        # Mock registry returns None for unsupported language
        mock_registry = MagicMock()
        mock_registry.get_parser.return_value = None
        mock_get_registry.return_value = mock_registry

        with pytest.raises(ValueError, match="Language not supported"):
            AstTree.parse(source)

    @patch("src.foundation.parsing.ast_tree.get_registry")
    def test_parse_failure_raises(self, mock_get_registry):
        """Test parsing failure raises ValueError."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="invalid syntax",
            language="python",
        )

        # Mock parser returns None (parse failure)
        mock_parser = MagicMock()
        mock_parser.parse.return_value = None

        mock_registry = MagicMock()
        mock_registry.get_parser.return_value = mock_parser
        mock_get_registry.return_value = mock_registry

        with pytest.raises(ValueError, match="Failed to parse file"):
            AstTree.parse(source)


class TestParseIncremental:
    """Test parse_incremental class method."""

    @patch("src.foundation.parsing.ast_tree._incremental_parser")
    @patch("src.foundation.parsing.ast_tree.get_registry")
    def test_parse_incremental_success(self, mock_get_registry, mock_incr_parser):
        """Test incremental parsing successfully."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo():\n    pass",
            language="python",
        )

        # Mock parser
        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        # Mock incremental parser
        mock_incr_parser.parse_incremental.return_value = mock_tree

        # Mock registry
        mock_registry = MagicMock()
        mock_registry.get_parser.return_value = mock_parser
        mock_get_registry.return_value = mock_registry

        old_content = "def foo():\n    return 1"

        ast = AstTree.parse_incremental(source, old_content=old_content)

        assert ast is not None
        mock_incr_parser.parse_incremental.assert_called_once_with(
            parser=mock_parser,
            file_path="test.py",
            new_content="def foo():\n    pass",
            old_content=old_content,
            diff_text=None,
        )

    @patch("src.foundation.parsing.ast_tree._incremental_parser")
    @patch("src.foundation.parsing.ast_tree.get_registry")
    def test_parse_incremental_with_diff(self, mock_get_registry, mock_incr_parser):
        """Test incremental parsing with diff text."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def bar():\n    pass",
            language="python",
        )

        mock_parser = MagicMock()
        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()
        mock_incr_parser.parse_incremental.return_value = mock_tree

        mock_registry = MagicMock()
        mock_registry.get_parser.return_value = mock_parser
        mock_get_registry.return_value = mock_registry

        diff_text = "@@ -1,1 +1,1 @@\n-def foo():\n+def bar():"

        ast = AstTree.parse_incremental(source, diff_text=diff_text)

        assert ast is not None
        call_kwargs = mock_incr_parser.parse_incremental.call_args.kwargs
        assert call_kwargs["diff_text"] == diff_text


class TestWalk:
    """Test AST traversal."""

    def test_walk_single_node(self):
        """Test walking AST with single node."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        # Mock tree with single root node
        mock_root = MagicMock()
        mock_root.children = []

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        nodes = ast.walk()

        assert len(nodes) == 1
        assert nodes[0] is mock_root

    def test_walk_with_children(self):
        """Test walking AST with children."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        # Mock tree with root and children
        child1 = MagicMock()
        child1.children = []

        child2 = MagicMock()
        child2.children = []

        mock_root = MagicMock()
        mock_root.children = [child1, child2]

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        nodes = ast.walk()

        # Should return root + 2 children = 3 nodes
        assert len(nodes) == 3
        assert nodes[0] is mock_root
        assert child1 in nodes
        assert child2 in nodes


class TestFindByType:
    """Test finding nodes by type."""

    def test_find_by_type_no_match(self):
        """Test finding nodes when no matches."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.children = []

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        matches = ast.find_by_type("function_definition")

        assert len(matches) == 0

    def test_find_by_type_single_match(self):
        """Test finding nodes with single match."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo(): pass",
            language="python",
        )

        # Mock tree structure
        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.children = []

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.children = [func_node]

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        matches = ast.find_by_type("function_definition")

        assert len(matches) == 1
        assert matches[0] is func_node

    def test_find_by_type_multiple_matches(self):
        """Test finding nodes with multiple matches."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo(): pass\ndef bar(): pass",
            language="python",
        )

        # Mock tree with two function nodes
        func1 = MagicMock()
        func1.type = "function_definition"
        func1.children = []

        func2 = MagicMock()
        func2.type = "function_definition"
        func2.children = []

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.children = [func1, func2]

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        matches = ast.find_by_type("function_definition")

        assert len(matches) == 2
        assert func1 in matches
        assert func2 in matches


class TestGetText:
    """Test extracting node text."""

    def test_get_text(self):
        """Test getting text content of a node."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo():\n    pass",
            language="python",
        )

        # Mock node with byte range
        mock_node = MagicMock()
        mock_node.start_byte = 0
        mock_node.end_byte = 10

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)
        text = ast.get_text(mock_node)

        assert text == "def foo():"


class TestGetSpan:
    """Test converting nodes to IR Span."""

    def test_get_span_single_line(self):
        """Test getting span for single-line node."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        # Mock node (Tree-sitter uses 0-indexed lines)
        mock_node = MagicMock()
        mock_node.start_point = (0, 0)  # Line 1, col 0
        mock_node.end_point = (0, 5)  # Line 1, col 5

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)
        span = ast.get_span(mock_node)

        # IR uses 1-indexed lines
        assert span.start_line == 1
        assert span.start_col == 0
        assert span.end_line == 1
        assert span.end_col == 5

    def test_get_span_multi_line(self):
        """Test getting span for multi-line node."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="def foo():\n    pass",
            language="python",
        )

        mock_node = MagicMock()
        mock_node.start_point = (0, 0)  # Line 1, col 0
        mock_node.end_point = (1, 8)  # Line 2, col 8

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)
        span = ast.get_span(mock_node)

        assert span.start_line == 1
        assert span.end_line == 2


class TestFindNodeAtLine:
    """Test finding node at specific line."""

    def test_find_node_at_line_root_only(self):
        """Test finding node at line when only root matches."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_root = MagicMock()
        mock_root.start_point = (0, 0)
        mock_root.end_point = (0, 5)
        mock_root.children = []

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        node = ast.find_node_at_line(1)

        assert node is mock_root

    def test_find_node_at_line_returns_deepest(self):
        """Test finding deepest node at line."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        # Deep child
        deep_child = MagicMock()
        deep_child.start_point = (0, 0)
        deep_child.end_point = (0, 5)
        deep_child.children = []

        # Parent
        parent = MagicMock()
        parent.start_point = (0, 0)
        parent.end_point = (0, 5)
        parent.children = [deep_child]

        # Root
        mock_root = MagicMock()
        mock_root.start_point = (0, 0)
        mock_root.end_point = (0, 5)
        mock_root.children = [parent]

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        node = ast.find_node_at_line(1)

        # Should return deepest node
        assert node is deep_child

    def test_find_node_at_line_outside_range(self):
        """Test finding node at line outside AST range."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_root = MagicMock()
        mock_root.start_point = (0, 0)
        mock_root.end_point = (0, 5)
        mock_root.children = []

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        node = ast.find_node_at_line(10)

        assert node is None


class TestNodeHelpers:
    """Test node helper methods."""

    def test_get_parent(self):
        """Test getting parent node."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_parent = MagicMock()
        mock_node = MagicMock()
        mock_node.parent = mock_parent

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)
        parent = ast.get_parent(mock_node)

        assert parent is mock_parent

    def test_get_children(self):
        """Test getting child nodes."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        child1 = MagicMock()
        child2 = MagicMock()
        mock_node = MagicMock()
        mock_node.children = [child1, child2]

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)
        children = ast.get_children(mock_node)

        assert len(children) == 2
        assert child1 in children
        assert child2 in children

    def test_get_named_children(self):
        """Test getting only named child nodes."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        # Named children
        named1 = MagicMock()
        named1.is_named = True

        named2 = MagicMock()
        named2.is_named = True

        # Anonymous child
        anon = MagicMock()
        anon.is_named = False

        mock_node = MagicMock()
        mock_node.children = [named1, anon, named2]

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)
        named_children = ast.get_named_children(mock_node)

        assert len(named_children) == 2
        assert named1 in named_children
        assert named2 in named_children
        assert anon not in named_children


class TestErrorChecking:
    """Test error checking methods."""

    def test_has_error_no_errors(self):
        """Test has_error returns False when no errors."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.is_missing = False
        mock_root.children = []

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)

        assert ast.has_error() is False

    def test_has_error_with_error_node(self):
        """Test has_error returns True when ERROR node present."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="invalid syntax",
            language="python",
        )

        error_node = MagicMock()
        error_node.type = "ERROR"
        error_node.is_missing = False
        error_node.children = []

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.is_missing = False
        mock_root.children = [error_node]

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)

        assert ast.has_error() is True

    def test_has_error_with_missing_node(self):
        """Test has_error returns True when missing node present."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="incomplete",
            language="python",
        )

        missing_node = MagicMock()
        missing_node.type = "identifier"
        missing_node.is_missing = True
        missing_node.children = []

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.is_missing = False
        mock_root.children = [missing_node]

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)

        assert ast.has_error() is True

    def test_get_errors_no_errors(self):
        """Test get_errors returns empty list when no errors."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="x = 1",
            language="python",
        )

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.is_missing = False
        mock_root.children = []

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        errors = ast.get_errors()

        assert len(errors) == 0

    def test_get_errors_with_errors(self):
        """Test get_errors returns all error nodes."""
        source = SourceFile.from_content(
            file_path="test.py",
            content="invalid",
            language="python",
        )

        error1 = MagicMock()
        error1.type = "ERROR"
        error1.is_missing = False
        error1.children = []

        error2 = MagicMock()
        error2.type = "identifier"
        error2.is_missing = True
        error2.children = []

        mock_root = MagicMock()
        mock_root.type = "module"
        mock_root.is_missing = False
        mock_root.children = [error1, error2]

        mock_tree = MagicMock()
        mock_tree.root_node = mock_root

        ast = AstTree(source, mock_tree)
        errors = ast.get_errors()

        assert len(errors) == 2
        assert error1 in errors
        assert error2 in errors


class TestRepr:
    """Test string representation."""

    def test_repr(self):
        """Test __repr__ returns expected format."""
        source = SourceFile.from_content(
            file_path="src/main.py",
            content="x = 1",
            language="python",
        )

        mock_tree = MagicMock()
        mock_tree.root_node = MagicMock()

        ast = AstTree(source, mock_tree)
        repr_str = repr(ast)

        assert "AstTree" in repr_str
        assert "src/main.py" in repr_str
        assert "python" in repr_str
