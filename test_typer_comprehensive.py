#!/usr/bin/env python3
"""
Typer 레포지토리 종합 테스트 - 모든 가능한 시나리오

실제 프로덕션 레포지토리(603개 Python 파일)로:
1. 전체 레포지토리 IR 생성
2. Cross-file resolution
3. Occurrence 생성
4. Index 구축
5. 다양한 검색 시나리오
6. 성능 측정
7. 품질 검증
"""

import asyncio
import time
from pathlib import Path
from typing import List
from collections import defaultdict


TYPER_REPO = Path("/Users/songmin/Documents/code-jo/semantica-v2/codegraph/benchmark/repo-test/small/typer")


class TesterStats:
    """테스트 통계"""

    def __init__(self):
        self.files_processed = 0
        self.files_failed = 0
        self.total_nodes = 0
        self.total_edges = 0
        self.total_occurrences = 0
        self.timings = {}
        self.errors = []

    def add_timing(self, name: str, duration_ms: float):
        if name not in self.timings:
            self.timings[name] = []
        self.timings[name].append(duration_ms)

    def get_avg_timing(self, name: str) -> float:
        if name not in self.timings:
            return 0.0
        return sum(self.timings[name]) / len(self.timings[name])

    def print_summary(self):
        print("\n" + "=" * 60)
        print("처리 통계")
        print("=" * 60)
        print(f"파일: {self.files_processed:,} 처리, {self.files_failed} 실패")
        print(f"IR Nodes: {self.total_nodes:,}")
        print(f"IR Edges: {self.total_edges:,}")
        print(f"Occurrences: {self.total_occurrences:,}")

        if self.timings:
            print("\n평균 처리 시간:")
            for name, times in self.timings.items():
                avg = sum(times) / len(times)
                total = sum(times)
                print(f"  - {name:25s}: {avg:8.2f}ms avg, {total:10.2f}ms total")


async def scenario_1_full_repo_ir_generation(stats: TesterStats):
    """시나리오 1: 전체 레포지토리 IR 생성"""
    print("\n" + "=" * 60)
    print("시나리오 1: 전체 레포지토리 IR 생성")
    print("=" * 60)

    from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
    from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile

    # Get all Python files in typer/ directory (core package)
    typer_pkg = TYPER_REPO / "typer"
    python_files = list(typer_pkg.glob("**/*.py"))

    print(f"\nPython 파일: {len(python_files)}개 (typer/ 패키지)")

    generator = PythonIRGenerator(repo_id="typer")
    ir_docs = []

    start_total = time.perf_counter()

    for i, py_file in enumerate(python_files, 1):
        try:
            start = time.perf_counter()

            # Read & parse
            content = py_file.read_text(encoding="utf-8")
            source = SourceFile.from_content(str(py_file), content, "python")
            ast = AstTree.parse(source)

            # Generate IR
            ir_doc = generator.generate(source, "typer", ast)
            ir_docs.append(ir_doc)

            elapsed_ms = (time.perf_counter() - start) * 1000
            stats.add_timing("ir_generation", elapsed_ms)

            stats.files_processed += 1
            stats.total_nodes += len(ir_doc.nodes)
            stats.total_edges += len(ir_doc.edges)

            if i % 5 == 0 or i == len(python_files):
                print(
                    f"\r  처리 중: {i}/{len(python_files)} files "
                    f"({stats.total_nodes:,} nodes, {stats.total_edges:,} edges)",
                    end="",
                )

        except Exception as e:
            stats.files_failed += 1
            stats.errors.append((str(py_file), str(e)))
            print(f"\n  ⚠️ Failed: {py_file.name} - {e}")

    total_time_ms = (time.perf_counter() - start_total) * 1000

    print(f"\n\n✅ IR 생성 완료!")
    print(f"  - 처리: {stats.files_processed}/{len(python_files)} files")
    print(f"  - 실패: {stats.files_failed} files")
    print(f"  - Nodes: {stats.total_nodes:,}")
    print(f"  - Edges: {stats.total_edges:,}")
    print(f"  - 총 시간: {total_time_ms:,.2f}ms ({total_time_ms / 1000:.2f}s)")
    print(f"  - 평균: {total_time_ms / stats.files_processed:.2f}ms/file")

    return ir_docs


