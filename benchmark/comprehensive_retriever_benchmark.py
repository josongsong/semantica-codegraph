"""
Comprehensive Retriever Benchmark - All 41 Scenarios

Tests retriever across ALL scenarios from 리트리버시나리오.md:
- Priority 1 (20 scenarios): Engine-based essentials
- Priority 2 (20 scenarios): Production essentials
- Priority 3 (1 scenario): RepoMap

This benchmark validates that the retriever can handle real-world
LLM agent queries across all categories:
- Symbol/Definition navigation
- Call relationships & dependencies
- Pipeline/E2E flows
- API/DTO analysis
- Config/Environment tracking
- Refactoring impact analysis
- Quality/Security/Debugging
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Reuse infrastructure from real_retriever_benchmark
import sys
sys.path.insert(0, str(Path(__file__).parent))

from real_retriever_benchmark import (
    MockLexicalIndex,
    MockVectorIndex,
    MockSymbolIndex,
    FusionV1,
    FusionV2,
    FusionV3Simplified,
    BenchmarkResult,
    calculate_ndcg,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ScenarioBenchmarkQuery:
    """Query with scenario mapping."""

    scenario_id: str  # e.g., "1-1", "2-5"
    scenario_name: str
    query: str
    intent: str
    expected_in_top_k: list[str]
    k: int = 10
    required_axes: list[str] = None  # e.g., ["Symbol Index", "AST"]

    def __post_init__(self):
        if self.required_axes is None:
            self.required_axes = []


# ============================================================
# Comprehensive Query Set (41 Scenarios)
# ============================================================

COMPREHENSIVE_QUERIES = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Priority 1: Engine-Based Essentials (20 queries)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # A. Symbol/Definition/Structure Navigation
    ScenarioBenchmarkQuery(
        scenario_id="1-1",
        scenario_name="정의 위치 / 코드 블럭 찾기",
        query="Chunk class definition",
        intent="symbol_nav",
        expected_in_top_k=["foundation/chunk/models.py"],
        k=5,
        required_axes=["Symbol Index", "AST"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-2",
        scenario_name="enum · 인터페이스 정의 찾기",
        query="GraphNodeKind enum",
        intent="symbol_nav",
        expected_in_top_k=["foundation/graph/models.py"],
        k=5,
        required_axes=["Symbol Index"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-3",
        scenario_name="라우트 → 핸들러 매핑",
        query="POST /search route handler",
        intent="symbol_nav",
        expected_in_top_k=["server/api_server/routes/search.py"],
        k=5,
        required_axes=["AST", "Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-4",
        scenario_name="인터페이스/포트 구현체 목록",
        query="LLMInterface implementations",
        intent="symbol_nav",
        expected_in_top_k=["infra/llm/openai.py"],
        k=10,
        required_axes=["Symbol Index"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-5",
        scenario_name="import/export 구조 분석",
        query="what does retriever package export",
        intent="code_search",
        expected_in_top_k=["retriever/__init__.py"],
        k=5,
        required_axes=["AST", "Graph"],
    ),

    # B. Call Relationships & Dependencies
    ScenarioBenchmarkQuery(
        scenario_id="1-6",
        scenario_name="특정 함수 호출하는 모든 곳",
        query="who calls chunk builder build method",
        intent="flow_trace",
        expected_in_top_k=["foundation/chunk/", "index/"],
        k=10,
        required_axes=["Graph", "Symbol Index"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-7",
        scenario_name="특정 클래스/타입 사용처",
        query="where is SearchHit type used",
        intent="flow_trace",
        expected_in_top_k=["index/", "retriever/"],
        k=10,
        required_axes=["Graph", "AST"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-8",
        scenario_name="리팩토링 영향 범위",
        query="impact of renaming InterleavingWeights",
        intent="flow_trace",
        expected_in_top_k=["retriever/fusion/"],
        k=10,
        required_axes=["Graph", "Symbol Index", "AST"],
    ),

    # C. Pipeline / E2E Flows
    ScenarioBenchmarkQuery(
        scenario_id="1-9",
        scenario_name="인덱싱 파이프라인 경로",
        query="indexing pipeline from chunks to search",
        intent="flow_trace",
        expected_in_top_k=["index/service.py", "index/factory.py"],
        k=10,
        required_axes=["Graph", "Chunk Hierarchy"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-10",
        scenario_name="검색 → 벡터 → reranker 흐름",
        query="retriever search to reranker flow",
        intent="flow_trace",
        expected_in_top_k=["retriever/service", "retriever/fusion/", "retriever/hybrid/"],
        k=10,
        required_axes=["Graph", "Weighted Fusion"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-11",
        scenario_name="GraphStore 초기화 경로",
        query="how is Kuzu graph database initialized",
        intent="flow_trace",
        expected_in_top_k=["infra/graph/kuzu.py", "container.py"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-12",
        scenario_name="에러 핸들링 전체 플로우",
        query="exception handling flow in API server",
        intent="flow_trace",
        expected_in_top_k=["server/api_server/"],
        k=10,
        required_axes=["Runtime Info"],
    ),

    # D. API / DTO
    ScenarioBenchmarkQuery(
        scenario_id="1-13",
        scenario_name="POST/GET API 목록",
        query="list all API endpoints",
        intent="code_search",
        expected_in_top_k=["server/api_server/routes/"],
        k=10,
        required_axes=["AST"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-14",
        scenario_name="DTO 정의 위치",
        query="SearchRequest DTO definition",
        intent="symbol_nav",
        expected_in_top_k=["retriever/", "server/"],
        k=5,
        required_axes=["AST"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-15",
        scenario_name="DTO 사용처 / 변경 영향",
        query="where is Chunk model used",
        intent="flow_trace",
        expected_in_top_k=["foundation/chunk/", "index/", "retriever/"],
        k=15,
        required_axes=["Graph", "Symbol Index"],
    ),

    # E. Config / Environment / Service Calls
    ScenarioBenchmarkQuery(
        scenario_id="1-16",
        scenario_name="config override 흐름",
        query="how are settings overridden",
        intent="flow_trace",
        expected_in_top_k=["infra/config/settings.py"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-17",
        scenario_name="서비스 간 호출 관계",
        query="how does API server call indexing service",
        intent="flow_trace",
        expected_in_top_k=["server/", "index/service.py"],
        k=10,
        required_axes=["Runtime Info", "Graph"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-18",
        scenario_name="tracing/logging 흐름",
        query="logging configuration and usage",
        intent="code_search",
        expected_in_top_k=["infra/config/logging.py"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-19",
        scenario_name="index rebuild 배치/스케줄러",
        query="batch indexing job implementation",
        intent="code_search",
        expected_in_top_k=["index/", "pipeline/"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="1-20",
        scenario_name="ACL/보안 필터 테스트",
        query="security filtering in search",
        intent="code_search",
        expected_in_top_k=["retriever/", "server/"],
        k=10,
        required_axes=["Runtime Info", "Domain Metadata"],
    ),

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Priority 2: Production Essentials (20 queries)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # A. Structure / Refactoring / Quality
    ScenarioBenchmarkQuery(
        scenario_id="2-1",
        scenario_name="인터페이스 구현체 찾기",
        query="find all ChunkStore implementations",
        intent="symbol_nav",
        expected_in_top_k=["foundation/chunk/store.py", "infra/storage/"],
        k=10,
        required_axes=["Symbol Index"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-2",
        scenario_name="deprecated API 탐지",
        query="find deprecated API usages",
        intent="code_search",
        expected_in_top_k=["retriever/fusion/smart_interleaving.py"],  # v1 is deprecated
        k=10,
        required_axes=["Symbol Index", "Lexical"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-3",
        scenario_name="unused 변수/함수",
        query="find unused helper functions",
        intent="code_search",
        expected_in_top_k=[],  # Would need static analysis
        k=10,
        required_axes=["Graph", "AST"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-4",
        scenario_name="side effect 탐지",
        query="global state modifications in caching",
        intent="code_search",
        expected_in_top_k=["infra/cache/"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-5",
        scenario_name="import cycle 감지",
        query="circular import dependencies",
        intent="code_search",
        expected_in_top_k=[],  # Would need dependency analysis
        k=10,
        required_axes=["Graph"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-6",
        scenario_name="exception throw/handle 매핑",
        query="where are IndexingError exceptions raised and caught",
        intent="flow_trace",
        expected_in_top_k=["index/", "retriever/exceptions.py"],
        k=10,
        required_axes=["Runtime Info"],
    ),

    # B. Parsing / Caching / Events / Batch
    ScenarioBenchmarkQuery(
        scenario_id="2-7",
        scenario_name="error code 사용처",
        query="where is error code ERR_001 used",
        intent="code_search",
        expected_in_top_k=[],  # Would need specific error codes
        k=10,
        required_axes=["Lexical", "Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-8",
        scenario_name="파싱 파이프라인 흐름",
        query="AST to IR to graph pipeline",
        intent="flow_trace",
        expected_in_top_k=["foundation/parsing/", "foundation/generators/", "foundation/graph/"],
        k=15,
        required_axes=["AST", "IR"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-9",
        scenario_name="caching layer 흐름",
        query="embedding cache implementation",
        intent="code_search",
        expected_in_top_k=["infra/cache/", "infra/vector/"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-10",
        scenario_name="event-driven 흐름",
        query="event publishing and handling",
        intent="code_search",
        expected_in_top_k=[],  # Would need event system
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-11",
        scenario_name="배치 job / scheduler",
        query="scheduled indexing jobs",
        intent="code_search",
        expected_in_top_k=["pipeline/", "index/"],
        k=10,
        required_axes=["Runtime Info"],
    ),

    # C. CLI / gRPC / Multi-version DTO
    ScenarioBenchmarkQuery(
        scenario_id="2-12",
        scenario_name="CLI → internal 모듈",
        query="CLI command to indexing flow",
        intent="flow_trace",
        expected_in_top_k=["cli/"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-13",
        scenario_name="gRPC / retry / backoff",
        query="retry logic for vector database",
        intent="code_search",
        expected_in_top_k=["infra/vector/", "infra/graph/"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-14",
        scenario_name="DTO / API 버전 분기",
        query="v1 vs v2 API differences",
        intent="code_search",
        expected_in_top_k=["retriever/fusion/smart_interleaving.py", "retriever/fusion/smart_interleaving_v2.py"],
        k=10,
        required_axes=["Symbol Index", "AST"],
    ),

    # D. Security / Env / Integrity / Debugging
    ScenarioBenchmarkQuery(
        scenario_id="2-15",
        scenario_name="deprecated API 사용 탐지",
        query="still using old SmartInterleaver v1",
        intent="code_search",
        expected_in_top_k=["retriever/service_optimized.py"],  # Has fallback to v1
        k=10,
        required_axes=["Symbol Index", "Lexical"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-16",
        scenario_name="env var 사용처",
        query="environment variable usage",
        intent="code_search",
        expected_in_top_k=["infra/config/"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-17",
        scenario_name="보안 / 입력 검증 누락 탐지",
        query="input validation in API endpoints",
        intent="code_search",
        expected_in_top_k=["server/api_server/routes/"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-18",
        scenario_name="크로스-스토리지 무결성",
        query="consistency between Qdrant and Kuzu",
        intent="code_search",
        expected_in_top_k=["infra/vector/", "infra/graph/"],
        k=10,
        required_axes=["Runtime Info", "Graph"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-19",
        scenario_name="디버깅 / 로그 기반 역추적",
        query="trace error log back to source",
        intent="flow_trace",
        expected_in_top_k=["infra/config/logging.py"],
        k=10,
        required_axes=["Runtime Info"],
    ),
    ScenarioBenchmarkQuery(
        scenario_id="2-20",
        scenario_name="테스트 / 타입 / 리팩토링 영향",
        query="test coverage for chunk builder",
        intent="code_search",
        expected_in_top_k=["tests/foundation/test_chunk_builder.py"],
        k=10,
        required_axes=["Graph", "AST"],
    ),

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Priority 3: RepoMap (1 query)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    ScenarioBenchmarkQuery(
        scenario_id="2-21",
        scenario_name="RepoMap / 프로젝트 구조 요약",
        query="project structure summary and important files",
        intent="balanced",
        expected_in_top_k=["retriever/", "index/", "foundation/"],
        k=20,
        required_axes=["Graph", "Chunk Hierarchy", "Domain Metadata", "Vector", "Weighted Fusion"],
    ),
]


# ============================================================
# Benchmark Runner
# ============================================================


async def run_single_scenario_benchmark(
    query_spec: ScenarioBenchmarkQuery,
    fusion_impl: Any,
    lexical_idx: MockLexicalIndex,
    vector_idx: MockVectorIndex,
    symbol_idx: MockSymbolIndex,
    version: str,
) -> BenchmarkResult:
    """Run benchmark for a single scenario."""
    # Set weights for intent
    fusion_impl.set_weights_for_intent(query_spec.intent)

    # Start timing
    start_time = time.perf_counter()

    # Search all indexes
    lexical_results = await lexical_idx.search(query_spec.query, limit=50)
    vector_results = await vector_idx.search(query_spec.query, limit=50)
    symbol_results = await symbol_idx.search(query_spec.query, limit=50)

    # Fuse results
    strategy_results = {
        "lexical": lexical_results,
        "vector": vector_results,
        "symbol": symbol_results,
    }

    fused_results = fusion_impl.fuse(strategy_results)

    # End timing
    latency_ms = (time.perf_counter() - start_time) * 1000

    # Evaluate precision
    top_k = fused_results[: query_spec.k]
    top_k_paths = [r["file_path"] for r in top_k]

    # Check how many expected files are in top-K
    hits = 0
    for expected in query_spec.expected_in_top_k:
        expected_clean = expected.replace("src/", "").replace("src\\", "")
        for path in top_k_paths:
            if expected_clean in path or expected in path:
                hits += 1
                break

    precision_at_k = hits / len(query_spec.expected_in_top_k) if query_spec.expected_in_top_k else 0.0
    hit_rate = hits / query_spec.k if query_spec.k > 0 else 0.0

    # Simple NDCG calculation
    ndcg = calculate_ndcg(top_k_paths, query_spec.expected_in_top_k, query_spec.k)

    return BenchmarkResult(
        query=f"[{query_spec.scenario_id}] {query_spec.query}",
        version=version,
        latency_ms=latency_ms,
        top_k_results=top_k,
        precision_at_k=precision_at_k,
        hit_rate=hit_rate,
        ndcg=ndcg,
    )


async def run_comprehensive_benchmark(src_dir: Path):
    """Run comprehensive benchmark across all 41 scenarios."""
    logger.info("=" * 80)
    logger.info("Comprehensive Retriever Benchmark - All 41 Scenarios")
    logger.info("=" * 80)
    logger.info(f"Source directory: {src_dir}")
    logger.info(f"Total scenarios: {len(COMPREHENSIVE_QUERIES)}")
    logger.info("")

    # Initialize indexes
    logger.info("Initializing indexes...")
    lexical_idx = MockLexicalIndex(src_dir)
    vector_idx = MockVectorIndex(src_dir)
    symbol_idx = MockSymbolIndex(src_dir)
    logger.info(f"Indexed {len(lexical_idx.files)} Python files")
    logger.info("")

    # Initialize fusion implementations
    versions = {
        "v2 (Weighted RRF)": FusionV2(rrf_k=60),  # Only test v2 (winner)
    }

    # Run benchmarks
    all_results = []

    # Group by priority
    priority1_queries = [q for q in COMPREHENSIVE_QUERIES if q.scenario_id.startswith("1-")]
    priority2_queries = [q for q in COMPREHENSIVE_QUERIES if q.scenario_id.startswith("2-") and q.scenario_id != "2-21"]
    priority3_queries = [q for q in COMPREHENSIVE_QUERIES if q.scenario_id == "2-21"]

    logger.info(f"━━━ Priority 1: Engine Essentials ({len(priority1_queries)} scenarios) ━━━")
    logger.info("")

    for query_spec in priority1_queries:
        logger.info(f"[{query_spec.scenario_id}] {query_spec.scenario_name}")
        logger.info(f"  Query: \"{query_spec.query}\"")
        logger.info(f"  Intent: {query_spec.intent}, K={query_spec.k}")
        logger.info(f"  Required axes: {', '.join(query_spec.required_axes)}")

        for version_name, fusion_impl in versions.items():
            result = await run_single_scenario_benchmark(
                query_spec=query_spec,
                fusion_impl=fusion_impl,
                lexical_idx=lexical_idx,
                vector_idx=vector_idx,
                symbol_idx=symbol_idx,
                version=version_name,
            )
            all_results.append((query_spec.scenario_id, result))

            logger.info(
                f"  {version_name}: "
                f"P@{query_spec.k}={result.precision_at_k:.2f}, "
                f"NDCG={result.ndcg:.3f}, "
                f"latency={result.latency_ms:.1f}ms"
            )

        logger.info("")

    logger.info("")
    logger.info(f"━━━ Priority 2: Production Essentials ({len(priority2_queries)} scenarios) ━━━")
    logger.info("")

    for query_spec in priority2_queries:
        logger.info(f"[{query_spec.scenario_id}] {query_spec.scenario_name}")
        logger.info(f"  Query: \"{query_spec.query}\"")

        for version_name, fusion_impl in versions.items():
            result = await run_single_scenario_benchmark(
                query_spec=query_spec,
                fusion_impl=fusion_impl,
                lexical_idx=lexical_idx,
                vector_idx=vector_idx,
                symbol_idx=symbol_idx,
                version=version_name,
            )
            all_results.append((query_spec.scenario_id, result))

            logger.info(
                f"  {version_name}: "
                f"P@{query_spec.k}={result.precision_at_k:.2f}, "
                f"NDCG={result.ndcg:.3f}"
            )

        logger.info("")

    logger.info("")
    logger.info(f"━━━ Priority 3: RepoMap ({len(priority3_queries)} scenario) ━━━")
    logger.info("")

    for query_spec in priority3_queries:
        logger.info(f"[{query_spec.scenario_id}] {query_spec.scenario_name}")
        logger.info(f"  Query: \"{query_spec.query}\"")

        for version_name, fusion_impl in versions.items():
            result = await run_single_scenario_benchmark(
                query_spec=query_spec,
                fusion_impl=fusion_impl,
                lexical_idx=lexical_idx,
                vector_idx=vector_idx,
                symbol_idx=symbol_idx,
                version=version_name,
            )
            all_results.append((query_spec.scenario_id, result))

            logger.info(
                f"  {version_name}: "
                f"P@{query_spec.k}={result.precision_at_k:.2f}, "
                f"NDCG={result.ndcg:.3f}"
            )

        logger.info("")

    # Aggregate results by category
    logger.info("=" * 80)
    logger.info("Aggregate Results by Category")
    logger.info("=" * 80)

    categories = {
        "A. Symbol/Definition": ["1-1", "1-2", "1-3", "1-4", "1-5"],
        "B. Call Relationships": ["1-6", "1-7", "1-8"],
        "C. Pipeline/E2E": ["1-9", "1-10", "1-11", "1-12"],
        "D. API/DTO": ["1-13", "1-14", "1-15"],
        "E. Config/Environment": ["1-16", "1-17", "1-18", "1-19", "1-20"],
        "F. Refactoring/Quality": ["2-1", "2-2", "2-3", "2-4", "2-5", "2-6"],
        "G. Parsing/Caching/Events": ["2-7", "2-8", "2-9", "2-10", "2-11"],
        "H. CLI/gRPC/Versioning": ["2-12", "2-13", "2-14"],
        "I. Security/Debugging": ["2-15", "2-16", "2-17", "2-18", "2-19", "2-20"],
        "J. RepoMap": ["2-21"],
    }

    for category_name, scenario_ids in categories.items():
        category_results = [r for sid, r in all_results if sid in scenario_ids]

        if not category_results:
            continue

        avg_precision = sum(r.precision_at_k for r in category_results) / len(category_results)
        avg_ndcg = sum(r.ndcg for r in category_results) / len(category_results)
        avg_latency = sum(r.latency_ms for r in category_results) / len(category_results)

        logger.info(f"{category_name} ({len(category_results)} scenarios):")
        logger.info(f"  Avg Precision: {avg_precision:.3f}")
        logger.info(f"  Avg NDCG: {avg_ndcg:.3f}")
        logger.info(f"  Avg Latency: {avg_latency:.1f}ms")
        logger.info("")

    # Overall aggregate
    logger.info("=" * 80)
    logger.info("Overall Results")
    logger.info("=" * 80)

    all_result_objs = [r for _, r in all_results]
    overall_precision = sum(r.precision_at_k for r in all_result_objs) / len(all_result_objs)
    overall_ndcg = sum(r.ndcg for r in all_result_objs) / len(all_result_objs)
    overall_latency = sum(r.latency_ms for r in all_result_objs) / len(all_result_objs)

    logger.info(f"Total Scenarios: {len(COMPREHENSIVE_QUERIES)}")
    logger.info(f"Overall Avg Precision: {overall_precision:.3f}")
    logger.info(f"Overall Avg NDCG: {overall_ndcg:.3f}")
    logger.info(f"Overall Avg Latency: {overall_latency:.1f}ms")
    logger.info("")

    # Coverage analysis
    logger.info("=" * 80)
    logger.info("Scenario Coverage Analysis")
    logger.info("=" * 80)

    successful_scenarios = [sid for sid, r in all_results if r.precision_at_k > 0.0]
    failed_scenarios = [sid for sid, r in all_results if r.precision_at_k == 0.0]

    logger.info(f"✅ Successful: {len(successful_scenarios)}/{len(COMPREHENSIVE_QUERIES)} scenarios")
    logger.info(f"❌ Failed: {len(failed_scenarios)}/{len(COMPREHENSIVE_QUERIES)} scenarios")
    logger.info("")

    if failed_scenarios:
        logger.info("Failed scenarios (need improvement):")
        for sid in failed_scenarios[:10]:  # Show first 10
            query = next(q for q in COMPREHENSIVE_QUERIES if q.scenario_id == sid)
            logger.info(f"  [{sid}] {query.scenario_name}")

    logger.info("")
    logger.info("=" * 80)
    logger.info("Comprehensive Benchmark Complete")
    logger.info("=" * 80)


# ============================================================
# Main Entry Point
# ============================================================


def main():
    """Main entry point."""
    # Get src directory
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"

    if not src_dir.exists():
        logger.error(f"Source directory not found: {src_dir}")
        return

    # Run comprehensive benchmark
    asyncio.run(run_comprehensive_benchmark(src_dir))


if __name__ == "__main__":
    main()
