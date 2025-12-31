"""
TypeScript AST-based Type Parsing Tests (SOTA)

Tests that verify Tree-sitter AST parsing is preferred over regex fallback
for conditional types and mapped types.
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.generators.typescript_type_parser import TypeScriptTypeParser


class TestConditionalTypeASTParsing:
    """Test conditional type parsing (Issue P1)"""

    def setup_method(self):
        """Setup"""
        self.parser = TypeScriptTypeParser()

    def test_conditional_type_regex_fallback(self):
        """Regex fallback for string input"""
        type_str = "T extends U ? X : Y"

        result = self.parser.parse_conditional_type(type_str)

        assert result is not None
        assert result["kind"] == "conditional"
        assert result["check_type"] == "T"
        assert result["extends_type"] == "U"
        assert result["true_type"] == "X"
        assert result["false_type"] == "Y"

    def test_conditional_type_with_generics(self):
        """Conditional type with generic types"""
        type_str = "T extends Array<U> ? T[] : never"

        result = self.parser.parse_conditional_type(type_str)

        assert result is not None
        assert result["kind"] == "conditional"
        assert result["check_type"] == "T"
        assert result["extends_type"] == "Array<U>"
        assert result["true_type"] == "T[]"
        assert result["false_type"] == "never"

    def test_conditional_type_nested(self):
        """Nested conditional type"""
        type_str = "T extends null ? never : T extends undefined ? never : T"

        result = self.parser.parse_conditional_type(type_str)

        # First level parsed
        assert result is not None
        assert result["kind"] == "conditional"
        assert result["check_type"] == "T"
        assert result["extends_type"] == "null"
        assert result["true_type"] == "never"
        # false_type contains nested conditional
        assert "extends" in result["false_type"]

    def test_conditional_type_with_spaces(self):
        """Conditional type with extra whitespace"""
        type_str = "  T   extends   U   ?   X   :   Y  "

        result = self.parser.parse_conditional_type(type_str)

        assert result is not None
        assert result["check_type"].strip() == "T"
        assert result["extends_type"].strip() == "U"


class TestMappedTypeASTParsing:
    """Test mapped type parsing (Issue P1)"""

    def setup_method(self):
        """Setup"""
        self.parser = TypeScriptTypeParser()

    def test_mapped_type_basic(self):
        """Basic mapped type"""
        type_str = "[P in keyof T]: T[P]"

        result = self.parser.parse_mapped_type(type_str)

        assert result is not None
        assert result["kind"] == "mapped"
        assert result["type_parameter"] == "P"
        assert result["constraint"] == "keyof T"
        assert result["mapped_type"] == "T[P]"
        assert result["optional"] is False
        assert result["readonly"] is False

    def test_mapped_type_optional(self):
        """Mapped type with optional modifier"""
        type_str = "[P in keyof T]?: T[P]"

        result = self.parser.parse_mapped_type(type_str)

        assert result is not None
        assert result["optional"] is True
        assert result["readonly"] is False

    def test_mapped_type_readonly(self):
        """Mapped type with readonly modifier"""
        type_str = "readonly [P in keyof T]: T[P]"

        result = self.parser.parse_mapped_type(type_str)

        assert result is not None
        assert result["readonly"] is True
        assert result["optional"] is False

    def test_mapped_type_both_modifiers(self):
        """Mapped type with readonly and optional"""
        type_str = "readonly [P in keyof T]?: T[P]"

        result = self.parser.parse_mapped_type(type_str)

        assert result is not None
        assert result["readonly"] is True
        assert result["optional"] is True

    def test_mapped_type_union_constraint(self):
        """Mapped type with union constraint"""
        type_str = "[P in 'name' | 'age']: string"

        result = self.parser.parse_mapped_type(type_str)

        assert result is not None
        assert result["type_parameter"] == "P"
        assert "'name'" in result["constraint"]
        assert "'age'" in result["constraint"]
        assert result["mapped_type"] == "string"


class TestTreeSitterUtilsIntegration:
    """Test tree_sitter_utils.py integration"""

    def test_get_node_text_with_none(self):
        """get_node_text handles None gracefully"""
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import get_node_text

        result = get_node_text(None)

        assert result == ""

    def test_get_node_text_with_string(self):
        """get_node_text handles string input"""
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import get_node_text

        result = get_node_text("test string")

        assert result == "test string"

    def test_safe_child_by_field_with_none(self):
        """safe_child_by_field handles None gracefully"""
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import (
            safe_child_by_field,
        )

        result = safe_child_by_field(None, "name")

        assert result is None

    def test_safe_child_by_field_with_invalid_object(self):
        """safe_child_by_field handles objects without child_by_field_name"""
        from codegraph_engine.code_foundation.infrastructure.generators.utils.tree_sitter_utils import (
            safe_child_by_field,
        )

        class FakeNode:
            pass

        result = safe_child_by_field(FakeNode(), "name")

        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
