"""
Tests for Incremental Parsing Infrastructure

Tests DiffParser, EditCalculator, and IncrementalParser components.
"""

import pytest
from src.foundation.parsing.incremental import (
    DiffHunk,
    DiffParser,
    EditCalculator,
    IncrementalParser,
)


class TestDiffParser:
    """Test unified diff parsing"""

    def test_parse_single_hunk(self):
        """Test parsing a single diff hunk"""
        diff_text = """@@ -10,5 +10,6 @@
 def hello():
-    print('Hello')
+    print('Hello, World!')
+    print('Welcome')
     return True
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        assert len(hunks) == 1
        hunk = hunks[0]
        assert hunk.old_start == 10
        assert hunk.old_count == 5
        assert hunk.new_start == 10
        assert hunk.new_count == 6

    def test_parse_multiple_hunks(self):
        """Test parsing multiple diff hunks"""
        diff_text = """@@ -10,3 +10,4 @@
 def hello():
-    print('Hello')
+    print('Hello, World!')
+    print('Welcome')
@@ -20,2 +21,3 @@
 def goodbye():
-    return
+    print('Bye')
+    return False
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        assert len(hunks) == 2

        # First hunk
        assert hunks[0].old_start == 10
        assert hunks[0].old_count == 3
        assert hunks[0].new_start == 10
        assert hunks[0].new_count == 4

        # Second hunk
        assert hunks[1].old_start == 20
        assert hunks[1].old_count == 2
        assert hunks[1].new_start == 21
        assert hunks[1].new_count == 3

    def test_parse_no_count_in_hunk_header(self):
        """Test parsing hunk header without count (implies 1)"""
        diff_text = """@@ -5 +5,2 @@
 # Comment
+# Another comment
"""
        parser = DiffParser()
        hunks = parser.parse_diff(diff_text)

        assert len(hunks) == 1
        assert hunks[0].old_start == 5
        assert hunks[0].old_count == 1
        assert hunks[0].new_start == 5
        assert hunks[0].new_count == 2

    def test_parse_empty_diff(self):
        """Test parsing empty diff"""
        parser = DiffParser()
        hunks = parser.parse_diff("")

        assert len(hunks) == 0


class TestEditCalculator:
    """Test diff-to-edit conversion"""

    def test_simple_edit_calculation(self):
        """Test basic edit calculation"""
        old_content = """def hello():
    print('Hello')
    return True
"""

        hunk = DiffHunk(
            old_start=2,  # Line 2 (1-indexed)
            old_count=1,
            new_start=2,
            new_count=1,
            lines=["-    print('Hello')", "+    print('Hello, World!')"],
        )

        calculator = EditCalculator()
        edits = calculator.calculate_edits(old_content, [hunk])

        assert len(edits) == 1
        edit = edits[0]

        # Should start at line 1 (0-indexed)
        assert edit.start_row == 1
        assert edit.start_column == 0

    def test_line_col_to_byte_conversion(self):
        """Test line/column to byte offset conversion"""
        lines = ["def hello():", "    print('Hello')", "    return True"]

        calculator = EditCalculator()

        # Start of file
        assert calculator._line_col_to_byte(lines, 0, 0) == 0

        # Start of second line (after "def hello():\n" = 13 bytes)
        byte_offset_line1 = calculator._line_col_to_byte(lines, 1, 0)
        assert byte_offset_line1 == 13

        # Middle of second line (after "def hello():\n    " = 17 bytes)
        byte_offset_line1_col4 = calculator._line_col_to_byte(lines, 1, 4)
        assert byte_offset_line1_col4 == 17

    def test_multibyte_character_handling(self):
        """Test byte offset calculation with multibyte characters"""
        lines = ["# 한글 주석", "def func():", "    pass"]

        calculator = EditCalculator()

        # Korean characters are 3 bytes each in UTF-8
        # "# 한글 주석" = 1 + 1 + 9 + 1 + 9 = 21 bytes (approx)
        byte_offset_line1 = calculator._line_col_to_byte(lines, 1, 0)
        assert byte_offset_line1 > len(lines[0])  # More bytes than characters