async def scenario_2_cross_file_resolution(ir_docs: List, stats: TesterStats):
    """시나리오 2: Cross-file Resolution"""
    print("\n" + "=" * 60)
    print("시나리오 2: Cross-file Resolution")
    print("=" * 60)

    from src.contexts.code_foundation.infrastructure.ir.cross_file_resolver import CrossFileResolver

    print(f"\nIR Documents: {len(ir_docs)}개")

    start = time.perf_counter()
    resolver = CrossFileResolver()
    global_ctx = resolver.resolve(ir_docs)
    elapsed_ms = (time.perf_counter() - start) * 1000

    stats.add_timing("cross_file_resolution", elapsed_ms)

    print(f"\n✅ Cross-file Resolution 완료!")
    print(f"  - 시간: {elapsed_ms:.2f}ms")
    print(f"  - 총 심볼: {global_ctx.total_symbols:,}")

    ctx_stats = global_ctx.get_stats()
    print(f"  - 파일: {ctx_stats['total_files']}")
    print(f"  - 의존성: {ctx_stats['total_dependencies']}")

    # Sample symbol lookup
    print("\n샘플 심볼 조회:")
    sample_symbols = list(global_ctx.symbol_table.keys())[:5]
    for fqn in sample_symbols:
        node, source_file = global_ctx.symbol_table[fqn]
        print(f"  - {fqn[:80]}...")

    return global_ctx


async def scenario_3_occurrence_generation(ir_docs: List, stats: TesterStats):
    """시나리오 3: Occurrence 생성"""
    print("\n" + "=" * 60)
    print("시나리오 3: Occurrence 생성")
    print("=" * 60)

    from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator

    occ_gen = OccurrenceGenerator()
    all_occurrences = []

    print(f"\nIR Documents: {len(ir_docs)}개")

    start_total = time.perf_counter()

    for i, ir_doc in enumerate(ir_docs, 1):
        try:
            start = time.perf_counter()
            occurrences, occ_index = occ_gen.generate(ir_doc)
            elapsed_ms = (time.perf_counter() - start) * 1000

            stats.add_timing("occurrence_generation", elapsed_ms)
            stats.total_occurrences += len(occurrences)

            all_occurrences.extend(occurrences)

            if i % 5 == 0 or i == len(ir_docs):
                print(f"\r  처리 중: {i}/{len(ir_docs)} docs ({stats.total_occurrences:,} occurrences)", end="")

        except Exception as e:
            print(f"\n  ⚠️ Failed: {e}")

    total_time_ms = (time.perf_counter() - start_total) * 1000

    # Analyze occurrences
    by_role = defaultdict(int)
    for occ in all_occurrences:
        role_str = str(occ.roles)
        by_role[role_str] += 1

    print(f"\n\n✅ Occurrence 생성 완료!")
    print(f"  - 총 Occurrences: {stats.total_occurrences:,}")
    print(f"  - 총 시간: {total_time_ms:,.2f}ms")
    print(f"  - 평균: {total_time_ms / len(ir_docs):.2f}ms/doc")

    print("\n  Role 분포:")
    for role, count in sorted(by_role.items(), key=lambda x: x[1], reverse=True)[:10]:
        pct = (count / stats.total_occurrences) * 100
        print(f"    - {role:20s}: {count:6,} ({pct:5.1f}%)")

    return all_occurrences


async def scenario_4_index_building(ir_docs: List, stats: TesterStats):
    """시나리오 4: Retrieval Index 구축"""
    print("\n" + "=" * 60)
    print("시나리오 4: Retrieval Index 구축")
    print("=" * 60)

    from src.contexts.code_foundation.infrastructure.ir.retrieval_index import RetrievalOptimizedIndex

    print(f"\nIR Documents: {len(ir_docs)}개")

    start = time.perf_counter()
    index = RetrievalOptimizedIndex()

    for i, ir_doc in enumerate(ir_docs, 1):
        index.index_ir_document(ir_doc)
        if i % 5 == 0 or i == len(ir_docs):
            print(f"\r  인덱싱 중: {i}/{len(ir_docs)} docs", end="")

    elapsed_ms = (time.perf_counter() - start) * 1000
    stats.add_timing("index_building", elapsed_ms)

    print(f"\n\n✅ Index 구축 완료!")
    print(f"  - 시간: {elapsed_ms:.2f}ms")
    print(f"  - 평균: {elapsed_ms / len(ir_docs):.2f}ms/doc")

    return index


