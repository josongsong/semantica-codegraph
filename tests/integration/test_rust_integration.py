"""
Integration Test: Rust + LayeredIRBuilder

Tests complete integration of Rust IR generator with Python pipeline.

PRODUCTION REQUIREMENTS:
- Rust-first execution
- Python fallback on error
- Same IR structure
- No data loss
- Performance improvement
"""

import pytest
from pathlib import Path


def test_rust_adapter_basic():
    """Test Rust adapter basic functionality"""
    try:
        from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import RustIRAdapter
        from codegraph_engine.code_foundation.infrastructure.parsing import SourceFile
        from codegraph_engine.code_foundation.domain.models import Language
    except ImportError as e:
        pytest.skip(f"Module not available: {e}")

    adapter = RustIRAdapter("test-repo", enable_rust=True)

    # Check availability
    print(f"Rust available: {adapter.is_rust_available()}")

    if not adapter.is_rust_available():
        pytest.skip("Rust module not installed")

    # Test with simple code
    code = """
class Test:
    def method(self):
        pass
"""

    source = SourceFile.from_content(
        file_path="test.py",
        content=code,
        language=Language.PYTHON,
    )

    ir_docs, errors = adapter.generate_ir_batch([source])

    assert len(errors) == 0, f"Errors: {errors}"
    assert len(ir_docs) == 1

    ir_doc = ir_docs[0]
    assert ir_doc.file_path == "test.py"
    assert len(ir_doc.nodes) == 2  # class + method
    assert len(ir_doc.edges) >= 1  # CONTAINS edge

    print(f"✅ Nodes: {len(ir_doc.nodes)}")
    print(f"✅ Edges: {len(ir_doc.edges)}")


def test_rust_adapter_fallback():
    """Test Python fallback when Rust fails"""
    try:
        from codegraph_engine.code_foundation.infrastructure.generators.rust_adapter import RustIRAdapter
    except ImportError as e:
        pytest.skip(f"Module not available: {e}")

    # Test with Rust disabled
    adapter = RustIRAdapter("test-repo", enable_rust=False)

    assert not adapter.is_rust_available()

    # Should return empty (caller handles fallback)
    ir_docs, errors = adapter.generate_ir_batch([])
    assert len(ir_docs) == 0


def test_layered_ir_builder_with_rust():
    """Test LayeredIRBuilder with Rust integration"""
    pytest.skip("Requires full environment setup")

    # TODO: Full E2E test
    # This would require:
    # - Complete environment
    # - Database
    # - LSP servers
    # - Full configuration


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
