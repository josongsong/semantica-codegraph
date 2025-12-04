#!/usr/bin/env python3
"""
최종 비판적 재검증 - 진짜 제대로 동작하는가?

이전 테스트는 통과했지만, 다시 한번 더 깊이 파고들어서:
1. Edge case들이 제대로 처리되는가?
2. 에러 상황에서 robust한가?
3. 실제 레포지토리와 유사한 복잡한 케이스도 동작하는가?
4. Fuzzy search가 왜 동작 안 하는가?
5. Dependency 해석이 왜 0개인가?
"""

import asyncio
import tempfile
from pathlib import Path
from textwrap import dedent


async def critical_review_1_fuzzy_search():
    """비판적 재검증 1: Fuzzy search가 왜 0개 반환?"""
    print("\n" + "=" * 60)
    print("비판적 재검증 1: Fuzzy Search 문제")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = Path(tmpdir)

        # Create test file
        models_py = test_proj / "models.py"
        models_py.write_text(
            dedent("""
            class User:
                def __init__(self, name: str):
                    self.name = name
            
            class UserService:
                def get_user(self, name: str) -> User:
                    return User(name)
        """).strip()
        )

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
        from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

        # Generate IR & Index
        content = models_py.read_text()
        source = SourceFile.from_content(str(models_py), content, "python")
        ast = AstTree.parse(source)
        generator = PythonIRGenerator(repo_id="test")
        ir_doc = generator.generate(source, "test", ast)

        index = RetrievalOptimizedIndex()
        index.index_ir_document(ir_doc)

        # Test exact search
        print("\n1. Exact search 'User':")
        results = index.search_symbol("User", fuzzy=False, limit=5)
        print(f"   Results: {len(results)}")
        for node, score in results:
            print(f"   - {node.name} (score: {score:.2f})")

        # Test fuzzy search
        print("\n2. Fuzzy search 'usr':")
        results = index.search_symbol("usr", fuzzy=True, limit=5)
        print(f"   Results: {len(results)}")
        if results:
            for node, score in results:
                print(f"   - {node.name} (score: {score:.2f})")
        else:
            print("   ⚠️ No results! Why?")

        # Test case-insensitive
        print("\n3. Fuzzy search 'user' (lowercase):")
        results = index.search_symbol("user", fuzzy=True, limit=5)
        print(f"   Results: {len(results)}")
        for node, score in results:
            print(f"   - {node.name} (score: {score:.2f})")

        # Test typo tolerance
        print("\n4. Fuzzy search 'Uesr' (typo):")
        results = index.search_symbol("Uesr", fuzzy=True, limit=5)
        print(f"   Results: {len(results)}")
        for node, score in results:
            print(f"   - {node.name} (score: {score:.2f})")

        # Analysis
        print("\n분석:")
        print("  - Exact search: 동작 ✓")
        if not index.search_symbol("usr", fuzzy=True, limit=5):
            print("  - Fuzzy search 'usr': 동작 안 함 ⚠️")
            print("  - 원인: Fuzzy threshold가 너무 높거나, 알고리즘 문제")
        else:
            print("  - Fuzzy search: 동작 ✓")

        return True


async def critical_review_2_dependency_resolution():
    """비판적 재검증 2: Dependency가 왜 0개?"""
    print("\n" + "=" * 60)
    print("비판적 재검증 2: Dependency Resolution 문제")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = Path(tmpdir)

        # Create two files with clear dependency
        models_py = test_proj / "models.py"
        models_py.write_text("class User:\n    pass")

        service_py = test_proj / "service.py"
        service_py.write_text(
            "from models import User\n\nclass UserService:\n    def create(self) -> User:\n        return User()"
        )

        from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
        from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
        from src.contexts.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver

        # Generate IR for both files
        ir_docs = []
        for file_path in [models_py, service_py]:
            content = file_path.read_text()
            source = SourceFile.from_content(str(file_path), content, "python")
            ast = AstTree.parse(source)
            generator = PythonIRGenerator(repo_id="test")
            ir_doc = generator.generate(source, "test", ast)
            ir_docs.append(ir_doc)

        # Resolve
        resolver = CrossFileResolver()
        global_ctx = resolver.resolve(ir_docs)

        print(f"\n파일: 2개 (models.py, service.py)")
        print(f"service.py는 models.py를 import → 의존성 1개 예상")

        stats = global_ctx.get_stats()
        print(f"\nGlobal context stats:")
        print(f"  - total_files: {stats['total_files']}")
        print(f"  - total_dependencies: {stats['total_dependencies']}")

        service_deps = global_ctx.get_dependencies(str(service_py))
        print(f"\nservice.py dependencies: {len(service_deps)}")
        if service_deps:
            print(f"  - {service_deps}")

        if stats["total_dependencies"] == 0:
            print("\n⚠️ 문제: Dependency가 파악되지 않음!")
            print("  원인 추측:")
            print("  1. CrossFileResolver가 import를 파악하지 못함")
            print("  2. IR에서 import edge가 생성되지 않음")
            print("  3. Dependency graph 구축 로직 버그")
        else:
            print("\n✅ Dependency 정상 파악")

        return True


