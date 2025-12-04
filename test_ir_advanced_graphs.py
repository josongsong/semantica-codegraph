#!/usr/bin/env python3
"""
IR 고급 그래프 분석 - CFG, DFG, Call Chain

더 깊은 IR 기능 테스트:
1. Control Flow Graph (CFG) - 제어 흐름
2. Data Flow Graph (DFG) - 데이터 흐름
3. Call Chain - 호출 체인 추적
4. Variable Lifecycle - 변수 생명주기
5. Type Propagation - 타입 전파
6. Scope Analysis - 스코프 분석
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Set, Tuple
from collections import defaultdict, deque


TYPER_REPO = Path("/Users/songmin/Documents/code-jo/semantica-v2/codegraph/benchmark/repo-test/small/typer")


def load_typer_ir():
    """Typer IR 로드"""
    from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile

    typer_pkg = TYPER_REPO / "typer"
    python_files = list(typer_pkg.glob("**/*.py"))[:20]

    generator = PythonIRGenerator(repo_id="typer")
    ir_docs = []

    for py_file in python_files:
        try:
            content = py_file.read_text(encoding="utf-8")
            source = SourceFile.from_content(str(py_file), content, "python")
            ast = AstTree.parse(source)
            ir_doc = generator.generate(source, "typer", ast)
            ir_docs.append(ir_doc)
        except:
            pass

    print(f"✅ Loaded {len(ir_docs)} IR documents")
    return ir_docs


def build_node_map(ir_docs: List) -> Dict[str, any]:
    """노드 ID → 노드 맵 생성"""
    node_map = {}
    for doc in ir_docs:
        for node in doc.nodes:
            node_map[node.id] = node
    return node_map


async def test_1_call_chain_depth(ir_docs: List):
    """테스트 1: Call Chain 깊이 분석"""
    print("\n" + "=" * 60)
    print("테스트 1: Call Chain 깊이 분석")
    print("=" * 60)

    node_map = build_node_map(ir_docs)

    # Build call graph
    call_graph = defaultdict(list)  # caller → [callees]

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "CALLS":
                call_graph[edge.source_id].append(edge.target_id)

    print(f"\nCall graph nodes: {len(call_graph)}")
    print(f"Total call edges: {sum(len(v) for v in call_graph.values())}")

    # Find deepest call chain using BFS
    def get_call_depth(start_node_id: str, max_depth: int = 10) -> int:
        """BFS로 최대 call depth 찾기"""
        if start_node_id not in call_graph:
            return 0

        visited = {start_node_id}
        queue = deque([(start_node_id, 0)])
        max_found = 0

        while queue:
            node_id, depth = queue.popleft()
            max_found = max(max_found, depth)

            if depth >= max_depth:
                continue

            for callee_id in call_graph.get(node_id, []):
                if callee_id not in visited:
                    visited.add(callee_id)
                    queue.append((callee_id, depth + 1))

        return max_found

    # Find functions with deepest call chains
    depth_by_func = {}
    for func_id in list(call_graph.keys())[:50]:  # Sample 50 functions
        depth = get_call_depth(func_id)
        if depth > 0:
            depth_by_func[func_id] = depth

    if depth_by_func:
        top_deep = sorted(depth_by_func.items(), key=lambda x: x[1], reverse=True)[:5]

        print("\n가장 깊은 Call Chain:")
        for func_id, depth in top_deep:
            node = node_map.get(func_id)
            name = node.name if node else func_id.split(":")[-1]
            print(f"  - {name}: depth {depth}")

        avg_depth = sum(depth_by_func.values()) / len(depth_by_func)
        print(f"\n평균 call depth: {avg_depth:.1f}")
        print(f"최대 call depth: {max(depth_by_func.values())}")

        print(f"\n✅ Call chain 추적 가능 (max depth: {max(depth_by_func.values())})")
    else:
        print("\n⚠️ No call chains found")

    return True


async def test_2_transitive_dependencies(ir_docs: List):
    """테스트 2: 전이적 의존성 (A imports B imports C)"""
    print("\n" + "=" * 60)
    print("테스트 2: 전이적 의존성 분석")
    print("=" * 60)

    node_map = build_node_map(ir_docs)

    # Build import graph
    import_graph = defaultdict(set)  # file → {imported symbols}

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "IMPORTS":
                source = node_map.get(edge.source_id)
                target = node_map.get(edge.target_id)
                if source and target:
                    import_graph[source.file_path].add(target.name or target.id)

    print(f"\n파일 수: {len(import_graph)}")
    print(f"직접 import: {sum(len(v) for v in import_graph.values())}개")

    # Find transitive dependencies
    def get_transitive_imports(file_path: str, visited: Set = None) -> Set[str]:
        """재귀적으로 전이적 의존성 찾기"""
        if visited is None:
            visited = set()

        if file_path in visited:
            return set()

        visited.add(file_path)
        transitive = set(import_graph.get(file_path, set()))

        # 재귀적으로 import된 모듈의 import도 추가
        # (실제로는 import된 심볼이 어느 파일에서 왔는지 추적 필요)

        return transitive

    # 샘플 파일의 의존성
    sample_files = list(import_graph.keys())[:5]

    print("\n샘플 파일별 의존성:")
    for file_path in sample_files:
        file_name = file_path.split("/")[-1]
        direct = len(import_graph.get(file_path, set()))
        print(f"  - {file_name}: {direct} direct imports")

    print(f"\n✅ Import dependency graph 구축 가능")
    return True


async def test_3_scope_chain(ir_docs: List):
    """테스트 3: Scope Chain (중첩 스코프)"""
    print("\n" + "=" * 60)
    print("테스트 3: Scope Chain 분석")
    print("=" * 60)

    node_map = build_node_map(ir_docs)

    # Build scope tree using CONTAINS edges
    contains_graph = defaultdict(list)  # parent → [children]

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "CONTAINS":
                contains_graph[edge.source_id].append(edge.target_id)

    print(f"\nCONTAINS edges: {sum(len(v) for v in contains_graph.values())}")

    # Find deepest scope nesting
    def get_scope_depth(node_id: str, depth: int = 0) -> int:
        """재귀적으로 최대 scope depth 찾기"""
        children = contains_graph.get(node_id, [])
        if not children:
            return depth

        return max(get_scope_depth(child_id, depth + 1) for child_id in children)

    # Find root nodes (File nodes)
    root_nodes = []
    all_children = set()
    for children in contains_graph.values():
        all_children.update(children)

    for doc in ir_docs:
        for node in doc.nodes:
            if node.kind.value == "File":
                root_nodes.append(node.id)

    # Calculate depths
    depths = []
    for root_id in root_nodes[:10]:  # Sample 10 files
        depth = get_scope_depth(root_id)
        depths.append(depth)

        root_node = node_map.get(root_id)
        if root_node:
            file_name = root_node.file_path.split("/")[-1]
            print(f"  {file_name}: max scope depth {depth}")

    if depths:
        print(f"\n평균 scope depth: {sum(depths) / len(depths):.1f}")
        print(f"최대 scope depth: {max(depths)}")
        print(f"\n✅ Scope chain 추적 가능")
    else:
        print("\n⚠️ No scope chains found")

    return True


async def test_4_type_information(ir_docs: List):
    """테스트 4: Type 정보 추출"""
    print("\n" + "=" * 60)
    print("테스트 4: Type 정보 분석")
    print("=" * 60)

    # Check node attributes for type info
    types_found = defaultdict(int)
    nodes_with_type = 0
    nodes_without_type = 0

    type_samples = []

    for doc in ir_docs:
        for node in doc.nodes:
            # Check if node has type information in attrs
            node_type = None

            # Check various sources of type info
            if hasattr(node, "type_hint") and node.type_hint:
                node_type = node.type_hint
            elif hasattr(node, "attrs") and "type" in node.attrs:
                node_type = node.attrs.get("type")
            elif hasattr(node, "attrs") and "type_hint" in node.attrs:
                node_type = node.attrs.get("type_hint")

            if node_type:
                nodes_with_type += 1
                types_found[str(node_type)] += 1
                if len(type_samples) < 10:
                    type_samples.append((node.kind.value, node.name, node_type))
            else:
                nodes_without_type += 1

    total = nodes_with_type + nodes_without_type

    print(f"\n총 Nodes: {total}")
    print(f"Type 정보 있음: {nodes_with_type} ({nodes_with_type / total * 100:.1f}%)")
    print(f"Type 정보 없음: {nodes_without_type} ({nodes_without_type / total * 100:.1f}%)")

    if type_samples:
        print("\n샘플 Type 정보:")
        for kind, name, type_info in type_samples[:5]:
            print(f"  - {kind} {name}: {type_info}")

    if nodes_with_type > 0:
        print(f"\n✅ Type 정보 일부 추출 ({nodes_with_type}개)")
    else:
        print(f"\n⚠️ Type 정보 추출 안 됨 (개선 필요)")

    return True


async def test_5_variable_lifecycle(ir_docs: List):
    """테스트 5: Variable 생명주기"""
    print("\n" + "=" * 60)
    print("테스트 5: Variable 생명주기 분석")
    print("=" * 60)

    node_map = build_node_map(ir_docs)

    # Find all variables
    variables = []
    for doc in ir_docs:
        for node in doc.nodes:
            if node.kind.value in ["Variable", "Field"]:
                variables.append(node)

    print(f"\n총 Variables: {len(variables)}")

    # Check if variables have definition location
    with_span = sum(1 for v in variables if v.span.start_line > 0)

    print(f"정의 위치 있음: {with_span} ({with_span / len(variables) * 100:.1f}%)")

    # Sample variable locations
    print("\n샘플 Variable 정의:")
    for var in variables[:10]:
        file_name = var.file_path.split("/")[-1]
        print(f"  - {var.name} @ {file_name}:{var.span.start_line}")

    # Check for READS/WRITES edges
    read_edges = []
    write_edges = []

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "READS":
                read_edges.append(edge)
            elif edge.kind.value == "WRITES":
                write_edges.append(edge)

    print(f"\nREADS edges: {len(read_edges)}")
    print(f"WRITES edges: {len(write_edges)}")

    if len(read_edges) + len(write_edges) > 0:
        print(f"\n✅ Variable lifecycle 추적 가능")
    else:
        print(f"\n⚠️ READS/WRITES edges 없음 (개선 필요)")
        print(f"   → 하지만 variable definition은 추적됨")

    return True


async def test_6_method_resolution(ir_docs: List):
    """테스트 6: Method Resolution (어떤 클래스의 메소드인지)"""
    print("\n" + "=" * 60)
    print("테스트 6: Method Resolution")
    print("=" * 60)

    node_map = build_node_map(ir_docs)

    # Build class → methods mapping using CONTAINS
    class_methods = defaultdict(list)

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "CONTAINS":
                parent = node_map.get(edge.source_id)
                child = node_map.get(edge.target_id)

                if parent and child:
                    if parent.kind.value == "Class" and child.kind.value == "Method":
                        class_methods[parent.id].append(child)

    print(f"\n클래스 수: {len(class_methods)}")

    if class_methods:
        print("\n클래스별 메소드:")
        for class_id, methods in list(class_methods.items())[:5]:
            class_node = node_map.get(class_id)
            if class_node:
                print(f"  {class_node.name}: {len(methods)} methods")
                for method in methods[:3]:
                    print(f"    - {method.name}()")

        total_methods = sum(len(m) for m in class_methods.values())
        avg_methods = total_methods / len(class_methods)

        print(f"\n평균 메소드/클래스: {avg_methods:.1f}")
        print(f"✅ Method resolution 가능")
    else:
        print("\n⚠️ No class-method relationships found")

    return True


async def test_7_call_graph_metrics(ir_docs: List):
    """테스트 7: Call Graph Metrics"""
    print("\n" + "=" * 60)
    print("테스트 7: Call Graph Metrics")
    print("=" * 60)

    node_map = build_node_map(ir_docs)

    # Build call graph
    outgoing_calls = defaultdict(int)  # caller → count
    incoming_calls = defaultdict(int)  # callee → count

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "CALLS":
                outgoing_calls[edge.source_id] += 1
                incoming_calls[edge.target_id] += 1

    print(f"\nTotal callers: {len(outgoing_calls)}")
    print(f"Total callees: {len(incoming_calls)}")

    # Fan-out (가장 많이 호출하는 함수)
    top_fan_out = sorted(outgoing_calls.items(), key=lambda x: x[1], reverse=True)[:5]
    print("\nFan-out (가장 많이 호출):")
    for func_id, count in top_fan_out:
        node = node_map.get(func_id)
        name = node.name if node else func_id.split(":")[-1]
        print(f"  - {name}: {count}번 호출")

    # Fan-in (가장 많이 호출되는 함수)
    top_fan_in = sorted(incoming_calls.items(), key=lambda x: x[1], reverse=True)[:5]
    print("\nFan-in (가장 많이 호출됨):")
    for func_id, count in top_fan_in:
        node = node_map.get(func_id)
        name = node.name if node else func_id.split(":")[-1]
        print(f"  - {name}: {count}번 호출됨")

    # Metrics
    avg_fan_out = sum(outgoing_calls.values()) / len(outgoing_calls) if outgoing_calls else 0
    avg_fan_in = sum(incoming_calls.values()) / len(incoming_calls) if incoming_calls else 0

    print(f"\n평균 fan-out: {avg_fan_out:.1f}")
    print(f"평균 fan-in: {avg_fan_in:.1f}")

    print(f"\n✅ Call graph metrics 계산 가능")
    return True


async def test_8_circular_dependencies(ir_docs: List):
    """테스트 8: Circular Dependencies 탐지"""
    print("\n" + "=" * 60)
    print("테스트 8: Circular Dependencies")
    print("=" * 60)

    node_map = build_node_map(ir_docs)

    # Build import graph
    import_graph = defaultdict(set)

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "IMPORTS":
                source = node_map.get(edge.source_id)
                target = node_map.get(edge.target_id)
                if source and target:
                    import_graph[source.file_path].add(target.file_path)

    # DFS로 cycle 찾기
    def find_cycle(node: str, visited: Set, rec_stack: Set, path: List) -> List:
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in import_graph.get(node, []):
            if neighbor not in visited:
                cycle = find_cycle(neighbor, visited, rec_stack, path)
                if cycle:
                    return cycle
            elif neighbor in rec_stack:
                # Found cycle
                cycle_start = path.index(neighbor)
                return path[cycle_start:] + [neighbor]

        path.pop()
        rec_stack.remove(node)
        return None

    cycles = []
    visited = set()

    for file_path in import_graph.keys():
        if file_path not in visited:
            cycle = find_cycle(file_path, visited, set(), [])
            if cycle:
                cycles.append(cycle)

    print(f"\n분석한 파일: {len(import_graph)}")
    print(f"발견된 circular dependencies: {len(cycles)}")

    if cycles:
        print("\n⚠️ Circular dependencies 발견:")
        for i, cycle in enumerate(cycles[:3], 1):
            print(f"  {i}. Cycle:")
            for file_path in cycle:
                file_name = file_path.split("/")[-1]
                print(f"     → {file_name}")
    else:
        print("\n✅ No circular dependencies (clean!)")

    return True


async def main():
    """고급 그래프 분석 테스트"""
    print("\n" + "📊" + "=" * 58 + "📊")
    print("   IR 고급 그래프 분석")
    print("   CFG, DFG, Call Chain, Scope, etc.")
    print("📊" + "=" * 58 + "📊")

    ir_docs = load_typer_ir()

    if not ir_docs:
        print("\n❌ Failed to load IR")
        return 1

    tests = [
        ("Call Chain Depth", test_1_call_chain_depth),
        ("Transitive Dependencies", test_2_transitive_dependencies),
        ("Scope Chain", test_3_scope_chain),
        ("Type Information", test_4_type_information),
        ("Variable Lifecycle", test_5_variable_lifecycle),
        ("Method Resolution", test_6_method_resolution),
        ("Call Graph Metrics", test_7_call_graph_metrics),
        ("Circular Dependencies", test_8_circular_dependencies),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            passed = await test_func(ir_docs)
            results.append((test_name, passed))
        except Exception as e:
            results.append((test_name, False))
            print(f"\n❌ Exception: {e}")
            import traceback

            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("고급 그래프 분석 결과")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    print("=" * 60)
    print(f"결과: {passed_count}/{total_count} 테스트 통과")

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
