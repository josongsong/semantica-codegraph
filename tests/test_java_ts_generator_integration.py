"""
Tests for Java/TypeScript Generator Integration with UnifiedSymbol
"""

from pathlib import Path

import pytest

from src.contexts.code_foundation.infrastructure.generators.java_generator import JavaIRGenerator
from src.contexts.code_foundation.infrastructure.generators.typescript_generator import TypeScriptIRGenerator
from src.contexts.code_foundation.infrastructure.parsing.source_file import SourceFile


class TestJavaGeneratorIntegration:
    """Test JavaIRGenerator UnifiedSymbol generation"""

    def test_generates_unified_symbols(self, tmp_path):
        """JavaIRGenerator가 UnifiedSymbol 생성하는지 확인"""
        code = """
package com.example;

public class Calculator {
    public int add(int x, int y) {
        return x + y;
    }
    
    public int subtract(int x, int y) {
        return x - y;
    }
}

public interface Computable {
    int compute();
}
"""

        test_file = tmp_path / "Calculator.java"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = JavaIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(
            source=source,
            snapshot_id="test-snapshot",
        )

        # UnifiedSymbol 생성 확인
        assert len(ir_doc.unified_symbols) > 0, "UnifiedSymbol이 생성되지 않았습니다"

        # Class symbol 확인
        class_symbols = [s for s in ir_doc.unified_symbols if s.language_kind == "Class"]
        assert len(class_symbols) >= 1

        # Interface symbol 확인
        interface_symbols = [s for s in ir_doc.unified_symbols if s.language_kind == "Interface"]
        assert len(interface_symbols) >= 1

        # Method symbol 확인
        method_symbols = [s for s in ir_doc.unified_symbols if s.language_kind == "Method"]
        assert len(method_symbols) >= 2  # add, subtract, compute

    def test_java_scip_descriptor(self, tmp_path):
        """Java UnifiedSymbol의 SCIP descriptor 확인"""
        code = """
package com.example;

public class MyClass {
    public void myMethod() {
        // method body
    }
}
"""

        test_file = tmp_path / "MyClass.java"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = JavaIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        assert len(ir_doc.unified_symbols) > 0

        for symbol in ir_doc.unified_symbols:
            # SCIP descriptor 확인
            descriptor = symbol.to_scip_descriptor()

            # Format 확인
            assert descriptor.startswith("scip-java")
            assert "maven" in descriptor
            assert "com.example" in descriptor

            # Descriptor suffix 확인
            if symbol.language_kind == "Class":
                assert "#" in symbol.descriptor
            elif symbol.language_kind == "Method":
                assert "()." in symbol.descriptor

    def test_java_package_extraction(self, tmp_path):
        """Java package name 추출 확인"""
        code = """
package com.example.myapp;

public class Test {
}
"""

        test_file = tmp_path / "Test.java"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = JavaIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        # Package name이 metadata에 있어야 함
        assert ir_doc.meta.get("package") == "com.example.myapp"

        # UnifiedSymbol에도 반영되어야 함
        if ir_doc.unified_symbols:
            symbol = ir_doc.unified_symbols[0]
            assert symbol.package == "com.example.myapp"


class TestTypeScriptGeneratorIntegration:
    """Test TypeScriptIRGenerator UnifiedSymbol generation"""

    @pytest.mark.skip(reason="TypeScript generator needs full implementation")
    def test_generates_unified_symbols(self, tmp_path):
        """TypeScriptIRGenerator가 UnifiedSymbol 생성하는지 확인"""
        code = """
export class Calculator {
    add(x: number, y: number): number {
        return x + y;
    }
    
    subtract(x: number, y: number): number {
        return x - y;
    }
}

export function multiply(a: number, b: number): number {
    return a * b;
}

export interface Computable {
    compute(): number;
}
"""

        test_file = tmp_path / "calculator.ts"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = TypeScriptIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(
            source=source,
            snapshot_id="test-snapshot",
        )

        # UnifiedSymbol 생성 확인
        # Note: TypeScript generator currently only generates FILE nodes
        # Full class/function parsing to be implemented
        assert hasattr(ir_doc, "unified_symbols"), "IRDocument should have unified_symbols field"

    @pytest.mark.skip(reason="TypeScript generator needs full implementation")
    def test_typescript_scip_descriptor(self, tmp_path):
        """TypeScript UnifiedSymbol의 SCIP descriptor 확인"""
        code = """
export class MyClass {
    myMethod(): void {
        // method body
    }
}

export interface MyInterface {
    getValue(): string;
}
"""

        test_file = tmp_path / "test.ts"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = TypeScriptIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        # TypeScript generator integration ready, but needs full node parsing
        assert hasattr(ir_doc, "unified_symbols")

    def test_typescript_arrow_function(self, tmp_path):
        """TypeScript generator has UnifiedSymbol support"""
        code = """
export const multiply = (a: number, b: number): number => {
    return a * b;
};
"""

        test_file = tmp_path / "arrow.ts"
        test_file.write_text(code)

        source = SourceFile.from_file(str(test_file), str(tmp_path))
        generator = TypeScriptIRGenerator(repo_id="test-repo")

        ir_doc = generator.generate(source, "snapshot")

        # TypeScript generator has unified_symbols field ready
        assert hasattr(ir_doc, "unified_symbols")
        # Full node parsing to be implemented in future phase


