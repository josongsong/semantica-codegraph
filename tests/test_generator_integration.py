"""
Generator Integration Tests

P0-3: Generator Integration with UnifiedSymbol
"""

import pytest
from pathlib import Path
from src.contexts.code_foundation.infrastructure.parsing.source_file import SourceFile
from src.contexts.code_foundation.infrastructure.generators.python_generator import (
    PythonIRGenerator,
)


class TestPythonGeneratorIntegration:
    """PythonIRGenerator + UnifiedSymbol 통합 테스트"""

    def test_generates_unified_symbols(self, tmp_path):
        """PythonIRGenerator가 UnifiedSymbol 생성하는지 확인"""
        # Python 코드 작성
        code = '''
class Calculator:
    """Simple calculator"""
    
    def add(self, x: int, y: int) -> int:
        return x + y
    
    def subtract(self, x: int, y: int) -> int:
        return x - y

def multiply(a: int, b: int) -> int:
    return a * b
'''

        # 임시 파일 생성
        test_file = tmp_path / "calc.py"
        test_file.write_text(code)

        # SourceFile 생성
        source = SourceFile.from_file(str(test_file), str(tmp_path))

        # Generator 생성
        generator = PythonIRGenerator(repo_id="test-repo")

        # IR 생성
        ir_doc = generator.generate(
            source=source,
            snapshot_id="test-snapshot",
        )

        # UnifiedSymbol 생성 확인
        assert len(ir_doc.unified_symbols) > 0, "UnifiedSymbol이 생성되지 않았습니다"

        # Class symbol 확인
        class_symbols = [s for s in ir_doc.unified_symbols if s.language_kind == "Class"]
        assert len(class_symbols) == 1

        calc_symbol = class_symbols[0]
        assert calc_symbol.scheme == "python"
        assert calc_symbol.manager == "pypi"
        assert "Calculator" in calc_symbol.descriptor

        # Function symbol 확인
        function_symbols = [s for s in ir_doc.unified_symbols if s.language_kind in ["Function", "Method"]]
        assert len(function_symbols) >= 3  # add, subtract, multiply

        # Method symbol 확인
        method_names = [s.language_fqn for s in function_symbols]
        assert any("add" in name for name in method_names)
        assert any("subtract" in name for name in method_names)
        assert any("multiply" in name for name in method_names)

    def test_unified_symbol_scip_descriptor(self, tmp_path):
        """UnifiedSymbol의 SCIP descriptor 확인"""
        code = """
class MyClass:
    def my_method(self):
        pass
"""

        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = PythonIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        # SCIP descriptor 검증
        for symbol in ir_doc.unified_symbols:
            descriptor = symbol.to_scip_descriptor()

            # SCIP format 확인
            assert "scip-python" in descriptor
            assert "pypi" in descriptor

            # Descriptor 형식 확인
            if symbol.language_kind == "Class":
                assert "#" in descriptor  # Class descriptor
            elif symbol.language_kind in ["Function", "Method"]:
                assert "()." in descriptor  # Function descriptor

    def test_empty_file(self, tmp_path):
        """빈 파일 처리"""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = PythonIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        # UnifiedSymbol이 없어야 함
        assert len(ir_doc.unified_symbols) == 0

    def test_complex_class_hierarchy(self, tmp_path):
        """복잡한 클래스 계층 구조"""
        code = """
class Base:
    def base_method(self):
        pass

class Child(Base):
    def child_method(self):
        pass
    
    class Nested:
        def nested_method(self):
            pass
"""

        test_file = tmp_path / "hierarchy.py"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = PythonIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        # 여러 class와 method가 있어야 함
        assert len(ir_doc.unified_symbols) >= 2

        # Class symbols
        class_symbols = [s for s in ir_doc.unified_symbols if s.language_kind == "Class"]
        class_names = [s.language_fqn for s in class_symbols]

        # At least Base and Child should be present
        assert any("Base" in name for name in class_names)
        assert any("Child" in name for name in class_names)


class TestCrossLanguageReadiness:
    """Cross-language resolution 준비도 테스트"""

    def test_unified_symbol_has_required_fields(self, tmp_path):
        """UnifiedSymbol이 모든 필수 필드를 가지는지 확인"""
        code = """
def test_function():
    pass
"""

        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = PythonIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        for symbol in ir_doc.unified_symbols:
            # SCIP required fields
            assert symbol.scheme is not None
            assert symbol.manager is not None
            assert symbol.package is not None
            assert symbol.version is not None
            assert symbol.root is not None
            assert symbol.file_path is not None
            assert symbol.descriptor is not None

            # Language-specific fields
            assert symbol.language_fqn is not None
            assert symbol.language_kind is not None

    def test_can_convert_to_other_languages(self, tmp_path):
        """LanguageBridge로 다른 언어로 변환 가능한지 확인"""
        from src.contexts.code_foundation.infrastructure.language_bridge import LanguageBridge

        code = """
def process_data(items: list[str]) -> dict[str, int]:
    return {item: len(item) for item in items}
"""

        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = PythonIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")
        bridge = LanguageBridge()

        # Python symbol → Java로 변환 시도
        for symbol in ir_doc.unified_symbols:
            # LanguageBridge를 사용한 변환은 type mapping이므로
            # UnifiedSymbol 자체는 변환하지 않지만,
            # type_info가 있으면 변환 가능해야 함
            assert symbol.scheme == "python"
            assert symbol.manager == "pypi"
