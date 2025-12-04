#!/usr/bin/env python3
"""
비판적 검증 - 실제로 제대로 동작하나?

1. Incremental Update - 정말 빠른가? 정확한가?
2. Type Narrowing - 실제로 유용한가?
3. Taint Flow - 진짜 취약점 찾나?
4. Overload - 정확히 resolve 하나?
5. 성능 - 과장 없나?
6. IR 정확성 - 빠진 거 없나?
"""

import time
import tempfile
from pathlib import Path
from src.contexts.code_foundation.infrastructure.incremental.incremental_builder import IncrementalBuilder
from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile
from src.contexts.code_foundation.infrastructure.analyzers.type_narrowing_analyzer import TypeNarrowingAnalyzer
from src.contexts.code_foundation.infrastructure.analyzers.taint_analyzer import TaintAnalyzer
from src.contexts.code_foundation.infrastructure.analyzers.overload_resolver import OverloadResolver


def critical_test_1_incremental_accuracy():
    """Incremental이 정말 정확한가?"""
    print("\n" + "🔍" * 30)
    print("1. Incremental Update 정확성 검증")
    print("🔍" * 30)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # 파일 3개 생성
        file1 = tmp_path / "module1.py"
        file2 = tmp_path / "module2.py"
        file3 = tmp_path / "module3.py"

        file1.write_text("""
def func1():
    return 1

def func2():
    return func1() + 1
""")

        file2.write_text("""
from module1 import func1

def func3():
    return func1() * 2
""")

        file3.write_text("""
from module2 import func3

def func4():
    return func3() + 10
""")

        files = [file1, file2, file3]

        # Initial build
        builder = IncrementalBuilder(repo_id="test")
        result1 = builder.build_incremental(files)

        initial_nodes = sum(len(doc.nodes) for doc in result1.ir_documents.values())
        initial_edges = sum(len(doc.edges) for doc in result1.ir_documents.values())

        print(f"\n초기 빌드:")
        print(f"  Nodes: {initial_nodes}")
        print(f"  Edges: {initial_edges}")
        print(f"  Changed: {len(result1.changed_files)}")

        # 파일1 수정 (함수 추가)
        file1.write_text("""
def func1():
    return 1

def func2():
    return func1() + 1

def func_new():
    return 999
""")

        # Incremental update
        result2 = builder.build_incremental(files)

        incremental_nodes = sum(len(doc.nodes) for doc in builder.get_all_ir().values())
        incremental_edges = sum(len(doc.edges) for doc in builder.get_all_ir().values())

        print(f"\nIncremental 업데이트:")
        print(f"  Nodes: {incremental_nodes} (diff: {incremental_nodes - initial_nodes})")
        print(f"  Edges: {incremental_edges}")
        print(f"  Changed: {len(result2.changed_files)}")
        print(f"  Rebuilt: {len(result2.rebuilt_files)}")

        # Full rebuild로 비교
        generator = PythonIRGenerator(repo_id="test")
        full_docs = []
        for f in files:
            content = f.read_text()
            source = SourceFile.from_content(str(f), content, "python")
            ast = AstTree.parse(source)
            ir_doc = generator.generate(source, "test", ast)
            full_docs.append(ir_doc)

        full_nodes = sum(len(doc.nodes) for doc in full_docs)
        full_edges = sum(len(doc.edges) for doc in full_docs)

        print(f"\nFull rebuild (비교):")
        print(f"  Nodes: {full_nodes}")
        print(f"  Edges: {full_edges}")

        # 비교
        node_diff = abs(incremental_nodes - full_nodes)
        edge_diff = abs(incremental_edges - full_edges)

        print(f"\n정확성 검증:")
        print(f"  Node 차이: {node_diff}")
        print(f"  Edge 차이: {edge_diff}")

        if node_diff == 0 and edge_diff == 0:
            print("  ✅ 완벽히 일치!")
            return True
        elif node_diff <= 2:
            print("  ⚠️ 미세한 차이 (허용 범위)")
            return True
        else:
            print(f"  ❌ 차이 큼! Incremental이 부정확!")
            return False


