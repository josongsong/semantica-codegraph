#!/usr/bin/env python3
"""
성능 비판적 검증

실제로 빠른지 확인:
1. 대규모 파일 처리 시간
2. 메모리 사용량
3. 병목 구간 식별
"""

import time
import psutil
import os
from pathlib import Path
from src.contexts.code_foundation.infrastructure.generators.python_generator import PythonIRGenerator
from src.contexts.code_foundation.infrastructure.parsing import AstTree, SourceFile


def measure_memory():
    """현재 프로세스 메모리 사용량 (MB)"""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def test_single_file_performance():
    """단일 파일 처리 성능"""
    print("\n" + "=" * 60)
    print("1. 단일 파일 성능 (typer/main.py)")
    print("=" * 60)

    file_path = Path("benchmark/repo-test/small/typer/typer/main.py")
    content = file_path.read_text()

    print(f"파일 크기: {len(content):,} bytes ({len(content.splitlines())} lines)")

    # 파싱 시간
    start = time.perf_counter()
    source = SourceFile.from_content(str(file_path), content, "python")
    ast = AstTree.parse(source)
    parse_time = (time.perf_counter() - start) * 1000

    print(f"✅ Parsing: {parse_time:.2f}ms")

    # IR 생성 시간
    mem_before = measure_memory()
    start = time.perf_counter()
    generator = PythonIRGenerator(repo_id="typer")
    ir_doc = generator.generate(source, "typer", ast)
    ir_time = (time.perf_counter() - start) * 1000
    mem_after = measure_memory()

    print(f"✅ IR Generation: {ir_time:.2f}ms")
    print(f"✅ Memory: {mem_after - mem_before:.2f}MB")
    print(f"✅ Nodes: {len(ir_doc.nodes)}")
    print(f"✅ Edges: {len(ir_doc.edges)}")

    # 처리량
    throughput = len(content) / (ir_time / 1000) / 1024
    print(f"✅ Throughput: {throughput:.2f} KB/s")

    return ir_time


def test_batch_performance():
    """배치 처리 성능"""
    print("\n" + "=" * 60)
    print("2. 배치 처리 성능 (16 files)")
    print("=" * 60)

    typer_path = Path("benchmark/repo-test/small/typer/typer")
    files = list(typer_path.glob("*.py"))[:16]

    total_size = sum(f.stat().st_size for f in files)
    total_lines = 0

    print(f"파일 수: {len(files)}")
    print(f"총 크기: {total_size:,} bytes")

    # 배치 처리
    mem_before = measure_memory()
    start = time.perf_counter()

    all_docs = []
    for file in files:
        try:
            content = file.read_text()
            total_lines += len(content.splitlines())
            source = SourceFile.from_content(str(file), content, "python")
            ast = AstTree.parse(source)
            generator = PythonIRGenerator(repo_id="typer")
            ir_doc = generator.generate(source, "typer", ast)
            all_docs.append(ir_doc)
        except:
            pass

    total_time = (time.perf_counter() - start) * 1000
    mem_after = measure_memory()

    print(f"총 라인: {total_lines:,} lines")
    print(f"✅ Total Time: {total_time:.2f}ms")
    print(f"✅ Avg per file: {total_time / len(files):.2f}ms")
    print(f"✅ Memory: {mem_after - mem_before:.2f}MB")

    # 통계
    total_nodes = sum(len(doc.nodes) for doc in all_docs)
    total_edges = sum(len(doc.edges) for doc in all_docs)

    print(f"✅ Total Nodes: {total_nodes:,}")
    print(f"✅ Total Edges: {total_edges:,}")
    print(f"✅ Throughput: {total_size / 1024 / (total_time / 1000):.2f} KB/s")
    print(f"✅ Lines/sec: {total_lines / (total_time / 1000):,.0f}")

    return total_time, len(files)


def test_large_file_performance():
    """대용량 파일 처리 (worst case)"""
    print("\n" + "=" * 60)
    print("3. 대용량 파일 처리 (synthetic)")
    print("=" * 60)

    # 큰 파일 생성
    large_code = []
    for i in range(100):
        large_code.append(f"""
class TestClass{i}:
    def __init__(self):
        self.value = {i}
    
    def method_{i}(self, x: int) -> int:
        result = x + self.value
        temp = result * 2
        return temp
    
    def method_{i}_b(self, y: str) -> str:
        return f"{{y}}_{i}"
""")

    content = "\n".join(large_code)

    print(f"생성 크기: {len(content):,} bytes ({len(content.splitlines())} lines)")

    # 처리
    mem_before = measure_memory()
    start = time.perf_counter()

    source = SourceFile.from_content("large.py", content, "python")
    ast = AstTree.parse(source)
    generator = PythonIRGenerator(repo_id="test")
    ir_doc = generator.generate(source, "test", ast)

    total_time = (time.perf_counter() - start) * 1000
    mem_after = measure_memory()

    print(f"✅ Total Time: {total_time:.2f}ms")
    print(f"✅ Memory: {mem_after - mem_before:.2f}MB")
    print(f"✅ Nodes: {len(ir_doc.nodes):,}")
    print(f"✅ Edges: {len(ir_doc.edges):,}")
    print(f"✅ Throughput: {len(content) / 1024 / (total_time / 1000):.2f} KB/s")

    return total_time