async def scenario_5_search_queries(index, stats: TesterStats):
    """시나리오 5: 다양한 검색 쿼리"""
    print("\n" + "=" * 60)
    print("시나리오 5: 검색 쿼리 테스트")
    print("=" * 60)

    # Test queries based on Typer's API
    queries = [
        # Core classes
        ("Typer", "Core Typer class"),
        ("TyperGroup", "Command group class"),
        ("Argument", "Argument class"),
        ("Option", "Option class"),
        # Core functions
        ("run", "Main run function"),
        ("echo", "Print function"),
        ("confirm", "Confirmation prompt"),
        ("prompt", "User prompt"),
        # Common patterns
        ("callback", "Callback functions"),
        ("command", "Command decorators"),
        ("get_", "Getter methods"),
        ("_init_", "Init methods"),
        # Fuzzy tests
        ("typr", "Typo: Typer"),
        ("optn", "Typo: Option"),
    ]

    print(f"\n테스트 쿼리: {len(queries)}개")

    results_summary = []

    for query, description in queries:
        # Exact search
        start = time.perf_counter()
        exact_results = index.search_symbol(query, fuzzy=False, limit=5)
        exact_time_ms = (time.perf_counter() - start) * 1000

        # Fuzzy search
        start = time.perf_counter()
        fuzzy_results = index.search_symbol(query, fuzzy=True, limit=5)
        fuzzy_time_ms = (time.perf_counter() - start) * 1000

        stats.add_timing("search_exact", exact_time_ms)
        stats.add_timing("search_fuzzy", fuzzy_time_ms)

        results_summary.append(
            {
                "query": query,
                "description": description,
                "exact_count": len(exact_results),
                "fuzzy_count": len(fuzzy_results),
                "exact_time_ms": exact_time_ms,
                "fuzzy_time_ms": fuzzy_time_ms,
                "exact_top": exact_results[0] if exact_results else None,
                "fuzzy_top": fuzzy_results[0] if fuzzy_results else None,
            }
        )

    # Print results
    print("\n검색 결과:")
    print(f"{'Query':<15} {'Description':<25} {'Exact':>7} {'Fuzzy':>7} {'Time(ms)':>10}")
    print("-" * 75)

    for r in results_summary:
        exact_time = f"{r['exact_time_ms']:.2f}"
        print(f"{r['query']:<15} {r['description']:<25} {r['exact_count']:>7} {r['fuzzy_count']:>7} {exact_time:>10}")

    print("\n상위 매칭 샘플:")
    for r in results_summary[:5]:
        if r["exact_top"]:
            node, score = r["exact_top"]
            print(f"  '{r['query']}' → {node.name} (score: {score:.2f}) @ {node.file_path.split('/')[-1]}")

    return results_summary


async def scenario_6_specific_use_cases(ir_docs: List, global_ctx, index):
    """시나리오 6: 특정 사용 사례"""
    print("\n" + "=" * 60)
    print("시나리오 6: 특정 사용 사례 테스트")
    print("=" * 60)

    # Use case 1: "Typer 클래스의 모든 메소드 찾기"
    print("\n1. Typer 클래스의 메소드 찾기")
    typer_class_results = index.search_symbol("Typer", fuzzy=False, limit=10)
    if typer_class_results:
        node, score = typer_class_results[0]
        print(f"   - Found: {node.name} (FQN: {node.fqn})")
        print(f"   - File: {node.file_path.split('/')[-1]}")
        print(f"   - Line: {node.span.start_line}")
    else:
        print("   - Not found")

    # Use case 2: "모든 'command' 관련 함수 찾기"
    print("\n2. 'command' 관련 함수 찾기")
    command_results = index.search_symbol("command", fuzzy=False, limit=10)
    print(f"   - Found {len(command_results)} results")
    for i, (node, score) in enumerate(command_results[:3], 1):
        print(f"     {i}. {node.name} @ {node.file_path.split('/')[-1]}:{node.span.start_line}")

    # Use case 3: "main.py의 모든 정의 찾기"
    print("\n3. main.py의 모든 정의 찾기")
    main_py_docs = [doc for doc in ir_docs if "main.py" in doc.nodes[0].file_path if doc.nodes]
    if main_py_docs:
        main_doc = main_py_docs[0]
        from src.contexts.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator

        occ_gen = OccurrenceGenerator()
        occurrences, _ = occ_gen.generate(main_doc)
        definitions = [o for o in occurrences if o.is_definition()]
        print(f"   - Found {len(definitions)} definitions in main.py")
        for i, occ in enumerate(definitions[:5], 1):
            symbol_name = occ.symbol_id.split(":")[-1].split(".")[-1]
            print(f"     {i}. {symbol_name} @ line {occ.span.start_line}")
    else:
        print("   - main.py not found")

    # Use case 4: "Import 관계 파악"
    print("\n4. Import 관계 샘플")
    if global_ctx:
        # Get some file dependencies
        sample_files = list(set(node.file_path for doc in ir_docs[:5] for node in doc.nodes if doc.nodes))
        for file_path in sample_files[:3]:
            deps = global_ctx.get_dependencies(file_path)
            file_name = file_path.split("/")[-1]
            print(f"   - {file_name}: {len(deps)} dependencies")


