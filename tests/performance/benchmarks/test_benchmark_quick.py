#!/usr/bin/env python3
"""
빠른 인덱싱 벤치마크 (간단 버전).
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# 로깅 설정 (ERROR만)
logging.basicConfig(level=logging.ERROR)


async def main():
    """메인"""
    load_dotenv()

    # API 키 매핑
    if os.getenv("SEMANTICA_OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.getenv("SEMANTICA_OPENAI_API_KEY")

    from src.container import Container

    container = Container()

    # 테스트 레포지토리
    bench_dir = Path(__file__).parent / "benchmark" / "repo-test"

    repos = [
        (bench_dir / "small" / "typer", "Typer (Small)"),
        (bench_dir / "medium" / "rich", "Rich (Medium)"),
    ]

    print(f"\n{'=' * 80}")
    print(f" 인덱싱 벤치마크")
    print(f"{'=' * 80}")

    results = []

    for repo_path, name in repos:
        if not repo_path.exists():
            print(f"\n❌ {name}: 레포지토리 없음")
            continue

        py_files = list(repo_path.rglob("*.py"))
        exclude = [".venv", "venv", "__pycache__", "build", "dist", ".git"]
        py_files = [f for f in py_files if not any(ex in str(f) for ex in exclude)]

        print(f"\n📦 {name}")
        print(f"   경로: {repo_path}")
        print(f"   파일: {len(py_files)}개")

        start = time.time()

        try:
            result = await container.indexing_orchestrator.index_repository_full(
                repo_path=str(repo_path),
                repo_id=name.lower().replace(" ", "_").replace("(", "").replace(")", ""),
                snapshot_id="bench",
                force=True,
            )

            elapsed = time.time() - start

            print(f"   ✅ 완료: {elapsed:.1f}s")
            print(f"   처리: {result.files_processed}개 파일")
            print(f"   속도: {result.files_processed / elapsed:.1f} files/s")

            if result.files_processed > 0:
                print(f"   파일당: {elapsed / result.files_processed * 1000:.1f}ms")

            results.append(
                {
                    "name": name,
                    "files": result.files_processed,
                    "time": elapsed,
                    "fps": result.files_processed / elapsed if elapsed > 0 else 0,
                }
            )

        except Exception as e:
            elapsed = time.time() - start
            print(f"   ❌ 실패: {e}")
            print(f"   경과: {elapsed:.1f}s")

    # 요약
    if results:
        print(f"\n{'=' * 80}")
        print(f" 요약")
        print(f"{'=' * 80}")
        print(f"\n{'레포지토리':20} {'파일':>8} {'시간(s)':>10} {'속도(f/s)':>12}")
        print(f"{'-' * 80}")

        for r in results:
            print(f"{r['name']:20} {r['files']:8} {r['time']:10.1f} {r['fps']:12.1f}")

        print(f"\n✅ 벤치마크 완료!")


if __name__ == "__main__":
    asyncio.run(main())
