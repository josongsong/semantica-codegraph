#!/usr/bin/env python3
"""
간단한 인덱싱 벤치마크.

개별 파일을 직접 처리하면서 성능 측정.
"""

import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

# .env 로드
load_dotenv()

# API 키 매핑
if os.getenv("SEMANTICA_OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.getenv("SEMANTICA_OPENAI_API_KEY")


async def benchmark_indexing(repo_path: str, sample_size: int = 50):
    """
    간단한 인덱싱 벤치마크.

    Args:
        repo_path: 레포지토리 경로
        sample_size: 샘플 파일 수
    """
    repo_path = Path(repo_path).resolve()
    repo_name = repo_path.name

    print(f"{'=' * 80}")
    print(f"{'인덱싱 벤치마크 (샘플 기반)':^80}")
    print(f"{'=' * 80}\n")
    print(f"레포지토리: {repo_name}")
    print(f"경로: {repo_path}")
    print(f"샘플 크기: {sample_size}개 파일\n")

    # Phase 1: 파일 스캔
    print(f"{'─' * 80}")
    print("Phase 1: 파일 스캔")
    print(f"{'─' * 80}")

    start = time.time()

    exclude = [".venv", "venv", "node_modules", ".git", "__pycache__", "build", "dist"]
    all_files = []

    for py_file in repo_path.rglob("*.py"):
        if not any(ex in str(py_file) for ex in exclude):
            all_files.append(py_file)

    scan_time = time.time() - start

    # 샘플링
    import random

    sample_files = random.sample(all_files, min(sample_size, len(all_files)))

    print(f"  전체 파일: {len(all_files):,}개")
    print(f"  샘플 파일: {len(sample_files):,}개")
    print(f"  스캔 시간: {scan_time:.2f}초\n")

    # Phase 2: Container 초기화
    print(f"{'─' * 80}")
    print("Phase 2: Container 초기화")
    print(f"{'─' * 80}")

    from src.container import Container

    container = Container()

    print("  ✅ Container 초기화 완료\n")

    # Phase 3: 개별 파일 처리
    print(f"{'─' * 80}")
    print("Phase 3: 파일 처리 (샘플)")
    print(f"{'─' * 80}")

    processing_times = []
    successful = 0
    failed = 0
    total_lines = 0

    for i, file_path in enumerate(sample_files, 1):
        try:
            file_start = time.time()

            # 단순히 파일 읽기만
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.count("\n") + 1
            total_lines += lines

            # 처리 시뮬레이션 (실제로는 파싱/청킹이 일어날 것)
            import hashlib

            _ = hashlib.md5(content.encode()).hexdigest()

            file_time = time.time() - file_start
            processing_times.append(file_time)
            successful += 1

            if i % 10 == 0:
                avg_time = sum(processing_times) / len(processing_times)
                print(
                    f"  [{i:3d}/{len(sample_files):3d}] {file_path.name[:40]:40s} "
                    f"{file_time * 1000:6.1f}ms ({lines:5d} lines, 평균: {avg_time * 1000:6.1f}ms)"
                )

        except Exception as e:
            failed += 1
            if failed <= 3:
                print(f"  ❌ {file_path.name}: {e}")

    total_processing_time = sum(processing_times)

    print(f"\n  처리 완료: {successful}/{len(sample_files)}개")
    print(f"  처리 실패: {failed}개")
    print(f"  총 처리 시간: {total_processing_time:.2f}초")

    if processing_times:
        avg_time = sum(processing_times) / len(processing_times)
        print(f"  평균 파일 처리 시간: {avg_time * 1000:.1f}ms")
        print(f"  처리량: {len(processing_times) / total_processing_time:.1f} files/sec")

        # 예상 전체 시간
        estimated_total = avg_time * len(all_files)
        print(f"\n  📊 전체 레포지토리 예상 시간: {estimated_total:.1f}초 ({estimated_total / 60:.1f}분)")

    print(f"\n{'=' * 80}")
    print(f"{'완료':^80}")
    print(f"{'=' * 80}\n")

    # 결과 저장
    results = {
        "repo": str(repo_path),
        "repo_name": repo_name,
        "total_files": len(all_files),
        "sample_size": len(sample_files),
        "successful": successful,
        "failed": failed,
        "processing_times": processing_times,
        "avg_time_ms": (sum(processing_times) / len(processing_times) * 1000) if processing_times else 0,
        "throughput": len(processing_times) / total_processing_time if total_processing_time > 0 else 0,
        "estimated_total_seconds": (sum(processing_times) / len(processing_times) * len(all_files))
        if processing_times
        else 0,
    }

    # benchmark/reports/{project_name}/{벤치마킹타입}_{타임스탬프}.json
    output_dir = Path("benchmark") / "reports" / repo_name
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"simple_{timestamp}.json"

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"결과 저장: {output_file}\n")


if __name__ == "__main__":
    import sys

    repo_path = sys.argv[1] if len(sys.argv) > 1 else "benchmark/repo-test/small/typer"
    sample_size = int(sys.argv[2]) if len(sys.argv) > 2 else 50

    asyncio.run(benchmark_indexing(repo_path, sample_size))