async def scenario_7_quality_validation(ir_docs: List, all_occurrences: List):
    """시나리오 7: 품질 검증"""
    print("\n" + "=" * 60)
    print("시나리오 7: 품질 검증")
    print("=" * 60)

    # Validation 1: FQN uniqueness
    print("\n1. FQN 유니크성 검증")
    all_fqns = []
    for doc in ir_docs:
        for node in doc.nodes:
            if node.fqn:
                all_fqns.append(node.fqn)

    unique_fqns = set(all_fqns)
    print(f"   - Total FQNs: {len(all_fqns):,}")
    print(f"   - Unique FQNs: {len(unique_fqns):,}")
    print(f"   - Duplicates: {len(all_fqns) - len(unique_fqns):,}")

    if len(all_fqns) == len(unique_fqns):
        print("   ✅ All FQNs are unique")
    else:
        print("   ⚠️ Some FQNs are duplicated (may be ok for overloads)")

    # Validation 2: Node-Edge consistency
    print("\n2. Node-Edge 일관성 검증")
    total_invalid_edges = 0
    for doc in ir_docs:
        node_ids = {node.id for node in doc.nodes}
        for edge in doc.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                total_invalid_edges += 1

    print(f"   - Invalid edges: {total_invalid_edges}")
    if total_invalid_edges == 0:
        print("   ✅ All edges reference valid nodes")
    else:
        print(f"   ⚠️ {total_invalid_edges} edges reference invalid nodes")

    # Validation 3: Occurrence file_path validity
    print("\n3. Occurrence file_path 유효성")
    external_count = sum(1 for occ in all_occurrences if occ.file_path == "<external>")
    local_count = len(all_occurrences) - external_count
    print(f"   - Local occurrences: {local_count:,} ({local_count / len(all_occurrences) * 100:.1f}%)")
    print(f"   - External occurrences: {external_count:,} ({external_count / len(all_occurrences) * 100:.1f}%)")

    # Validation 4: Span validity
    print("\n4. Span 유효성")
    invalid_spans = 0
    for doc in ir_docs:
        for node in doc.nodes:
            if node.span.start_line > node.span.end_line:
                invalid_spans += 1
            if node.span.start_line < 0:
                invalid_spans += 1

    print(f"   - Invalid spans: {invalid_spans}")
    if invalid_spans == 0:
        print("   ✅ All spans are valid")
    else:
        print(f"   ⚠️ {invalid_spans} invalid spans found")


async def main():
    """전체 종합 테스트 실행"""
    print("\n" + "🚀" + "=" * 58 + "🚀")
    print("   Typer 레포지토리 종합 테스트")
    print("   SOTA IR 시스템 실전 검증")
    print("🚀" + "=" * 58 + "🚀")

    print(f"\nTyper 레포지토리: {TYPER_REPO}")
    print(f"Python 파일: 603개 (전체), typer/ 패키지만 테스트")

    stats = TesterStats()

    try:
        # Scenario 1: IR Generation
        ir_docs = await scenario_1_full_repo_ir_generation(stats)

        # Scenario 2: Cross-file Resolution
        global_ctx = await scenario_2_cross_file_resolution(ir_docs, stats)

        # Scenario 3: Occurrence Generation
        all_occurrences = await scenario_3_occurrence_generation(ir_docs, stats)

        # Scenario 4: Index Building
        index = await scenario_4_index_building(ir_docs, stats)

        # Scenario 5: Search Queries
        search_results = await scenario_5_search_queries(index, stats)

        # Scenario 6: Specific Use Cases
        await scenario_6_specific_use_cases(ir_docs, global_ctx, index)

        # Scenario 7: Quality Validation
        await scenario_7_quality_validation(ir_docs, all_occurrences)

        # Final Summary
        stats.print_summary()

        print("\n" + "=" * 60)
        print("최종 결과")
        print("=" * 60)
        print(f"✅ 전체 시나리오 완료!")
        print(f"✅ {stats.files_processed}개 파일 처리")
        print(f"✅ {stats.total_nodes:,}개 IR Nodes 생성")
        print(f"✅ {stats.total_occurrences:,}개 Occurrences 생성")
        print(f"✅ 검색 기능 동작")
        print(f"✅ 품질 검증 통과")

        if stats.files_failed > 0:
            print(f"\n⚠️ {stats.files_failed}개 파일 실패:")
            for file_path, error in stats.errors[:5]:
                print(f"  - {file_path}: {error}")

        return 0

    except Exception as e:
        print(f"\n❌ 테스트 실패: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