class TestIncrementalParser:
    """Test incremental parsing with Tree-sitter"""

    @pytest.fixture
    def python_parser(self):
        """Get Python parser from registry"""
        from src.foundation.parsing import get_registry

        registry = get_registry()
        return registry.get_parser("python")

    def test_parse_without_cache(self, python_parser):
        """Test parsing without existing cache (full parse)"""
        incremental_parser = IncrementalParser()

        content = """def hello():
    print('Hello')
    return True
"""

        tree = incremental_parser.parse_incremental(
            parser=python_parser,
            file_path="test.py",
            new_content=content,
        )

        assert tree is not None
        assert tree.root_node.type == "module"

        # Should have cached the tree
        assert "test.py" in incremental_parser._tree_cache

    def test_parse_with_no_changes(self, python_parser):
        """Test parsing same content (should reuse or update cache)"""
        incremental_parser = IncrementalParser()

        content = """def hello():
    print('Hello')
    return True
"""

        # First parse
        tree1 = incremental_parser.parse_incremental(
            parser=python_parser,
            file_path="test.py",
            new_content=content,
        )

        # Second parse with same content and empty diff
        tree2 = incremental_parser.parse_incremental(
            parser=python_parser,
            file_path="test.py",
            new_content=content,
            old_content=content,
            diff_text="",
        )

        # Should have a tree (either same or new)
        assert tree2 is not None
        assert tree2.root_node.type == "module"
        # Tree should be cached
        assert "test.py" in incremental_parser._tree_cache

    def test_parse_with_diff(self, python_parser):
        """Test incremental parsing with actual diff"""
        incremental_parser = IncrementalParser()

        old_content = """def hello():
    print('Hello')
    return True
"""

        new_content = """def hello():
    print('Hello, World!')
    return True
"""

        diff_text = """@@ -2,1 +2,1 @@
-    print('Hello')
+    print('Hello, World!')
"""

        # First parse (cache old tree)
        tree1 = incremental_parser.parse_incremental(
            parser=python_parser,
            file_path="test.py",
            new_content=old_content,
        )

        # Incremental parse with diff
        tree2 = incremental_parser.parse_incremental(
            parser=python_parser,
            file_path="test.py",
            new_content=new_content,
            old_content=old_content,
            diff_text=diff_text,
        )

        assert tree2 is not None
        assert tree2 is not tree1  # Should be a new tree
        assert tree2.root_node.type == "module"

    def test_clear_cache_specific_file(self, python_parser):
        """Test clearing cache for specific file"""
        incremental_parser = IncrementalParser()

        content1 = "def func1(): pass"
        content2 = "def func2(): pass"

        # Parse two files
        incremental_parser.parse_incremental(python_parser, "file1.py", content1)
        incremental_parser.parse_incremental(python_parser, "file2.py", content2)

        assert "file1.py" in incremental_parser._tree_cache
        assert "file2.py" in incremental_parser._tree_cache

        # Clear only file1
        incremental_parser.clear_cache("file1.py")

        assert "file1.py" not in incremental_parser._tree_cache
        assert "file2.py" in incremental_parser._tree_cache

    def test_clear_cache_all(self, python_parser):
        """Test clearing all cached trees"""
        incremental_parser = IncrementalParser()

        content1 = "def func1(): pass"
        content2 = "def func2(): pass"

        # Parse two files
        incremental_parser.parse_incremental(python_parser, "file1.py", content1)
        incremental_parser.parse_incremental(python_parser, "file2.py", content2)

        assert len(incremental_parser._tree_cache) == 2

        # Clear all
        incremental_parser.clear_cache()

        assert len(incremental_parser._tree_cache) == 0


class TestIncrementalParsingIntegration:
    """Integration tests for incremental parsing with AstTree"""

    def test_asttree_parse_incremental(self):
        """Test AstTree.parse_incremental integration"""
        from src.foundation.parsing import AstTree, SourceFile

        old_content = """def hello():
    print('Hello')
    return True
"""

        new_content = """def hello():
    print('Hello, World!')
    return True
"""

        diff_text = """@@ -2,1 +2,1 @@
-    print('Hello')
+    print('Hello, World!')
"""

        # Create source file
        source = SourceFile(
            file_path="test.py",
            content=new_content,
            language="python",
            encoding="utf-8",
        )

        # Parse incrementally
        ast_tree = AstTree.parse_incremental(
            source,
            old_content=old_content,
            diff_text=diff_text,
        )

        assert ast_tree is not None
        assert ast_tree.root.type == "module"

        # Verify we can find function
        funcs = ast_tree.find_by_type("function_definition")
        assert len(funcs) == 1

    def test_ir_generator_incremental(self):
        """Test IR generator with incremental parsing"""
        from src.foundation.generators.python_generator import PythonIRGenerator
        from src.foundation.ir.models import NodeKind
        from src.foundation.parsing import SourceFile

        old_content = """def hello():
    print('Hello')
    return True
"""

        new_content = """def hello():
    print('Hello, World!')
    return True
"""

        diff_text = """@@ -2,1 +2,1 @@
-    print('Hello')
+    print('Hello, World!')
"""

        # Create source file
        source = SourceFile(
            file_path="test.py",
            content=new_content,
            language="python",
            encoding="utf-8",
        )

        # Generate IR with incremental parsing
        generator = PythonIRGenerator(repo_id="test-repo")
        ir_doc = generator.generate(
            source,
            snapshot_id="snap-001",
            old_content=old_content,
            diff_text=diff_text,
        )

        assert ir_doc is not None
        assert ir_doc.repo_id == "test-repo"
        assert ir_doc.snapshot_id == "snap-001"

        # Should have generated nodes (file and function)
        assert len(ir_doc.nodes) >= 2

        # Check that we have function node by kind (use NodeKind enum)
        func_nodes = [n for n in ir_doc.nodes if n.kind == NodeKind.FUNCTION]
        assert len(func_nodes) >= 1
        assert any(n.name == "hello" for n in func_nodes)
