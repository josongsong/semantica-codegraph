"""
Integration test for cross-file resolution on real Python code.

This test verifies that cross-file resolution actually works on realistic
Python codebases, not just synthetic test cases.

Based on SOTA verification findings:
- Current issue: total_dependencies: 0 on real code
- Expected: Non-zero dependency graph
"""

import pytest
import tempfile
import os
from pathlib import Path


# Real Python code fixtures
REAL_CODE_FIXTURES = {
    "utils.py": """
'''Utility functions for the application.'''

def log(message: str) -> None:
    '''Log a message.'''
    print(f"[LOG] {message}")

def format_number(num: int) -> str:
    '''Format a number with commas.'''
    return f"{num:,}"

class ConfigManager:
    '''Manages application configuration.'''

    def __init__(self, config_path: str):
        self.config_path = config_path

    def load(self) -> dict:
        '''Load configuration from file.'''
        return {}
""",
    "helpers.py": """
'''Helper functions that use utilities.'''

from utils import log, format_number

def process_data(data: list) -> None:
    '''Process a list of data.'''
    log(f"Processing {format_number(len(data))} items")
    for item in data:
        log(f"Item: {item}")

def validate_input(value: str) -> bool:
    '''Validate user input.'''
    if not value:
        log("Empty input detected")
        return False
    return True
""",
    "main.py": """
'''Main application entry point.'''

from utils import ConfigManager, log
from helpers import process_data, validate_input

def main():
    '''Run the application.'''
    log("Starting application")

    config = ConfigManager("config.json")
    settings = config.load()

    data = ["item1", "item2", "item3"]
    if validate_input(str(data)):
        process_data(data)

    log("Application finished")

if __name__ == "__main__":
    main()
""",
}


@pytest.fixture
def temp_codebase():
    """Create a temporary directory with real Python code."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Write fixture files
        for filename, content in REAL_CODE_FIXTURES.items():
            filepath = tmpdir / filename
            filepath.write_text(content)

        yield tmpdir


def test_cross_file_resolution_real_code(temp_codebase):
    """
    Test cross-file resolution on realistic Python code.

    This is the CRITICAL test that must pass for SOTA certification.
    """
    try:
        import codegraph_ir
    except ImportError:
        pytest.skip("codegraph_ir Rust module not available")

    # Prepare IR documents (simplified - would normally use full pipeline)
    files = []
    for filepath in temp_codebase.glob("*.py"):
        content = filepath.read_text()
        module_path = filepath.stem  # Simple module path

        files.append(
            {
                "file_path": str(filepath),
                "content": content,
                "module_path": module_path,
            }
        )

    # Build global context
    result = codegraph_ir.build_global_context_py(files)

    # CRITICAL ASSERTIONS - These MUST pass
    assert result["total_files"] == 3, "Should have 3 files"
    assert result["total_symbols"] > 0, "Should have symbols"
    assert result["total_imports"] > 0, "Should have imports"

    # THIS IS THE FAILING ASSERTION per SOTA verification
    assert result["total_dependencies"] > 0, (
        "CRITICAL: total_dependencies is 0! Cross-file resolution is broken. "
        "This is the #1 blocker for SOTA certification."
    )

    # Verify specific symbols exist
    symbol_table = result["symbol_table"]
    assert "utils.log" in symbol_table, "utils.log should be in symbol table"
    assert "helpers.process_data" in symbol_table
    assert "main.main" in symbol_table

    # Verify symbol kinds
    assert symbol_table["utils.log"]["kind"] == "function"
    assert symbol_table["utils.ConfigManager"]["kind"] == "class"

    # Verify dependency graph structure
    deps = result["file_dependencies"]

    # main.py depends on utils.py and helpers.py
    main_deps = deps.get("main.py", [])
    assert "utils.py" in main_deps, "main.py should depend on utils.py"
    assert "helpers.py" in main_deps, "main.py should depend on helpers.py"

    # helpers.py depends on utils.py
    helpers_deps = deps.get("helpers.py", [])
    assert "utils.py" in helpers_deps, "helpers.py should depend on utils.py"

    # utils.py has no dependencies
    utils_deps = deps.get("utils.py", [])
    assert len(utils_deps) == 0, "utils.py should have no dependencies"

    print(f"\n✅ Cross-file resolution WORKS on real code!")
    print(f"   Symbols: {result['total_symbols']}")
    print(f"   Imports: {result['total_imports']}")
    print(f"   Dependencies: {result['total_dependencies']}")


def test_cross_file_resolution_complex_imports():
    """Test more complex import patterns."""
    try:
        import codegraph_ir
    except ImportError:
        pytest.skip("codegraph_ir Rust module not available")

    complex_code = {
        "base.py": """
class BaseClass:
    def method(self):
        pass
""",
        "derived.py": """
from base import BaseClass

class DerivedClass(BaseClass):
    def method(self):
        super().method()
""",
        "using.py": """
from derived import DerivedClass
from base import BaseClass

def use_classes():
    obj1 = BaseClass()
    obj2 = DerivedClass()
    obj2.method()
""",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        files = []
        for filename, content in complex_code.items():
            filepath = tmpdir / filename
            filepath.write_text(content)
            files.append(
                {
                    "file_path": str(filepath),
                    "content": content,
                    "module_path": filepath.stem,
                }
            )

        result = codegraph_ir.build_global_context_py(files)

        # Should detect inheritance relationship
        assert result["total_dependencies"] >= 2, "Should have at least 2 dependencies: derived → base, using → derived"

        # Verify class symbols
        symbol_table = result["symbol_table"]
        assert "base.BaseClass" in symbol_table
        assert "derived.DerivedClass" in symbol_table


def test_cross_file_resolution_circular_imports():
    """Test handling of circular imports (Python allows this)."""
    try:
        import codegraph_ir
    except ImportError:
        pytest.skip("codegraph_ir Rust module not available")

    circular_code = {
        "a.py": """
from b import func_b

def func_a():
    return func_b()
""",
        "b.py": """
from a import func_a

def func_b():
    return func_a()
""",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        files = []
        for filename, content in circular_code.items():
            filepath = tmpdir / filename
            filepath.write_text(content)
            files.append(
                {
                    "file_path": str(filepath),
                    "content": content,
                    "module_path": filepath.stem,
                }
            )

        result = codegraph_ir.build_global_context_py(files)

        # Should detect circular dependency
        assert result["total_dependencies"] >= 2, "Should detect circular deps"

        # Both files should depend on each other
        deps = result["file_dependencies"]
        assert "b.py" in deps.get("a.py", [])
        assert "a.py" in deps.get("b.py", [])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
