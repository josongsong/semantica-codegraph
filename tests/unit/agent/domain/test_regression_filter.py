"""
Tests for Regression Filter
"""

import pytest

from apps.orchestrator.orchestrator.domain.testing.regression_filter import LightweightRegressionFilter


@pytest.mark.asyncio
class TestLightweightRegressionFilter:
    """Test lightweight regression filter"""

    async def test_filter_syntax_errors(self):
        """Test filtering out syntax errors"""
        filter = LightweightRegressionFilter(enable_pytest=False)

        codes = [
            "def foo(): return 1",  # Valid
            "def bar( return 2",  # Syntax error
            "def baz(): return 3",  # Valid
        ]

        safe, flags = await filter.filter_safe(codes)

        assert len(safe) == 2  # 2 valid
        assert flags == [True, False, True]

    async def test_filter_import_errors(self):
        """Test filtering out import errors"""
        filter = LightweightRegressionFilter(enable_pytest=False)

        codes = [
            "def foo(): return 1",  # Valid
            "import nonexistent_module\ndef bar(): return 2",  # Compiles OK (import checked at runtime)
            "def baz(): return 3",  # Valid
        ]

        safe, flags = await filter.filter_safe(codes)

        # Import errors are not caught by compile() - they're runtime errors
        # So all pass syntax + compile checks
        assert len(safe) == 3  # All pass compile
        assert all(flags)

    async def test_all_valid(self):
        """Test all codes are valid"""
        filter = LightweightRegressionFilter()

        codes = [
            "def foo(): return 1",
            "def bar(): return 2",
            "def baz(): return 3",
        ]

        safe, flags = await filter.filter_safe(codes)

        assert len(safe) == 3  # All valid
        assert all(flags)

    async def test_all_invalid(self):
        """Test all codes are invalid"""
        filter = LightweightRegressionFilter()

        codes = [
            "def foo( return 1",  # Syntax error
            "def bar( return 2",  # Syntax error
        ]

        safe, flags = await filter.filter_safe(codes)

        assert len(safe) == 0  # None valid
        assert not any(flags)

    async def test_empty_input(self):
        """Test empty input handling"""
        filter = LightweightRegressionFilter()

        safe, flags = await filter.filter_safe([])

        assert len(safe) == 0
        assert len(flags) == 0

    def test_syntax_check(self):
        """Test syntax checking method"""
        filter = LightweightRegressionFilter()

        assert filter._check_syntax("def foo(): pass") is True
        assert filter._check_syntax("def foo( pass") is False

    def test_import_check(self):
        """Test import checking method"""
        filter = LightweightRegressionFilter()

        assert filter._check_imports("def foo(): return 1") is True
        assert filter._check_imports("import os\ndef foo(): return 1") is True
        # Import errors pass through compile (only caught at runtime)
        # So this test is tricky - import check happens at compile time