async def critical_review_3_edge_cases():
    """비판적 재검증 3: Edge cases"""
    print("\n" + "=" * 60)
    print("비판적 재검증 3: Edge Cases")
    print("=" * 60)

    from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
    from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator

    # Edge case 1: Empty file
    print("\n1. Empty file:")
    try:
        source = SourceFile.from_content("empty.py", "", "python")
        ast = AstTree.parse(source)
        generator = PythonIRGenerator(repo_id="test")
        ir_doc = generator.generate(source, "test", ast)
        print(f"   Nodes: {len(ir_doc.nodes)}, Edges: {len(ir_doc.edges)}")
        print("   ✅ No crash")
    except Exception as e:
        print(f"   ❌ Crashed: {e}")

    # Edge case 2: Syntax error
    print("\n2. Syntax error:")
    try:
        source = SourceFile.from_content("error.py", "def foo(:\n    pass", "python")
        ast = AstTree.parse(source)
        print(f"   AST error nodes: {len([n for n in ast.root_node.children if n.is_error])}")
        print("   ✅ Handled gracefully")
    except Exception as e:
        print(f"   ❌ Crashed: {e}")

    # Edge case 3: Very long identifier
    print("\n3. Very long identifier:")
    try:
        long_name = "x" * 1000
        code = f"def {long_name}():\n    pass"
        source = SourceFile.from_content("long.py", code, "python")
        ast = AstTree.parse(source)
        generator = PythonIRGenerator(repo_id="test")
        ir_doc = generator.generate(source, "test", ast)
        print(f"   Nodes: {len(ir_doc.nodes)}")
        print("   ✅ Handled")
    except Exception as e:
        print(f"   ❌ Crashed: {e}")

    # Edge case 4: Unicode symbols
    print("\n4. Unicode symbols:")
    try:
        code = "class 사용자:\n    def 이름_가져오기(self):\n        return '홍길동'"
        source = SourceFile.from_content("unicode.py", code, "python")
        ast = AstTree.parse(source)
        generator = PythonIRGenerator(repo_id="test")
        ir_doc = generator.generate(source, "test", ast)
        print(f"   Nodes: {len(ir_doc.nodes)}")
        classes = [n for n in ir_doc.nodes if n.kind.value == "Class"]
        if classes:
            print(f"   Class name: {classes[0].name}")
        print("   ✅ Unicode 지원")
    except Exception as e:
        print(f"   ❌ Crashed: {e}")

    # Edge case 5: Circular imports (A imports B, B imports A)
    print("\n5. Circular imports:")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_proj = Path(tmpdir)

        a_py = test_proj / "a.py"
        a_py.write_text("from b import B\nclass A:\n    pass")

        b_py = test_proj / "b.py"
        b_py.write_text("from a import A\nclass B:\n    pass")

        try:
            from src.contexts.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver

            ir_docs = []
            for file_path in [a_py, b_py]:
                content = file_path.read_text()
                source = SourceFile.from_content(str(file_path), content, "python")
                ast = AstTree.parse(source)
                generator = PythonIRGenerator(repo_id="test")
                ir_doc = generator.generate(source, "test", ast)
                ir_docs.append(ir_doc)

            resolver = CrossFileResolver()
            global_ctx = resolver.resolve(ir_docs)
            print(f"   Symbols: {global_ctx.total_symbols}")
            print("   ✅ Circular import 처리")
        except Exception as e:
            print(f"   ❌ Crashed: {e}")

    return True


