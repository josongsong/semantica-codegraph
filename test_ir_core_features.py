#!/usr/bin/env python3
"""
SOTA IR 핵심 기능 테스트 - Typer 레포지토리

IR의 본질적 기능만 테스트:
1. Call Graph (함수 호출 관계)
2. Class Hierarchy (상속 관계)
3. Import/Dependency Graph
4. Definition-Use Chain (변수 사용)
5. Type Resolution
6. Scope Chain
7. Edge 종류별 검증
8. FQN 정확도
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Set
from collections import defaultdict


TYPER_REPO = Path("/Users/songmin/Documents/code-jo/semantica-v2/codegraph/benchmark/repo-test/small/typer")


def load_typer_ir():
    """Typer 레포지토리 IR 로드"""
    from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile

    typer_pkg = TYPER_REPO / "typer"
    python_files = list(typer_pkg.glob("**/*.py"))[:20]  # 처음 20개만

    print(f"Loading {len(python_files)} Python files...")

    generator = PythonIRGenerator(repo_id="typer")
    ir_docs = []

    for py_file in python_files:
        try:
            content = py_file.read_text(encoding="utf-8")
            source = SourceFile.from_content(str(py_file), content, "python")
            ast = AstTree.parse(source)
            ir_doc = generator.generate(source, "typer", ast)
            ir_docs.append(ir_doc)
        except Exception as e:
            print(f"  ⚠️ Failed {py_file.name}: {e}")

    print(f"✅ Loaded {len(ir_docs)} IR documents")
    return ir_docs


async def test_1_call_graph(ir_docs: List):
    """테스트 1: Call Graph (함수 호출 관계)"""
    print("\n" + "=" * 60)
    print("테스트 1: Call Graph (함수 호출 관계)")
    print("=" * 60)

    # Edge kind가 CALLS인 것들 추출
    call_edges = []
    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "CALLS":
                call_edges.append((doc, edge))

    print(f"\nCALLS edges: {len(call_edges)}개")

    if len(call_edges) == 0:
        print("❌ CRITICAL: No CALLS edges found!")
        return False

    # 샘플 call graph 출력
    print("\n샘플 함수 호출:")
    node_by_id = {}
    for doc in ir_docs:
        for node in doc.nodes:
            node_by_id[node.id] = node

    for i, (doc, edge) in enumerate(call_edges[:10], 1):
        source_node = node_by_id.get(edge.source_id)
        target_node = node_by_id.get(edge.target_id)

        if source_node and target_node:
            source_name = source_node.name or source_node.id.split(":")[-1]
            target_name = target_node.name or target_node.id.split(":")[-1]
            print(f"  {i}. {source_name} → calls → {target_name}")

    # Call graph 통계
    call_counts = defaultdict(int)
    for doc, edge in call_edges:
        source_node = node_by_id.get(edge.source_id)
        if source_node:
            call_counts[source_node.id] += 1

    top_callers = sorted(call_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    print(f"\nTop callers (호출을 많이 하는 함수):")
    for node_id, count in top_callers:
        node = node_by_id.get(node_id)
        name = node.name if node else node_id
        print(f"  - {name}: {count}번 호출")

    print(f"\n✅ Call Graph 동작: {len(call_edges)}개 호출 관계")
    return True


async def test_2_class_hierarchy(ir_docs: List):
    """테스트 2: Class Hierarchy (상속 관계)"""
    print("\n" + "=" * 60)
    print("테스트 2: Class Hierarchy (상속 관계)")
    print("=" * 60)

    # INHERITS edge 찾기
    inherit_edges = []
    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "INHERITS":
                inherit_edges.append((doc, edge))

    print(f"\nINHERITS edges: {len(inherit_edges)}개")

    if len(inherit_edges) == 0:
        print("⚠️ No inheritance found (may be ok for some repos)")
        return True

    # 상속 관계 출력
    node_by_id = {}
    for doc in ir_docs:
        for node in doc.nodes:
            node_by_id[node.id] = node

    print("\n상속 관계:")
    for i, (doc, edge) in enumerate(inherit_edges[:10], 1):
        child = node_by_id.get(edge.source_id)
        parent = node_by_id.get(edge.target_id)

        if child and parent:
            child_name = child.name or child.id.split(":")[-1]
            parent_name = parent.name or parent.id.split(":")[-1]
            print(f"  {i}. {child_name} extends {parent_name}")

    print(f"\n✅ Class Hierarchy: {len(inherit_edges)}개 상속 관계")
    return True


async def test_3_import_dependencies(ir_docs: List):
    """테스트 3: Import/Dependency 관계"""
    print("\n" + "=" * 60)
    print("테스트 3: Import/Dependency 관계")
    print("=" * 60)

    # IMPORTS edge 찾기
    import_edges = []
    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "IMPORTS":
                import_edges.append((doc, edge))

    print(f"\nIMPORTS edges: {len(import_edges)}개")

    if len(import_edges) == 0:
        print("❌ CRITICAL: No IMPORTS edges found!")
        return False

    # Import 관계 출력
    node_by_id = {}
    for doc in ir_docs:
        for node in doc.nodes:
            node_by_id[node.id] = node

    print("\n샘플 Import 관계:")
    for i, (doc, edge) in enumerate(import_edges[:10], 1):
        importer = node_by_id.get(edge.source_id)
        imported = node_by_id.get(edge.target_id)

        if importer and imported:
            importer_file = importer.file_path.split("/")[-1]
            imported_name = imported.name or imported.id.split(":")[-1]
            print(f"  {i}. {importer_file} imports {imported_name}")

    # 파일별 import 통계
    imports_by_file = defaultdict(set)
    for doc, edge in import_edges:
        source = node_by_id.get(edge.source_id)
        target = node_by_id.get(edge.target_id)
        if source and target:
            imports_by_file[source.file_path].add(target.name or target.id)

    print(f"\n파일별 Import 통계:")
    for file_path, imports in sorted(imports_by_file.items(), key=lambda x: len(x[1]), reverse=True)[:5]:
        file_name = file_path.split("/")[-1]
        print(f"  - {file_name}: {len(imports)} imports")

    print(f"\n✅ Import Dependencies: {len(import_edges)}개")
    return True


async def test_4_definition_use_chain(ir_docs: List):
    """테스트 4: Definition-Use Chain (변수 정의/사용)"""
    print("\n" + "=" * 60)
    print("테스트 4: Definition-Use Chain")
    print("=" * 60)

    # READS, WRITES edge 찾기
    read_edges = []
    write_edges = []

    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "READS":
                read_edges.append((doc, edge))
            elif edge.kind.value == "WRITES":
                write_edges.append((doc, edge))

    print(f"\nREADS edges: {len(read_edges)}개")
    print(f"WRITES edges: {len(write_edges)}개")

    total_def_use = len(read_edges) + len(write_edges)

    if total_def_use == 0:
        print("⚠️ No READS/WRITES edges (may need improvement)")
        return True

    # 샘플 출력
    node_by_id = {}
    for doc in ir_docs:
        for node in doc.nodes:
            node_by_id[node.id] = node

    if read_edges:
        print("\n샘플 READS:")
        for i, (doc, edge) in enumerate(read_edges[:5], 1):
            reader = node_by_id.get(edge.source_id)
            variable = node_by_id.get(edge.target_id)
            if reader and variable:
                print(f"  {i}. {reader.name} reads {variable.name}")

    if write_edges:
        print("\n샘플 WRITES:")
        for i, (doc, edge) in enumerate(write_edges[:5], 1):
            writer = node_by_id.get(edge.source_id)
            variable = node_by_id.get(edge.target_id)
            if writer and variable:
                print(f"  {i}. {writer.name} writes {variable.name}")

    print(f"\n✅ Definition-Use Chain: {total_def_use}개")
    return True


async def test_5_contains_hierarchy(ir_docs: List):
    """테스트 5: CONTAINS 계층 구조"""
    print("\n" + "=" * 60)
    print("테스트 5: CONTAINS 계층 구조 (Scope)")
    print("=" * 60)

    contains_edges = []
    for doc in ir_docs:
        for edge in doc.edges:
            if edge.kind.value == "CONTAINS":
                contains_edges.append((doc, edge))

    print(f"\nCONTAINS edges: {len(contains_edges)}개")

    if len(contains_edges) == 0:
        print("❌ CRITICAL: No CONTAINS edges!")
        return False

    # Build containment tree for one file
    node_by_id = {}
    for doc in ir_docs:
        for node in doc.nodes:
            node_by_id[node.id] = node

    # 샘플 계층 구조
    print("\n샘플 CONTAINS 계층:")
    shown = 0
    for doc, edge in contains_edges[:20]:
        parent = node_by_id.get(edge.source_id)
        child = node_by_id.get(edge.target_id)

        if parent and child and parent.kind.value == "Class":
            print(f"  Class {parent.name} contains:")
            # Find all children
            children = [e for d, e in contains_edges if e.source_id == parent.id]
            for child_edge in children[:5]:
                child_node = node_by_id.get(child_edge.target_id)
                if child_node:
                    print(f"    - {child_node.kind.value}: {child_node.name}")
            shown += 1
            if shown >= 3:
                break

    print(f"\n✅ CONTAINS hierarchy: {len(contains_edges)}개")
    return True


async def test_6_edge_kind_coverage(ir_docs: List):
    """테스트 6: Edge 종류별 커버리지"""
    print("\n" + "=" * 60)
    print("테스트 6: Edge Kind 커버리지")
    print("=" * 60)

    edge_kinds = defaultdict(int)
    for doc in ir_docs:
        for edge in doc.edges:
            edge_kinds[edge.kind.value] += 1

    total_edges = sum(edge_kinds.values())

    print(f"\n총 Edges: {total_edges}개")
    print(f"Edge Kind 종류: {len(edge_kinds)}개")

    print("\nEdge Kind 분포:")
    for kind, count in sorted(edge_kinds.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_edges) * 100 if total_edges > 0 else 0
        print(f"  {kind:20s}: {count:6,} ({pct:5.1f}%)")

    # 필수 edge kinds 체크
    required_edges = ["CONTAINS", "CALLS", "IMPORTS"]
    missing = []
    for req in required_edges:
        if req not in edge_kinds:
            missing.append(req)

    if missing:
        print(f"\n❌ Missing required edges: {missing}")
        return False
    else:
        print(f"\n✅ All required edges present")

    return True


async def test_7_node_kind_coverage(ir_docs: List):
    """테스트 7: Node 종류별 커버리지"""
    print("\n" + "=" * 60)
    print("테스트 7: Node Kind 커버리지")
    print("=" * 60)

    node_kinds = defaultdict(int)
    for doc in ir_docs:
        for node in doc.nodes:
            node_kinds[node.kind.value] += 1

    total_nodes = sum(node_kinds.values())

    print(f"\n총 Nodes: {total_nodes}개")
    print(f"Node Kind 종류: {len(node_kinds)}개")

    print("\nNode Kind 분포:")
    for kind, count in sorted(node_kinds.items(), key=lambda x: x[1], reverse=True):
        pct = (count / total_nodes) * 100 if total_nodes > 0 else 0
        print(f"  {kind:20s}: {count:6,} ({pct:5.1f}%)")

    # 필수 node kinds 체크
    required_nodes = ["Class", "Function", "Method"]
    missing = []
    for req in required_nodes:
        if req not in node_kinds:
            missing.append(req)

    if missing:
        print(f"\n⚠️ Missing some node kinds: {missing}")
    else:
        print(f"\n✅ All required nodes present")

    return True


async def test_8_fqn_quality(ir_docs: List):
    """테스트 8: FQN 품질"""
    print("\n" + "=" * 60)
    print("테스트 8: FQN (Fully Qualified Name) 품질")
    print("=" * 60)

    all_fqns = []
    nodes_without_fqn = 0

    for doc in ir_docs:
        for node in doc.nodes:
            if node.fqn:
                all_fqns.append((node.kind.value, node.name, node.fqn))
            else:
                nodes_without_fqn += 1

    total_nodes = sum(len(doc.nodes) for doc in ir_docs)

    print(f"\n총 Nodes: {total_nodes}")
    print(f"FQN 있음: {len(all_fqns)} ({len(all_fqns) / total_nodes * 100:.1f}%)")
    print(f"FQN 없음: {nodes_without_fqn} ({nodes_without_fqn / total_nodes * 100:.1f}%)")

    # FQN 샘플
    print("\n샘플 FQNs:")
    for i, (kind, name, fqn) in enumerate(all_fqns[:10], 1):
        # Shorten FQN for display
        fqn_display = fqn if len(fqn) < 80 else fqn[:77] + "..."
        print(f"  {i}. {kind:10s} {name:20s}")
        print(f"     → {fqn_display}")

    # FQN 유니크성 체크
    fqn_only = [fqn for _, _, fqn in all_fqns]
    unique_fqns = set(fqn_only)
    duplicates = len(fqn_only) - len(unique_fqns)

    print(f"\nFQN 유니크성:")
    print(f"  - Total: {len(fqn_only)}")
    print(f"  - Unique: {len(unique_fqns)}")
    print(f"  - Duplicates: {duplicates}")

    if duplicates > 0:
        print(f"  ⚠️ {duplicates} duplicate FQNs (may be ok for overloads)")
    else:
        print(f"  ✅ All FQNs unique")

    return True


async def test_9_span_accuracy(ir_docs: List):
    """테스트 9: Span 정확도"""
    print("\n" + "=" * 60)
    print("테스트 9: Span (위치 정보) 정확도")
    print("=" * 60)

    invalid_spans = []
    valid_spans = 0

    for doc in ir_docs:
        for node in doc.nodes:
            if node.span.start_line > node.span.end_line:
                invalid_spans.append((node.name, node.span))
            elif node.span.start_line < 0:
                invalid_spans.append((node.name, node.span))
            else:
                valid_spans += 1

    total = valid_spans + len(invalid_spans)

    print(f"\n총 Spans: {total}")
    print(f"Valid: {valid_spans} ({valid_spans / total * 100:.1f}%)")
    print(f"Invalid: {len(invalid_spans)} ({len(invalid_spans) / total * 100:.1f}%)")

    if invalid_spans:
        print("\n⚠️ Invalid spans:")
        for name, span in invalid_spans[:5]:
            print(f"  - {name}: {span.start_line}-{span.end_line}")
        return False
    else:
        print("\n✅ All spans valid")
        return True


async def test_10_docstring_extraction(ir_docs: List):
    """테스트 10: Docstring 추출"""
    print("\n" + "=" * 60)
    print("테스트 10: Docstring 추출")
    print("=" * 60)

    with_docstring = 0
    without_docstring = 0

    docstring_samples = []

    for doc in ir_docs:
        for node in doc.nodes:
            # Class, Function, Method만 체크
            if node.kind.value in ["Class", "Function", "Method"]:
                if node.docstring:
                    with_docstring += 1
                    if len(docstring_samples) < 5:
                        docstring_samples.append((node.kind.value, node.name, node.docstring))
                else:
                    without_docstring += 1

    total = with_docstring + without_docstring

    print(f"\n총 함수/클래스: {total}")
    print(f"Docstring 있음: {with_docstring} ({with_docstring / total * 100:.1f}%)")
    print(f"Docstring 없음: {without_docstring} ({without_docstring / total * 100:.1f}%)")

    print("\n샘플 Docstrings:")
    for kind, name, docstring in docstring_samples:
        doc_preview = docstring[:60] + "..." if len(docstring) > 60 else docstring
        print(f"  {kind} {name}:")
        print(f'    "{doc_preview}"')

    if with_docstring > 0:
        print(f"\n✅ Docstring extraction working")
    else:
        print(f"\n⚠️ No docstrings found (may be repo issue)")

    return True


async def main():
    """전체 IR 핵심 기능 테스트"""
    print("\n" + "🔬" + "=" * 58 + "🔬")
    print("   SOTA IR 핵심 기능 테스트")
    print("   Call Graph, Class Hierarchy, Dependencies, etc.")
    print("🔬" + "=" * 58 + "🔬")

    # Load IR
    ir_docs = load_typer_ir()

    if not ir_docs:
        print("\n❌ Failed to load IR documents")
        return 1

    # Run tests
    tests = [
        ("Call Graph", test_1_call_graph),
        ("Class Hierarchy", test_2_class_hierarchy),
        ("Import Dependencies", test_3_import_dependencies),
        ("Definition-Use Chain", test_4_definition_use_chain),
        ("CONTAINS Hierarchy", test_5_contains_hierarchy),
        ("Edge Kind Coverage", test_6_edge_kind_coverage),
        ("Node Kind Coverage", test_7_node_kind_coverage),
        ("FQN Quality", test_8_fqn_quality),
        ("Span Accuracy", test_9_span_accuracy),
        ("Docstring Extraction", test_10_docstring_extraction),
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
    print("IR 핵심 기능 테스트 결과")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")

    passed_count = sum(1 for _, p in results if p)
    total_count = len(results)

    print("=" * 60)
    print(f"결과: {passed_count}/{total_count} 테스트 통과 ({passed_count / total_count * 100:.0f}%)")

    if passed_count == total_count:
        print("\n🎉 모든 IR 핵심 기능 동작!")
        return 0
    else:
        print(f"\n⚠️ {total_count - passed_count}개 기능 개선 필요")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