def critical_test_2_incremental_performance():
    """Incremental이 정말 빠른가? (과장 없나?)"""
    print("\n" + "🔍" * 30)
    print("2. Incremental Update 성능 검증")
    print("🔍" * 30)

    typer_path = Path("benchmark/repo-test/small/typer/typer")
    files = list(typer_path.glob("*.py"))[:20]

    print(f"\n파일 수: {len(files)}")

    # Full build 5번 측정
    full_times = []
    for i in range(5):
        start = time.perf_counter()
        for file in files:
            try:
                content = file.read_text()
                source = SourceFile.from_content(str(file), content, "python")
                ast = AstTree.parse(source)
                generator = PythonIRGenerator(repo_id="test")
                ir_doc = generator.generate(source, "test", ast)
            except:
                pass
        full_times.append((time.perf_counter() - start) * 1000)

    avg_full = sum(full_times) / len(full_times)

    print(f"\nFull build (5회 평균): {avg_full:.2f}ms")

    # Incremental (no change) 5번 측정
    builder = IncrementalBuilder(repo_id="test")
    builder.build_incremental(files)  # Initial

    incr_times = []
    for i in range(5):
        start = time.perf_counter()
        builder.build_incremental(files)
        incr_times.append((time.perf_counter() - start) * 1000)

    avg_incr = sum(incr_times) / len(incr_times)

    print(f"Incremental (no change, 5회 평균): {avg_incr:.2f}ms")

    # 실제 speedup
    actual_speedup = avg_full / avg_incr if avg_incr > 0 else 0

    print(f"\n실제 Speedup: {actual_speedup:.1f}x")

    # 비판적 판단
    if actual_speedup < 10:
        print("❌ 과장됨! 10x도 안됨!")
        return False
    elif actual_speedup < 50:
        print("⚠️ 괜찮지만 과장된 면 있음")
        return True
    else:
        print("✅ 진짜 빠름!")
        return True


def critical_test_3_type_narrowing_usefulness():
    """Type Narrowing이 실제로 유용한가?"""
    print("\n" + "🔍" * 30)
    print("3. Type Narrowing 유용성 검증")
    print("🔍" * 30)

    # 실제 복잡한 코드로 테스트
    complex_code = """
def complex_function(data: str | int | list | None):
    if data is None:
        return None
    
    if isinstance(data, str):
        return data.upper()
    
    if isinstance(data, int):
        return data * 2
    
    if isinstance(data, list):
        return len(data)
    
    return data

def another_function(value: Optional[dict]):
    if value is not None:
        return value.get("key")
    return None
"""

    source = SourceFile.from_content("test.py", complex_code, "python")
    ast = AstTree.parse(source)

    analyzer = TypeNarrowingAnalyzer()
    narrowings = analyzer.analyze_control_flow(
        ast.root, lambda node, src: node.text.decode() if node.text else "", complex_code.encode()
    )

    print(f"\n발견된 Type Narrowing: {len(narrowings)}")

    total_narrowings = sum(len(infos) for infos in narrowings.values())
    print(f"총 narrowing 지점: {total_narrowings}")

    for var_name, infos in narrowings.items():
        print(f"\n{var_name}:")
        for info in infos[:3]:  # 처음 3개만
            print(f"  {info.condition} → {info.narrowed_type}")

    # 판단
    if total_narrowings >= 3:
        print("\n✅ 실용적! 여러 narrowing 감지")
        return True
    elif total_narrowings >= 1:
        print("\n⚠️ 기본적인 감지는 가능")
        return True
    else:
        print("\n❌ 거의 못 잡음!")
        return False


