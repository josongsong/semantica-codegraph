"""
Tests for Pyright Integration

Tests the integration of Pyright type checker with IR generation.
"""

import tempfile
from pathlib import Path

import pytest

from src.contexts.code_foundation.infrastructure.ir.lsp.pyright import PyrightAdapter
from src.foundation.generators.python_generator import PythonIRGenerator
from src.foundation.ir.external_analyzers import PyrightExternalAnalyzer
from src.foundation.parsing import SourceFile
from src.foundation.semantic_ir.typing.models import TypeResolutionLevel


@pytest.fixture
def temp_project():
    """Create a temporary project directory"""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)

        # Create pyrightconfig.json
        config = project_root / "pyrightconfig.json"
        config.write_text(
            """{
  "typeCheckingMode": "basic",
  "pythonVersion": "3.10"
}"""
        )

        yield project_root


@pytest.fixture
def sample_code():
    """Sample Python code with type annotations"""
    return """
def add(x: int, y: int) -> int:
    return x + y

def greet(name: str) -> str:
    return f"Hello, {name}"

class Calculator:
    def multiply(self, a: int, b: int) -> int:
        return a * b
"""


def test_pyright_adapter_basic(temp_project, sample_code):
    """Test basic Pyright adapter functionality"""
    # Create source file
    src_file = temp_project / "main.py"
    src_file.write_text(sample_code)

    # Initialize Pyright adapter
    adapter = PyrightAdapter(temp_project)

    # Analyze file (this will actually run pyright if available)
    type_infos = adapter.analyze_file(src_file)

    # We can't guarantee pyright is installed, so this test is lenient
    # Just check that the method doesn't crash
    assert isinstance(type_infos, list)

    # Clean up
    adapter.shutdown()


def test_type_resolver_with_pyright(temp_project, sample_code):
    """Test TypeResolver with Pyright integration"""
    from src.foundation.semantic_ir.typing.resolver import TypeResolver

    # Create source file
    src_file = temp_project / "main.py"
    src_file.write_text(sample_code)

    # Initialize Pyright adapter
    adapter = PyrightExternalAnalyzer(temp_project)

    # Create TypeResolver with external analyzer
    resolver = TypeResolver("test-repo", external_analyzer=adapter)

    # Test basic type resolution (should work without Pyright)
    type_entity = resolver.resolve_type("int")
    assert type_entity.resolution_level == TypeResolutionLevel.BUILTIN

    # Test complex type
    type_entity = resolver.resolve_type("list[str]")
    assert "list" in type_entity.raw or "List" in type_entity.raw

    # Clean up
    adapter.shutdown()


def test_ir_generator_with_pyright(temp_project, sample_code):
    """Test IR generation with Pyright"""
    # Create source file
    src_file = temp_project / "main.py"
    src_file.write_text(sample_code)

    # Initialize Pyright adapter
    adapter = PyrightExternalAnalyzer(temp_project)

    # Create IR generator with external analyzer
    generator = PythonIRGenerator("test-repo", external_analyzer=adapter)

    # Generate IR
    source = SourceFile(str(src_file), sample_code, "python")
    ir_doc = generator.generate(source, "snapshot-1")

    # Verify IR was generated
    assert ir_doc is not None
    assert len(ir_doc.nodes) > 0

    # Check that types were collected
    assert len(ir_doc.types) > 0

    # Find the 'add' function
    add_func = next((n for n in ir_doc.nodes if n.name == "add"), None)
    assert add_func is not None

    # Check signature
    if add_func.signature_id:
        signature = next((s for s in ir_doc.signatures if s.id == add_func.signature_id), None)
        assert signature is not None
        # Should have parameter types
        assert signature.parameter_type_ids is not None

    # Clean up
    adapter.shutdown()


def test_pyright_not_available():
    """Test graceful degradation when Pyright is not available"""
    from src.foundation.semantic_ir.typing.resolver import TypeResolver

    # Use invalid pyright path
    adapter = PyrightExternalAnalyzer(Path("/tmp"))

    # TypeResolver should still work (fallback to internal resolution)
    resolver = TypeResolver("test-repo", external_analyzer=adapter)

    # Basic resolution should still work
    type_entity = resolver.resolve_type("int")
    assert type_entity.resolution_level == TypeResolutionLevel.BUILTIN

    adapter.shutdown()


def test_type_resolution_levels():
    """Test different type resolution levels"""
    from src.foundation.semantic_ir.typing.models import TypeFlavor, TypeResolutionLevel
    from src.foundation.semantic_ir.typing.resolver import TypeResolver

    resolver = TypeResolver("test-repo")

    # RAW level (unknown type)
    unknown_type = resolver.resolve_type("UnknownType")
    assert unknown_type.resolution_level == TypeResolutionLevel.RAW
    assert unknown_type.flavor == TypeFlavor.EXTERNAL

    # BUILTIN level
    int_type = resolver.resolve_type("int")
    assert int_type.resolution_level == TypeResolutionLevel.BUILTIN
    assert int_type.flavor == TypeFlavor.BUILTIN

    # LOCAL level (register local class)
    resolver.register_local_class("MyClass", "node:123")
    local_type = resolver.resolve_type("MyClass")
    assert local_type.resolution_level == TypeResolutionLevel.LOCAL
    assert local_type.flavor == TypeFlavor.USER
    assert local_type.resolved_target == "node:123"


def test_pyright_caching(temp_project, sample_code):
    """Test that Pyright results are cached"""
    # Create source file
    src_file = temp_project / "main.py"
    src_file.write_text(sample_code)

    # Initialize adapter
    adapter = PyrightAdapter(temp_project)

    # First call
    result1 = adapter.analyze_file(src_file)

    # Second call (should use cache)
    result2 = adapter.analyze_file(src_file)

    # Results should be identical
    assert result1 == result2

    # Cache should contain the file
    cache_key = str(src_file.resolve())
    assert cache_key in adapter._cache

    adapter.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
