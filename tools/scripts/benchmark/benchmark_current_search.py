"""
RFC-020 Phase 0: 기존 Zoekt/PostgreSQL 성능 기준선 측정

Phase 4 마이그레이션 시 성능 비교를 위한 baseline 측정.

Usage:
    python scripts/benchmark_current_search.py --repo-id test --output baseline.json
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

from codegraph_shared.common.observability import get_logger
from codegraph_shared.infra.config.settings import Settings

logger = get_logger(__name__)


async def measure_zoekt_search(zoekt_index, repo_id: str, queries: list[str], iterations: int = 10) -> dict:
    """Zoekt 검색 성능 측정"""
    results = []

    for query in queries:
        durations = []
        for _ in range(iterations):
            start = time.time()
            try:
                hits = await zoekt_index.search(repo_id, "snapshot", query, limit=50)
                duration_ms = (time.time() - start) * 1000
                durations.append(duration_ms)
            except Exception as e:
                logger.warning(f"Zoekt search failed: {query}", error=str(e))
                durations.append(-1)

        valid_durations = [d for d in durations if d > 0]
        results.append(
            {
                "query": query,
                "mean_ms": sum(valid_durations) / len(valid_durations) if valid_durations else -1,
                "min_ms": min(valid_durations) if valid_durations else -1,
                "max_ms": max(valid_durations) if valid_durations else -1,
                "samples": len(valid_durations),
            }
        )

    return {
        "engine": "zoekt",
        "queries": results,
        "avg_mean_ms": sum(r["mean_ms"] for r in results if r["mean_ms"] > 0) / len(results),
    }


async def measure_postgres_fuzzy(fuzzy_index, repo_id: str, queries: list[str], iterations: int = 10) -> dict:
    """PostgreSQL pg_trgm fuzzy 성능 측정"""
    results = []

    for query in queries:
        durations = []
        for _ in range(iterations):
            start = time.time()
            try:
                hits = await fuzzy_index.search(repo_id, "snapshot", query, limit=50)
                duration_ms = (time.time() - start) * 1000
                durations.append(duration_ms)
            except Exception as e:
                logger.warning(f"Fuzzy search failed: {query}", error=str(e))
                durations.append(-1)

        valid_durations = [d for d in durations if d > 0]
        results.append(
            {
                "query": query,
                "mean_ms": sum(valid_durations) / len(valid_durations) if valid_durations else -1,
                "min_ms": min(valid_durations) if valid_durations else -1,
                "max_ms": max(valid_durations) if valid_durations else -1,
                "samples": len(valid_durations),
            }
        )

    return {
        "engine": "postgres_fuzzy",
        "queries": results,
        "avg_mean_ms": sum(r["mean_ms"] for r in results if r["mean_ms"] > 0) / len(results),
    }


async def main():
    parser = argparse.ArgumentParser(description="RFC-020: Measure baseline search performance")
    parser.add_argument("--repo-id", required=True, help="Repository ID")
    parser.add_argument("--output", default="baseline.json", help="Output JSON file")
    parser.add_argument("--iterations", type=int, default=10, help="Number of iterations per query")
    args = parser.parse_args()

    # Test queries (다양한 패턴)
    queries = [
        "function",  # 일반 단어
        "Calculator",  # CamelCase
        "process_payment",  # snake_case
        "http",  # 짧은 단어
        "get_user_by_id",  # 긴 함수명
    ]

    logger.info(f"Measuring baseline for repo_id={args.repo_id}, queries={len(queries)}")

    try:
        # DI 초기화 (Zoekt/PostgreSQL 현재 상태)
        settings = Settings()

        # TODO: DI container에서 실제 인덱스 가져오기
        # from src.container import Container
        # container = Container(settings)
        # zoekt_index = container.index.lexical_index
        # fuzzy_index = container.index.fuzzy_index

        # 임시: 수동 초기화 (Phase 4 전까지)
        logger.warning("Manual DI initialization - TODO: use Container")
        zoekt_result = {"engine": "zoekt", "queries": [], "note": "Not measured (manual DI needed)"}
        fuzzy_result = {"engine": "postgres_fuzzy", "queries": [], "note": "Not measured (manual DI needed)"}

        # Measure (DI 연동 후 활성화)
        # zoekt_result = await measure_zoekt_search(zoekt_index, args.repo_id, queries, args.iterations)
        # fuzzy_result = await measure_postgres_fuzzy(fuzzy_index, args.repo_id, queries, args.iterations)

        baseline = {
            "repo_id": args.repo_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "iterations": args.iterations,
            "queries": queries,
            "results": {
                "zoekt": zoekt_result,
                "postgres_fuzzy": fuzzy_result,
            },
        }

        # Save
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(baseline, f, indent=2)

        logger.info(f"Baseline saved to {output_path}")
        print(f"\nBaseline saved: {output_path}")
        print(f"Zoekt avg: {zoekt_result.get('avg_mean_ms', 'N/A')} ms")
        print(f"Fuzzy avg: {fuzzy_result.get('avg_mean_ms', 'N/A')} ms")

    except Exception as e:
        logger.error("Baseline measurement failed", error=str(e))
        raise


if __name__ == "__main__":
    asyncio.run(main())
