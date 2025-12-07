"""
Java 지원 검증 스크립트
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))


def verify_java_generator():
    """Java generator 가져오기 및 기본 검증"""
    try:
        from src.contexts.code_foundation.infrastructure.generators.java_generator import JavaIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import SourceFile

        print("✓ JavaIRGenerator import 성공")

        # 간단한 Java 코드
        code = """
package com.example;

public class Hello {
    public void sayHello() {
        System.out.println("Hello, Java!");
    }
}
"""

        source = SourceFile.from_content(
            file_path="Hello.java",
            content=code,
            language="java",
        )

        generator = JavaIRGenerator(repo_id="test")
        ir_doc = generator.generate(source, snapshot_id="test")

        print(f"✓ IR 생성 성공: {len(ir_doc.nodes)} nodes, {len(ir_doc.edges)} edges")

        # 노드 타입 출력
        from collections import Counter

        node_types = Counter(n.kind.value for n in ir_doc.nodes)
        print(f"  Node types: {dict(node_types)}")

        edge_types = Counter(e.kind.value for e in ir_doc.edges)
        print(f"  Edge types: {dict(edge_types)}")

        return True

    except Exception as e:
        print(f"✗ 오류 발생: {e}")
        import traceback

        traceback.print_exc()
        return False


def verify_registry():
    """ParserRegistry에 Java가 등록되어 있는지 확인"""
    try:
        from src.contexts.code_foundation.infrastructure.parsing.parser_registry import get_registry

        registry = get_registry()
        print(f"✓ ParserRegistry 지원 언어: {registry.supported_languages}")

        if registry.supports_language("java"):
            print("✓ Java 언어 지원 확인")
            return True
        else:
            print("✗ Java 언어 미지원")
            return False

    except Exception as e:
        print(f"✗ Registry 확인 실패: {e}")
        import traceback

        traceback.print_exc()
        return False


def verify_sota_builder():
    """SOTAIRBuilder에 Java가 통합되어 있는지 확인"""
    try:
        # Check if JavaIRGenerator is imported
        with open("src/contexts/code_foundation/infrastructure/ir/sota_ir_builder.py") as f:
            content = f.read()
            if "JavaIRGenerator" in content:
                print("✓ SOTAIRBuilder에 JavaIRGenerator 통합됨")
                return True
            else:
                print("✗ SOTAIRBuilder에 JavaIRGenerator 미통합")
                return False

    except Exception as e:
        print(f"✗ SOTAIRBuilder 확인 실패: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Java 지원 검증")
    print("=" * 60)

    results = []

    print("\n[1] ParserRegistry 확인")
    results.append(verify_registry())

    print("\n[2] JavaIRGenerator 확인")
    results.append(verify_java_generator())

    print("\n[3] SOTAIRBuilder 통합 확인")
    results.append(verify_sota_builder())

    print("\n" + "=" * 60)
    if all(results):
        print("✓ 모든 검증 통과!")
        sys.exit(0)
    else:
        print("✗ 일부 검증 실패")
        sys.exit(1)
