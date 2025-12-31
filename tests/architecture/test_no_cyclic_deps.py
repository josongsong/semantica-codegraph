"""
Architecture Tests - Cyclic Dependency Prevention

RFC-021 Phase 0: Ensure no cyclic dependencies between contexts
"""

import ast
from pathlib import Path

import pytest


def test_no_code_foundation_imports_reasoning_engine_models():
    """code_foundation이 reasoning_engine의 모델을 직접 import하지 않음 (구현체는 허용)"""
    violations = []
    code_foundation_path = Path("src/contexts/code_foundation")

    if not code_foundation_path.exists():
        pytest.skip("code_foundation not found")

    # Forbidden: reasoning_engine의 모델 import (shared_kernel로 이동됨)
    forbidden_patterns = [
        "reasoning_engine.infrastructure.pdg.models",
        "reasoning_engine.infrastructure.slicer.slicer.SliceResult",
        "reasoning_engine.infrastructure.slicer.slicer.SliceConfig",
        "reasoning_engine.infrastructure.slicer.slicer.CodeFragment",
        "reasoning_engine.domain.models.SliceResult",
    ]

    for py_file in code_foundation_path.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    module = getattr(node, "module", None)
                    if module:
                        # Check if importing models from reasoning_engine
                        for pattern in forbidden_patterns:
                            if pattern in module:
                                violations.append(f"{py_file}:{node.lineno} imports {module}")
                                break
                        # Also check if importing PDGNode/PDGEdge from pdg_builder
                        if "pdg_builder" in module and isinstance(node, ast.ImportFrom):
                            for alias in node.names:
                                if alias.name in ("PDGNode", "PDGEdge", "DependencyType"):
                                    violations.append(
                                        f"{py_file}:{node.lineno} imports {alias.name} from {module} "
                                        f"(should use shared_kernel)"
                                    )
        except SyntaxError:
            continue

    assert not violations, "Cyclic dependency - models should come from shared_kernel:\n" + "\n".join(violations)


def test_shared_kernel_stdlib_only():
    """shared_kernel은 stdlib만 import (relative imports 제외)"""
    shared_kernel_path = Path("src/contexts/shared_kernel")

    if not shared_kernel_path.exists():
        pytest.skip("shared_kernel not found")

    violations = []
    allowed_prefixes = ("typing", "dataclasses", "enum", "abc")

    for py_file in shared_kernel_path.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module = node.module
                    # Allow relative imports (module is None or empty)
                    if module and not module.startswith(allowed_prefixes) and module.startswith("src."):
                        violations.append(f"{py_file}:{node.lineno} imports {module}")
        except SyntaxError:
            continue

    assert not violations, "shared_kernel has illegal imports:\n" + "\n".join(violations)


def test_shared_kernel_no_implementation():
    """shared_kernel에 실제 구현 코드가 없는지 확인"""
    shared_kernel_path = Path("src/contexts/shared_kernel")

    if not shared_kernel_path.exists():
        pytest.skip("shared_kernel not found")

    violations = []

    for py_file in shared_kernel_path.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                # Check for classes with actual methods (not just __init__)
                if isinstance(node, ast.ClassDef):
                    # Allow dataclass and Enum
                    is_dataclass = any(
                        dec.id == "dataclass" if isinstance(dec, ast.Name) else False for dec in node.decorator_list
                    )
                    is_enum = any(base.id == "Enum" if isinstance(base, ast.Name) else False for base in node.bases)
                    is_protocol = any(
                        base.id == "Protocol" if isinstance(base, ast.Name) else False for base in node.bases
                    )

                    if not (is_dataclass or is_enum or is_protocol):
                        methods = [
                            f for f in node.body if isinstance(f, ast.FunctionDef) and not f.name.startswith("__")
                        ]
                        if methods:
                            violations.append(
                                f"{py_file}: Class {node.name} has implementation methods: {[m.name for m in methods]}"
                            )

        except SyntaxError:
            continue

    assert not violations, "shared_kernel has implementation code:\n" + "\n".join(violations)


def test_reasoning_engine_uses_shared_kernel():
    """reasoning_engine이 shared_kernel을 사용하는지 확인"""
    # pdg_builder.py와 slicer.py가 shared_kernel을 import하는지 확인
    pdg_builder = Path("src/contexts/reasoning_engine/infrastructure/pdg/pdg_builder.py")
    slicer = Path("src/contexts/reasoning_engine/infrastructure/slicer/slicer.py")

    if not pdg_builder.exists() or not slicer.exists():
        pytest.skip("reasoning_engine files not found")

    # Check pdg_builder.py
    pdg_content = pdg_builder.read_text(encoding="utf-8")
    assert "from codegraph_engine.shared_kernel.pdg" in pdg_content, "pdg_builder.py should import from shared_kernel"

    # Check slicer.py
    slicer_content = slicer.read_text(encoding="utf-8")
    assert "from codegraph_engine.shared_kernel.slice" in slicer_content, "slicer.py should import from shared_kernel"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