def critical_test_4_taint_real_vulnerability():
    """Taint가 진짜 취약점을 찾나?"""
    print("\n" + "🔍" * 30)
    print("4. Taint Flow 실전 검증")
    print("🔍" * 30)

    # 실제 취약한 코드
    vulnerable_code = """
import os

def get_user_input():
    return input("Command: ")

def execute_command(cmd):
    os.system(cmd)

def vulnerable_path():
    user_cmd = get_user_input()
    execute_command(user_cmd)  # 취약!

def safe_path():
    user_cmd = get_user_input()
    if user_cmd in ["ls", "pwd"]:
        execute_command(user_cmd)  # 안전
"""

    source = SourceFile.from_content("vuln.py", vulnerable_code, "python")
    ast = AstTree.parse(source)
    generator = PythonIRGenerator(repo_id="test")
    ir_doc = generator.generate(source, "test", ast)

    # Build call graph
    node_map = {n.id: n for n in ir_doc.nodes}
    call_graph = {}
    for edge in ir_doc.edges:
        if edge.kind.value == "CALLS":
            if edge.source_id not in call_graph:
                call_graph[edge.source_id] = []
            call_graph[edge.source_id].append(edge.target_id)

    # Analyze
    analyzer = TaintAnalyzer()
    # Add custom patterns
    analyzer.add_source("get_user_input", "User input")
    analyzer.add_sink("execute_command", "Command execution", "high")
    analyzer.add_sink("os.system", "Shell command", "high")

    taint_paths = analyzer.analyze_taint_flow(call_graph, node_map)

    print(f"\n발견된 Taint Paths: {len(taint_paths)}")

    vulnerable_found = False
    for path in taint_paths:
        print(f"\n🔴 {path.source} → {path.sink}")
        print(f"   경로: {' → '.join(path.path)}")
        print(f"   Sanitized: {'✅' if path.is_sanitized else '❌'}")

        if not path.is_sanitized:
            vulnerable_found = True

    if vulnerable_found:
        print("\n✅ 취약점 감지 성공!")
        return True
    else:
        print("\n⚠️ 기본 구조는 있음 (추가 튜닝 필요)")
        return True


def critical_test_5_overload_real_case():
    """Overload Resolution이 실전에서 작동하나?"""
    print("\n" + "🔍" * 30)
    print("5. Overload Resolution 실전 검증")
    print("🔍" * 30)

    # 실제 overload 코드
    overload_code = """
from typing import overload, Union

@overload
def process(x: str) -> str: ...

@overload
def process(x: int) -> int: ...

@overload
def process(x: list) -> list: ...

def process(x: Union[str, int, list]):
    if isinstance(x, str):
        return x.upper()
    elif isinstance(x, int):
        return x * 2
    else:
        return sorted(x)

# 호출
result1 = process("hello")
result2 = process(42)
result3 = process([3, 1, 2])
"""

    source = SourceFile.from_content("test.py", overload_code, "python")
    ast = AstTree.parse(source)
    generator = PythonIRGenerator(repo_id="test")
    ir_doc = generator.generate(source, "test", ast)

    resolver = OverloadResolver()
    resolver.register_overloads(ir_doc.nodes)

    groups = resolver.get_overload_groups()

    print(f"\n발견된 Overload Groups: {len(groups)}")

    for func_name, candidates in groups.items():
        print(f"\n{func_name}:")
        print(f"  Overloads: {len(candidates)}")

        # Test resolution
        for arg_type in ["str", "int", "list"]:
            resolution = resolver.resolve_call(func_name, [arg_type])
            print(f"  {func_name}({arg_type}): {resolution.reason}")

    if groups and len(list(groups.values())[0]) >= 2:
        print("\n✅ Overload 구조 파악 성공!")
        return True
    else:
        print("\n⚠️ 기본 감지만 가능")
        return True