def test_scalability():
    """확장성 테스트"""
    print("\n" + "=" * 60)
    print("4. 확장성 테스트 (1, 5, 10, 20 files)")
    print("=" * 60)

    typer_path = Path("benchmark/repo-test/small/typer/typer")
    all_files = list(typer_path.glob("*.py"))

    results = []

    for count in [1, 5, 10, 20]:
        files = all_files[: min(count, len(all_files))]

        start = time.perf_counter()
        processed = 0

        for file in files:
            try:
                content = file.read_text()
                source = SourceFile.from_content(str(file), content, "python")
                ast = AstTree.parse(source)
                generator = PythonIRGenerator(repo_id="typer")
                ir_doc = generator.generate(source, "typer", ast)
                processed += 1
            except:
                pass

        total_time = (time.perf_counter() - start) * 1000
        avg_time = total_time / processed if processed > 0 else 0

        results.append((count, total_time, avg_time))
        print(f"  {count:2d} files: {total_time:7.2f}ms total, {avg_time:6.2f}ms avg")

    # 선형성 체크
    print("\n확장성 분석:")
    if len(results) >= 2:
        ratio_10_5 = results[2][1] / results[1][1] if results[1][1] > 0 else 0
        ratio_20_10 = results[3][1] / results[2][1] if results[2][1] > 0 else 0

        print(f"  10 files / 5 files: {ratio_10_5:.2f}x")
        print(f"  20 files / 10 files: {ratio_20_10:.2f}x")

        if ratio_10_5 < 2.5 and ratio_20_10 < 2.5:
            print("  ✅ 선형 확장성 양호")
        else:
            print("  ⚠️ 비선형 확장 (병목 존재)")


def test_bottleneck_analysis():
    """병목 구간 분석"""
    print("\n" + "=" * 60)
    print("5. 병목 구간 분석")
    print("=" * 60)

    file_path = Path("benchmark/repo-test/small/typer/typer/main.py")
    content = file_path.read_text()

    # Step by step timing
    timings = {}

    # 1. File I/O
    start = time.perf_counter()
    _ = file_path.read_text()
    timings["file_io"] = (time.perf_counter() - start) * 1000

    # 2. Source creation
    start = time.perf_counter()
    source = SourceFile.from_content(str(file_path), content, "python")
    timings["source_creation"] = (time.perf_counter() - start) * 1000

    # 3. Parsing (tree-sitter)
    start = time.perf_counter()
    ast = AstTree.parse(source)
    timings["parsing"] = (time.perf_counter() - start) * 1000

    # 4. IR Generation
    start = time.perf_counter()
    generator = PythonIRGenerator(repo_id="typer")
    ir_doc = generator.generate(source, "typer", ast)
    timings["ir_generation"] = (time.perf_counter() - start) * 1000

    # 5. Graph building (edges)
    # Already included in IR generation

    total = sum(timings.values())

    print("\n시간 분포:")
    for name, time_ms in sorted(timings.items(), key=lambda x: -x[1]):
        pct = time_ms / total * 100
        bar = "█" * int(pct / 2)
        print(f"  {name:20s}: {time_ms:7.2f}ms ({pct:5.1f}%) {bar}")

    print(f"\n총 시간: {total:.2f}ms")

    # 병목 판정
    max_name, max_time = max(timings.items(), key=lambda x: x[1])
    if max_time / total > 0.5:
        print(f"⚠️ 병목: {max_name} ({max_time / total * 100:.1f}%)")
    else:
        print("✅ 균형잡힌 처리 시간")


def main():
    print("\n" + "🔍" * 30)
    print("성능 비판적 검증")
    print("🔍" * 30)

    # Run tests
    single_time = test_single_file_performance()
    batch_time, file_count = test_batch_performance()
    large_time = test_large_file_performance()
    test_scalability()
    test_bottleneck_analysis()

    # Final verdict
    print("\n" + "=" * 60)
    print("최종 판정")
    print("=" * 60)

    print(f"\n단일 파일: {single_time:.2f}ms")
    print(f"배치 처리: {batch_time:.2f}ms ({file_count} files, {batch_time / file_count:.2f}ms avg)")
    print(f"대용량 파일: {large_time:.2f}ms")

    # 기준
    ACCEPTABLE_SINGLE = 100  # 100ms
    ACCEPTABLE_BATCH_AVG = 20  # 20ms per file

    verdict = []

    if single_time < ACCEPTABLE_SINGLE:
        verdict.append("✅ 단일 파일 성능 양호")
    else:
        verdict.append(f"⚠️ 단일 파일 느림 ({single_time:.0f}ms > {ACCEPTABLE_SINGLE}ms)")

    if batch_time / file_count < ACCEPTABLE_BATCH_AVG:
        verdict.append("✅ 배치 처리 성능 양호")
    else:
        verdict.append(f"⚠️ 배치 처리 느림 ({batch_time / file_count:.0f}ms > {ACCEPTABLE_BATCH_AVG}ms)")

    print("\n" + "\n".join(verdict))

    # Incremental update 필요성 판단
    print("\n" + "=" * 60)
    print("Incremental Update 필요성")
    print("=" * 60)

    avg_time = batch_time / file_count

    if avg_time < 10:
        print(f"✅ 현재 성능 충분 ({avg_time:.1f}ms/file)")
        print("⚠️ Incremental Update는 선택 사항")
    elif avg_time < 50:
        print(f"⚠️ 성능 개선 권장 ({avg_time:.1f}ms/file)")
        print("💡 Incremental Update 구현 추천")
    else:
        print(f"❌ 성능 문제 ({avg_time:.1f}ms/file)")
        print("🚨 Incremental Update 필수!")

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
