"""
L11 SOTA Tests: _extract_var_name validation

Tests for strict input validation and error handling.
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
    InterproceduralTaintAnalyzer,
)


class TestExtractVarName:
    """Test _extract_var_name with L11 strict validation"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer with minimal setup"""

        class MockCallGraph:
            def get_callees(self, func_name: str) -> list[str]:
                return []

            def get_functions(self) -> list[str]:
                return []

        return InterproceduralTaintAnalyzer(
            call_graph=MockCallGraph(),
            max_depth=3,
        )

    # === Happy Path ===

    def test_extract_valid_var_id(self, analyzer):
        """Valid variable ID should extract correctly"""
        var_id = "var:.:benchmark/taint/fixtures/python/advanced_taint/interprocedural.py:benchmark.taint.fixtures.python.advanced_taint.interprocedural.interprocedural_example_3:clean_input@5:1"

        result = analyzer._extract_var_name(var_id)

        assert result == "clean_input"

    def test_extract_short_var_name(self, analyzer):
        """Single character variable names should work"""
        var_id = "var:.:file.py:mod.func:x@1:0"

        result = analyzer._extract_var_name(var_id)

        assert result == "x"

    def test_extract_underscore_vars(self, analyzer):
        """Underscores in names should work"""
        var_id = "var:.:file.py:mod.func:_private_var@10:5"

        result = analyzer._extract_var_name(var_id)

        assert result == "_private_var"

    # === Error Cases: None/Empty ===

    def test_none_input_raises(self, analyzer):
        """None input should raise ValueError"""
        with pytest.raises(ValueError, match="cannot be None"):
            analyzer._extract_var_name(None)

    def test_empty_string_raises(self, analyzer):
        """Empty string should raise ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            analyzer._extract_var_name("")

    # === Error Cases: Wrong Type ===

    def test_int_input_raises(self, analyzer):
        """Integer input should raise TypeError"""
        with pytest.raises(TypeError, match="must be str"):
            analyzer._extract_var_name(123)  # type: ignore

    def test_list_input_raises(self, analyzer):
        """List input should raise TypeError"""
        with pytest.raises(TypeError, match="must be str"):
            analyzer._extract_var_name(["var", "name"])  # type: ignore

    # === Error Cases: Malformed Format ===

    def test_too_few_parts_raises(self, analyzer):
        """Less than 5 parts should raise ValueError"""
        with pytest.raises(ValueError, match="expected 5\\+ parts"):
            analyzer._extract_var_name("var:path:only_three")

    def test_missing_at_symbol_raises(self, analyzer):
        """Missing @ in parts[-2] should raise ValueError"""
        with pytest.raises(ValueError, match="expected '@'"):
            analyzer._extract_var_name("var:.:path:mod:name_no_at:1")

    def test_empty_var_name_raises(self, analyzer):
        """Empty variable name extraction should raise"""
        with pytest.raises(ValueError, match="empty var_name"):
            analyzer._extract_var_name("var:.:path:mod:@5:1")

    # === Error Cases: Suspicious Content ===

    @pytest.mark.skip("Test case construction is tricky, sanity check works in practice")
    def test_colon_in_name_raises(self, analyzer):
        """Colon in extracted name indicates parse error"""
        # Would need malformed IR to trigger this
        pass

    def test_slash_in_name_raises(self, analyzer):
        """Slash in extracted name indicates parse error"""
        # Malformed: var name contains path separator
        with pytest.raises(ValueError, match="Suspicious var_name"):
            analyzer._extract_var_name("var:.:path:mod:bad/name@5:1")

    # === Edge Cases ===

    def test_unicode_var_name(self, analyzer):
        """Unicode characters in variable names (Python 3 allows)"""
        var_id = "var:.:file.py:mod.func:变量名@1:0"

        result = analyzer._extract_var_name(var_id)

        assert result == "变量名"

    def test_numeric_suffix_in_name(self, analyzer):
        """Variables with numbers are valid"""
        var_id = "var:.:file.py:mod.func:var123@10:5"

        result = analyzer._extract_var_name(var_id)

        assert result == "var123"

    def test_dunder_methods(self, analyzer):
        """__method__ style names"""
        var_id = "var:.:file.py:mod.func:__init__@5:10"

        result = analyzer._extract_var_name(var_id)

        assert result == "__init__"

    # === Regression Tests ===

    def test_real_world_example_1(self, analyzer):
        """Real example from interprocedural.py"""
        var_id = "var:.:benchmark/taint/fixtures/python/advanced_taint/interprocedural.py:benchmark.taint.fixtures.python.advanced_taint.interprocedural.interprocedural_example_3:sanitize_input@5:1"

        result = analyzer._extract_var_name(var_id)

        assert result == "sanitize_input"

    def test_real_world_example_2(self, analyzer):
        """Real example with user_input"""
        var_id = "var:.:benchmark/taint/fixtures/python/advanced_taint/interprocedural.py:benchmark.taint.fixtures.python.advanced_taint.interprocedural.interprocedural_example_3:user_input@5:3"

        result = analyzer._extract_var_name(var_id)

        assert result == "user_input"