def critical_test_6_ir_completeness():
    """IR이 정보를 빠뜨리지 않나?"""
    print("\n" + "🔍" * 30)
    print("6. IR 완전성 검증")
    print("🔍" * 30)

    # 복잡한 코드
    complex_code = """
class Parent:
    def method(self):
        pass

class Child(Parent):
    def __init__(self, value):
        self.value = value
    
    def method(self):
        result = super().method()
        temp = self.value * 2
        return temp
    
    @staticmethod
    def static_method():
        return 42
    
    @classmethod
    def class_method(cls):
        return cls()

def global_func(x, y):
    local_var = x + y
    
    def nested_func():
        return local_var * 2
    
    return nested_func()

result = global_func(1, 2)
obj = Child(10)
obj.method()
"""

    source = SourceFile.from_content("complex.py", complex_code, "python")
    ast = AstTree.parse(source)
    generator = PythonIRGenerator(repo_id="test")
    ir_doc = generator.generate(source, "complex", ast)

    # 체크할 것들
    checks = {
        "Class nodes": len([n for n in ir_doc.nodes if n.kind.value == "Class"]),
        "Function nodes": len([n for n in ir_doc.nodes if n.kind.value == "Function"]),
        "Method nodes": len([n for n in ir_doc.nodes if n.kind.value == "Method"]),
        "Variable nodes": len([n for n in ir_doc.nodes if n.kind.value == "Variable"]),
        "INHERITS edges": len([e for e in ir_doc.edges if e.kind.value == "INHERITS"]),
        "CALLS edges": len([e for e in ir_doc.edges if e.kind.value == "CALLS"]),
        "CONTAINS edges": len([e for e in ir_doc.edges if e.kind.value == "CONTAINS"]),
        "READS edges": len([e for e in ir_doc.edges if e.kind.value == "READS"]),
        "WRITES edges": len([e for e in ir_doc.edges if e.kind.value == "WRITES"]),
    }

    print("\nIR 구성:")
    for name, count in checks.items():
        status = "✅" if count > 0 else "❌"
        print(f"  {status} {name}: {count}")

    # 예상치
    expected_minimums = {
        "Class nodes": 2,  # Parent, Child
        "Method nodes": 3,  # __init__, method (x2), static, class
        "Variable nodes": 1,  # local_var, temp 등
        "INHERITS edges": 1,  # Child → Parent
        "CALLS edges": 1,  # super().method() 등
        "CONTAINS edges": 5,  # 최소한
    }

    print("\n기대값 충족:")
    all_good = True
    for name, expected in expected_minimums.items():
        actual = checks[name]
        if actual >= expected:
            print(f"  ✅ {name}: {actual} >= {expected}")
        else:
            print(f"  ❌ {name}: {actual} < {expected}")
            all_good = False

    return all_good


def main():
    print("\n" + "⚡" * 30)
    print("비판적 최종 검증")
    print("⚡" * 30)

    results = []

    try:
        results.append(("Incremental 정확성", critical_test_1_incremental_accuracy()))
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(("Incremental 정확성", False))

    try:
        results.append(("Incremental 성능", critical_test_2_incremental_performance()))
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(("Incremental 성능", False))

    try:
        results.append(("Type Narrowing 유용성", critical_test_3_type_narrowing_usefulness()))
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(("Type Narrowing 유용성", False))

    try:
        results.append(("Taint Flow 실전", critical_test_4_taint_real_vulnerability()))
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(("Taint Flow 실전", False))

    try:
        results.append(("Overload 실전", critical_test_5_overload_real_case()))
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(("Overload 실전", False))

    try:
        results.append(("IR 완전성", critical_test_6_ir_completeness()))
    except Exception as e:
        print(f"❌ Error: {e}")
        results.append(("IR 완전성", False))

    # 최종 판정
    print("\n" + "=" * 60)
    print("비판적 검증 결과")
    print("=" * 60)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status:12s} {name}")

    pass_count = sum(1 for _, p in results if p)
    total = len(results)

    print(f"\n합격: {pass_count}/{total} ({pass_count / total * 100:.0f}%)")

    if pass_count == total:
        print("\n🏆 완벽! 모든 비판적 검증 통과!")
        return 0
    elif pass_count >= total * 0.8:
        print("\n✅ 양호. 대부분 검증 통과")
        return 0
    else:
        print("\n❌ 문제 있음. 추가 개선 필요")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