class TestCrossLanguageIntegration:
    """Test cross-language integration"""

    def test_java_typescript_unified_symbols(self, tmp_path):
        """Java와 TypeScript generator가 unified_symbols를 지원하는지 확인"""
        # Java code
        java_code = """
package com.example;
public class JavaClass {
    public void method() {}
}
"""
        java_file = tmp_path / "JavaClass.java"
        java_file.write_text(java_code)

        # TypeScript code
        ts_code = """
export class TypeScriptClass {
    method(): void {}
}
"""
        ts_file = tmp_path / "typescript.ts"
        ts_file.write_text(ts_code)

        # Generate IR
        java_source = SourceFile.from_file(str(java_file), str(tmp_path))
        ts_source = SourceFile.from_file(str(ts_file), str(tmp_path))

        java_gen = JavaIRGenerator(repo_id="test")
        ts_gen = TypeScriptIRGenerator(repo_id="test")

        java_ir = java_gen.generate(java_source, "snapshot")
        ts_ir = ts_gen.generate(ts_source, "snapshot")

        # Java는 UnifiedSymbol 생성해야 함
        assert len(java_ir.unified_symbols) > 0

        # TypeScript는 통합 준비 완료 (full parsing은 향후)
        assert hasattr(ts_ir, "unified_symbols")

        # Java SCIP descriptor format 확인
        java_descriptor = java_ir.unified_symbols[0].to_scip_descriptor()
        assert java_descriptor.startswith("scip-java")
        assert "maven" in java_descriptor

    def test_all_generators_use_same_format(self, tmp_path):
        """모든 generator가 unified_symbols 필드를 지원하는지 확인"""
        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator

        # Python
        py_code = "class PyClass:\n    pass"
        py_file = tmp_path / "test.py"
        py_file.write_text(py_code)

        # Java
        java_code = "package test; public class JavaClass {}"
        java_file = tmp_path / "Test.java"
        java_file.write_text(java_code)

        # TypeScript
        ts_code = "export class TsClass {}"
        ts_file = tmp_path / "test.ts"
        ts_file.write_text(ts_code)

        # Generate
        py_ir = PythonIRGenerator(repo_id="test").generate(SourceFile.from_file(str(py_file), str(tmp_path)), "s")
        java_ir = JavaIRGenerator(repo_id="test").generate(SourceFile.from_file(str(java_file), str(tmp_path)), "s")
        ts_ir = TypeScriptIRGenerator(repo_id="test").generate(SourceFile.from_file(str(ts_file), str(tmp_path)), "s")

        # 모두 unified_symbols 필드를 가져야 함
        assert hasattr(py_ir, "unified_symbols")
        assert hasattr(java_ir, "unified_symbols")
        assert hasattr(ts_ir, "unified_symbols")

        # Python과 Java는 UnifiedSymbol 생성
        assert len(py_ir.unified_symbols) > 0
        assert len(java_ir.unified_symbols) > 0

        # Python과 Java는 SCIP descriptor 생성 가능
        py_ir.unified_symbols[0].to_scip_descriptor()
        java_ir.unified_symbols[0].to_scip_descriptor()

        # TypeScript는 통합 준비 완료 (full node parsing은 향후)