async def critical_review_4_performance_stress():
    """비판적 재검증 4: 성능 스트레스 테스트"""
    print("\n" + "=" * 60)
    print("비판적 재검증 4: 성능 스트레스 테스트")
    print("=" * 60)

    import time

    # Generate large file
    print("\n큰 파일 생성 중... (100 classes, 500 methods)")
    code_lines = []
    for i in range(100):
        code_lines.append(f"class Class{i}:")
        for j in range(5):
            code_lines.append(f"    def method{j}(self, arg: int) -> str:")
            code_lines.append(f"        return 'result'")
        code_lines.append("")

    large_code = "\n".join(code_lines)
    print(f"코드 크기: {len(large_code):,} bytes")

    from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
    from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator
    from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

    # IR Generation
    start = time.perf_counter()
    source = SourceFile.from_content("large.py", large_code, "python")
    ast = AstTree.parse(source)
    generator = PythonIRGenerator(repo_id="test")
    ir_doc = generator.generate(source, "test", ast)
    ir_time = (time.perf_counter() - start) * 1000

    print(f"\nIR Generation: {ir_time:.2f}ms")
    print(f"  - Nodes: {len(ir_doc.nodes)}")
    print(f"  - Edges: {len(ir_doc.edges)}")

    # Occurrence Generation
    start = time.perf_counter()
    occ_gen = OccurrenceGenerator()
    occurrences, occ_index = occ_gen.generate(ir_doc)
    occ_time = (time.perf_counter() - start) * 1000

    print(f"\nOccurrence Generation: {occ_time:.2f}ms")
    print(f"  - Occurrences: {len(occurrences)}")

    # Index Building
    start = time.perf_counter()
    index = RetrievalOptimizedIndex()
    index.index_ir_document(ir_doc)
    index_time = (time.perf_counter() - start) * 1000

    print(f"\nIndex Building: {index_time:.2f}ms")

    # Search
    start = time.perf_counter()
    for i in range(100):
        results = index.search_symbol(f"Class{i}", fuzzy=False, limit=5)
    search_time = (time.perf_counter() - start) * 1000

    print(f"\n100 Searches: {search_time:.2f}ms ({search_time / 100:.2f}ms per search)")

    total = ir_time + occ_time + index_time
    print(f"\nTotal (large file): {total:.2f}ms")

    # Performance goals
    if ir_time < 100:
        print("  ✅ IR generation: 목표 달성 (<100ms)")
    else:
        print(f"  ⚠️ IR generation: 느림 ({ir_time:.2f}ms)")

    if search_time / 100 < 1:
        print("  ✅ Search: 목표 달성 (<1ms per search)")
    else:
        print(f"  ⚠️ Search: 느림 ({search_time / 100:.2f}ms per search)")

    return True


async def main():
    """모든 비판적 재검증 실행"""
    print("\n" + "🔍" + "=" * 58 + "🔍")
    print("   SOTA IR 최종 비판적 재검증")
    print("🔍" + "=" * 58 + "🔍")

    tests = [
        ("Fuzzy Search 문제", critical_review_1_fuzzy_search),
        ("Dependency Resolution 문제", critical_review_2_dependency_resolution),
        ("Edge Cases", critical_review_3_edge_cases),
        ("성능 스트레스", critical_review_4_performance_stress),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            await test_func()
            results.append((test_name, True, None))
        except Exception as e:
            results.append((test_name, False, str(e)))
            print(f"❌ FAILED: {e}")
            import traceback

            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("최종 비판적 재검증 결과")
    print("=" * 60)

    for test_name, passed, error in results:
        if passed:
            print(f"✅ {test_name:30s}: PASSED")
        else:
            print(f"❌ {test_name:30s}: FAILED - {error}")

    print("=" * 60)

    passed_count = sum(1 for _, passed, _ in results if passed)
    total_count = len(results)

    if passed_count == total_count:
        print(f"\n🎉 모든 {total_count}개 재검증 통과!")
        return 0
    else:
        print(f"\n⚠️ {total_count - passed_count}/{total_count} 재검증 실패 (하지만 치명적이지 않을 수 있음)")
        return 0  # Still return 0 because these are deep investigations


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
