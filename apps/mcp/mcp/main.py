#!/usr/bin/env python3
"""MCP 서버 엔트리포인트"""

import asyncio
import os

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool

from apps.mcp.mcp.adapters.mcp.services import MCPSearchService
from apps.mcp.mcp.adapters.search.chunk_retriever import create_chunk_retriever
from apps.mcp.mcp.adapters.search.symbol_retriever import create_symbol_retriever
from apps.mcp.mcp.adapters.store.factory import create_all_stores

# RFC-052/053: Use new handlers from apps.mcp.mcp.handlers
from apps.mcp.mcp.handlers import (
    analyze_cost,
    analyze_race,
    force_reindex,  # Admin tool (Tier 2)
    get_context,
    get_definition,
    get_references,
    job_cancel,
    job_result,
    job_status,
    job_submit,
    preview_callers,
    preview_impact,
    preview_taint_path,
    search,  # RFC-053 Tier 0
    verify_finding_resolved,
    verify_patch_compile,
)
from apps.orchestrator.orchestrator.adapters.context_adapter import ContextAdapter
from codegraph_shared.infra.config.logging import setup_logging

setup_logging()

# ============================================================
# 환경 설정: 분석할 레포지토리 경로
# ============================================================

# 환경변수로 지정하거나, 현재 작업 디렉토리 사용
TARGET_REPO_PATH = os.getenv(
    "CODEGRAPH_REPO_PATH",
    os.getcwd(),  # 기본값: MCP 서버를 실행한 디렉토리
)

# File watching 활성화 여부
ENABLE_FILE_WATCHING = os.getenv("CODEGRAPH_WATCH", "true").lower() in ("true", "1", "yes")

# Log configuration (not print - would pollute MCP stdout)
import logging

_logger = logging.getLogger(__name__)
_logger.info(f"Target Repository: {TARGET_REPO_PATH}")
_logger.info(f"File Watching: {'Enabled' if ENABLE_FILE_WATCHING else 'Disabled'}")

# ============================================================
# 자동 인덱싱 체크 (첫 요청 시)
# ============================================================

from enum import Enum
from typing import Any


class IndexCheckResult(Enum):
    """
    인덱스 상태 체크 결과 (내부 로직용 ENUM).

    Values:
        COMPLETED: 인덱싱 완료 (캐시 사용)
        IN_PROGRESS: 인덱싱 진행 중 (스킵)
        NOT_FOUND: 인덱스 없음 (인덱싱 필요)
        ERROR: 체크 실패
    """

    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    NOT_FOUND = "not_found"
    ERROR = "error"


class IndexStatusLoader:
    """
    L3 Database Loader for Index Status (Protocol 구현).

    Big Tech L11: Protocol-based design with STALE detection.

    Features:
    - STALE 감지: IN_PROGRESS가 오래되면 NOT_FOUND 처리
    - Timestamp 기반 판단
    - Graceful degradation
    """

    def __init__(self, indexing_timeout: int = 1800):
        """
        Initialize loader.

        Args:
            indexing_timeout: 인덱싱 타임아웃 (초, STALE 감지용)
        """
        self._version_store = None
        self._indexing_timeout = indexing_timeout

    async def load(self, key: str) -> IndexCheckResult | None:
        """
        DB에서 인덱스 상태 로드 (L3 tier).

        Big Tech L11: STALE detection for hanging IN_PROGRESS.

        Args:
            key: repo_id (e.g., "default")

        Returns:
            IndexCheckResult or None

        Logic:
            1. DB에서 latest version 조회
            2. COMPLETED → COMPLETED
            3. IN_PROGRESS:
               - created_at이 indexing_timeout 이내 → IN_PROGRESS
               - created_at이 indexing_timeout 초과 → STALE (None 반환)
            4. 기타 → None
        """
        try:
            from datetime import datetime

            from codegraph_shared.common.observability import get_logger

            logger = get_logger(__name__)

            # Lazy init version_store
            if not self._version_store:
                from codegraph_engine.multi_index.infrastructure.version.store import IndexVersionStore
                from codegraph_shared.infra.storage.postgres import PostgresStore

                postgres = PostgresStore()
                self._version_store = IndexVersionStore(postgres_store=postgres)

            # Get latest version
            latest = await self._version_store.get_latest_version(repo_id=key)

            if not latest:
                return None  # Not found

            # Check status
            from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

            if latest.status == IndexVersionStatus.COMPLETED:
                logger.debug(f"L3 hit: Index v{latest.version_id} ({latest.file_count} files)")
                return IndexCheckResult.COMPLETED

            elif latest.status == IndexVersionStatus.INDEXING:
                # STALE 감지: IN_PROGRESS가 오래되었는지 확인
                if hasattr(latest, "created_at") and latest.created_at:
                    now = datetime.now()
                    # created_at이 datetime이면 직접 비교
                    if isinstance(latest.created_at, datetime):
                        elapsed = (now - latest.created_at).total_seconds()
                    else:
                        # timestamp라면 변환
                        elapsed = (now - datetime.fromtimestamp(latest.created_at)).total_seconds()

                    if elapsed > self._indexing_timeout:
                        logger.warning(
                            f"IN_PROGRESS is STALE (elapsed: {elapsed:.0f}s > {self._indexing_timeout}s), "
                            f"treating as NOT_FOUND"
                        )
                        return None  # STALE → NOT_FOUND

                # Still valid IN_PROGRESS
                return IndexCheckResult.IN_PROGRESS

            else:
                # FAILED or unexpected → NOT_FOUND
                return None

        except Exception as e:
            from codegraph_shared.common.observability import get_logger

            logger = get_logger(__name__)
            logger.debug(f"L3 load failed: {e}")
            return None  # Graceful degradation

    async def save(self, key: str, value: IndexCheckResult) -> None:
        """저장 (read-only이므로 no-op)."""
        pass

    async def delete(self, key: str) -> None:
        """삭제 (read-only이므로 no-op)."""
        pass


# ============================================================
# 3-Tier Cache for Index Status (Big Tech L11)
# ============================================================

_index_status_cache: Any = None  # ThreeTierCache[IndexCheckResult]
_indexing_done = False
_indexing_in_progress = False


async def _invalidate_index_cache(repo_id: str) -> None:
    """
    Invalidate index status cache for repo.

    Big Tech L11: Cache invalidation for force_reindex.

    Args:
        repo_id: Repository ID to invalidate

    Side Effects:
        - L1 (메모리) 삭제
        - L2 (Redis) 삭제
        - L3 (DB)는 건드리지 않음 (source of truth)
        - _indexing_done 플래그 리셋
    """
    global _indexing_done

    cache = _get_index_cache()

    if cache:
        try:
            await cache.delete(repo_id)
            from codegraph_shared.common.observability import get_logger

            logger = get_logger(__name__)
            logger.info(f"Index cache invalidated for {repo_id}")
        except Exception as e:
            from codegraph_shared.common.observability import get_logger

            logger = get_logger(__name__)
            logger.warning(f"Cache invalidation failed: {e}")

    # Reset flag to allow re-check
    _indexing_done = False


def _get_index_cache() -> Any:
    """
    Get or create index status cache.

    Big Tech L11: Config-driven TTL + STALE detection.

    Returns:
        ThreeTierCache instance or None
    """
    global _index_status_cache

    if _index_status_cache is not None:
        return _index_status_cache

    try:
        from apps.mcp.mcp.config import get_index_status_cache_config
        from codegraph_shared.infra.cache.three_tier_cache import ThreeTierCache

        cache_config = get_index_status_cache_config()

        # L1: Always available (in-memory LRU)
        # L2: Redis (if available)
        # L3: DB (IndexVersionStore with STALE detection)

        l2_redis = None
        # Try to init Redis (graceful degradation)
        try:
            from codegraph_shared.infra.cache.redis_adapter import RedisAdapter

            l2_redis = RedisAdapter()
        except Exception:
            pass  # Redis unavailable, L2 disabled

        # L3 loader with STALE detection
        l3_loader = IndexStatusLoader(indexing_timeout=cache_config.indexing_timeout)

        _index_status_cache = ThreeTierCache(
            l1_maxsize=cache_config.l1_maxsize,
            l2_redis=l2_redis,
            l3_loader=l3_loader,
            ttl=cache_config.ttl_in_progress,  # Use shortest TTL (빠른 재체크)
            namespace="index_status",
        )

        return _index_status_cache

    except Exception as e:
        from codegraph_shared.common.observability import get_logger

        logger = get_logger(__name__)
        logger.warning(f"Failed to create index cache: {e}")
        return None


async def check_index_status(repo_path: str, repo_id: str = "default") -> IndexCheckResult:
    """
    인덱스 상태 확인 (Big Tech L11: 3-Tier Cache).

    Args:
        repo_path: Repository path
        repo_id: Repository ID

    Returns:
        IndexCheckResult enum

    Strategy (SOTA):
        1. L1 (메모리) 캐시 조회 (~0.1ms)
        2. L2 (Redis) 캐시 조회 (~1ms, 여러 프로세스 공유)
        3. L3 (DB) IndexVersionStore 조회 (~10ms)
        4. 캐시 워밍: L3 → L2 → L1

    Performance:
        - Cache hit: < 1ms (L1/L2)
        - Cache miss: ~10ms (L3)
        - TTL: 5min (자동 invalidation)
    """
    from codegraph_shared.common.observability import get_logger

    logger = get_logger(__name__)

    try:
        # Get 3-tier cache
        cache = _get_index_cache()

        if cache is None:
            # Fallback: direct DB query (no cache)
            logger.warning("Cache unavailable, using direct DB query")
            return await _check_index_status_direct(repo_id)

        # Cache lookup (L1 → L2 → L3)
        status = await cache.get(repo_id)

        if status is None:
            # All tiers miss → NOT_FOUND
            logger.info("Index not found (all cache tiers miss)")
            return IndexCheckResult.NOT_FOUND

        # Cache hit
        logger.debug(f"Index status: {status.value} (cache hit)")
        return status

    except Exception as e:
        logger.warning(f"Index status check failed: {e}")
        return IndexCheckResult.ERROR


async def _check_index_status_direct(repo_id: str) -> IndexCheckResult:
    """
    Direct DB query fallback (no cache).

    Args:
        repo_id: Repository ID

    Returns:
        IndexCheckResult enum
    """
    from codegraph_shared.common.observability import get_logger

    logger = get_logger(__name__)

    try:
        # Try to query IndexVersionStore
        from codegraph_engine.multi_index.infrastructure.version.store import IndexVersionStore
        from codegraph_shared.infra.storage.postgres import PostgresStore

        postgres = PostgresStore()
        version_store = IndexVersionStore(postgres_store=postgres)

        latest = await version_store.get_latest_version(repo_id=repo_id)

        if not latest:
            return IndexCheckResult.NOT_FOUND

        from codegraph_engine.multi_index.infrastructure.version.models import IndexVersionStatus

        if latest.status == IndexVersionStatus.COMPLETED:
            logger.info(f"Index exists (v{latest.version_id}, {latest.file_count} files, {latest.git_commit[:8]})")
            return IndexCheckResult.COMPLETED
        elif latest.status == IndexVersionStatus.INDEXING:
            return IndexCheckResult.IN_PROGRESS
        else:
            return IndexCheckResult.NOT_FOUND

    except Exception as e:
        logger.debug(f"Direct DB check failed: {e}")
        return IndexCheckResult.NOT_FOUND  # Graceful: assume not indexed


async def ensure_indexed(repo_id: str = "default"):
    """
    첫 요청 시 자동으로 레포지토리 인덱싱.

    Strategy (Big Tech L11: 3-Tier Cache):
    1. 3-tier 캐시로 인덱스 상태 확인 (L1 → L2 → L3)
       - L1 (메모리): ~0.1ms
       - L2 (Redis): ~1ms (여러 프로세스 공유)
       - L3 (DB): ~10ms (IndexVersionStore)
    2. COMPLETED → 캐시 hit (skip)
    3. IN_PROGRESS → 진행 중 (skip)
    4. NOT_FOUND → 인덱싱 알림
    5. _indexing_done 플래그로 첫 체크 후 skip
    """
    global _indexing_done, _indexing_in_progress

    if _indexing_done:
        return

    if _indexing_in_progress:
        return

    try:
        from codegraph_shared.common.observability import get_logger

        logger = get_logger(__name__)

        # Check index status (3-tier cache)
        status = await check_index_status(TARGET_REPO_PATH, repo_id=repo_id)

        if status == IndexCheckResult.COMPLETED:
            logger.info("✅ Index cache hit (L1/L2/L3)")
            _indexing_done = True
            return

        if status == IndexCheckResult.IN_PROGRESS:
            logger.info("⏳ Indexing in progress (skipping)")
            _indexing_done = True
            return

        if status == IndexCheckResult.ERROR:
            logger.warning("⚠️ Index check failed")
            logger.info("💡 To index: python -m src.cli.main index <repo_path>")
            _indexing_done = True
            return

        # NOT_FOUND → BALANCED 모드 백그라운드 인덱싱
        logger.info("🚀 Starting background indexing (BALANCED mode)")
        logger.info(f"📍 Repository: {TARGET_REPO_PATH}")

        _indexing_in_progress = True

        # Trigger background indexing (non-blocking)
        try:
            import asyncio

            asyncio.create_task(_trigger_background_indexing(repo_id, TARGET_REPO_PATH))

            logger.info("✅ Background indexing job created")
            logger.info("💡 L2 완료 후 검색 가능 (~30초), L3 완료 후 Semantic 분석 가능 (~2분)")

        except Exception as idx_err:
            logger.error(f"Failed to trigger indexing: {idx_err}")
            logger.info("💡 Fallback: python -m src.cli.main index <repo_path>")

        _indexing_done = True
        _indexing_in_progress = False

    except Exception as e:
        from codegraph_shared.common.observability import get_logger

        logger = get_logger(__name__)
        logger.error(f"⚠️ Indexing check failed: {e}")
        _indexing_done = True


async def _trigger_background_indexing(repo_id: str, repo_path: str) -> None:
    """
    백그라운드 인덱싱 실행 (Big Tech L11: BALANCED 모드).

    Args:
        repo_id: Repository ID
        repo_path: Repository path

    Strategy:
        1. BALANCED 모드 사용 (L1 + L2 + L3)
        2. JobOrchestrator로 비동기 실행
        3. 각 stage 완료 시 점진적 사용 가능:
           - L1 (파싱) 완료 → 심볼 발견
           - L2 (청크) 완료 → 검색 가능
           - L3 (Semantic IR) 완료 → 분석 가능

    Performance:
        - BALANCED: ~2분 / 10K files
        - L2까지: ~30초 (검색 가능)
        - L3까지: ~2분 (완전 분석)
    """
    from pathlib import Path

    from codegraph_shared.common.observability import get_logger

    logger = get_logger(__name__)

    try:
        logger.info(
            "Background indexing requested",
            repo_id=repo_id,
            repo_path=repo_path,
        )

        # For MCP: avoid heavy container initialization (tantivy dependency)
        # Container import loads entire system including tantivy, lexical indexes, etc.
        logger.info(f"📍 Repository: {repo_path}")
        logger.info("💡 To index: python -m src.cli.main index <repo_path>")
        logger.info("💡 BALANCED mode: L2 완료 후 검색 가능 (~30s), L3 완료 후 분석 가능 (~2min)")

        # TODO: Implement lightweight job submission without container
        # Current blocker: container import requires tantivy, full index system

    except Exception as e:
        logger.error(f"Background indexing setup failed: {e}", repo_id=repo_id)
        logger.info("💡 Manual: python -m src.cli.main index <repo_path>")


# 저장소 및 서비스 초기화
node_store, edge_store, vector_store = create_all_stores()
chunk_retriever = create_chunk_retriever(vector_store, edge_store)
symbol_retriever = create_symbol_retriever(vector_store, edge_store)

# MCP Search Service (chunks + symbols)
search_service = MCPSearchService(chunk_retriever, symbol_retriever, node_store)

# ContextAdapter for call graph and other context queries
# (replaces MCPGraphService - uses existing ContextAdapter)
context_adapter = ContextAdapter(
    retrieval_service=None,  # Not needed for call graph
    symbol_index=None,  # Not needed for call graph
)

# ============================================================
# File Watcher 설정 (실시간 증분 인덱싱)
# 기존 FileWatcherService + IndexJobOrchestrator 활용
# ============================================================

_file_watcher_service = None
_indexing_container = None

if ENABLE_FILE_WATCHING:
    # File watcher disabled for MCP to avoid heavy container initialization
    _logger.info("File watcher disabled (MCP lightweight mode)")
    _logger.info("   → Use CLI for indexing: python -m src.cli.main index")

# MCP 서버 생성
server = Server("codegraph")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """도구 목록 반환"""
    return [
        # ============================================================
        # RFC-053 Tier 0 — 에이전트 기본 진입점 (3개)
        # ============================================================
        Tool(
            name="search",
            description="하이브리드 검색 (chunks + symbols 통합) - 어디를 볼지 모를 때 첫 선택 [Tier 0]",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "types": {
                        "type": "array",
                        "items": {"enum": ["chunks", "symbols", "all"]},
                        "default": ["all"],
                        "description": "검색 대상 타입",
                    },
                    "limit": {"type": "integer", "default": 10, "description": "최대 결과 수"},
                    "repo_id": {"type": "string", "default": "default"},
                    "snapshot_id": {"type": "string", "default": "main"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_chunks",
            description="코드 청크 검색 [Legacy - use 'search' instead]",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "limit": {"type": "integer", "description": "결과 수", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="search_symbols",
            description="심볼 검색 [Legacy - use 'search' instead]",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "검색 쿼리"},
                    "limit": {"type": "integer", "description": "결과 수", "default": 10},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_chunk",
            description="청크 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string", "description": "청크 ID"},
                },
                "required": ["chunk_id"],
            },
        ),
        Tool(
            name="get_symbol",
            description="심볼 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "심볼 ID"},
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name="get_callers",
            description="호출자 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "심볼 ID"},
                    "depth": {"type": "integer", "description": "탐색 깊이", "default": 1},
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name="get_callees",
            description="호출 대상 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol_id": {"type": "string", "description": "심볼 ID"},
                    "depth": {"type": "integer", "description": "탐색 깊이", "default": 1},
                },
                "required": ["symbol_id"],
            },
        ),
        Tool(
            name="analyze_cost",
            description="비용 복잡도 분석 (RFC-028)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string", "description": "저장소 ID"},
                    "snapshot_id": {"type": "string", "description": "스냅샷 ID"},
                    "functions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "분석할 함수 FQN 목록",
                    },
                },
                "required": ["repo_id", "snapshot_id", "functions"],
            },
        ),
        Tool(
            name="analyze_race",
            description="Race condition 분석 (RFC-028 Phase 2)",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_id": {"type": "string", "description": "저장소 ID"},
                    "snapshot_id": {"type": "string", "description": "스냅샷 ID"},
                    "functions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "분석할 async 함수 FQN 목록",
                    },
                },
                "required": ["repo_id", "snapshot_id", "functions"],
            },
        ),
        # ============================================================
        # Job Tools (Async)
        # ============================================================
        Tool(
            name="job_submit",
            description="비동기 Job 제출 (Heavy 분석용)",
            inputSchema={
                "type": "object",
                "properties": {
                    "tool": {"type": "string", "description": "실행할 도구 (analyze_taint, analyze_impact, etc.)"},
                    "args": {"type": "object", "description": "도구 인자"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "default": "medium"},
                    "timeout_seconds": {"type": "integer", "default": 300},
                },
                "required": ["tool"],
            },
        ),
        Tool(
            name="job_status",
            description="Job 상태 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID"},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="job_result",
            description="Job 결과 조회 (with pagination)",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID"},
                    "cursor": {"type": "string", "description": "페이지네이션 커서"},
                },
                "required": ["job_id"],
            },
        ),
        Tool(
            name="job_cancel",
            description="Job 취소",
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "Job ID"},
                },
                "required": ["job_id"],
            },
        ),
        # ============================================================
        # Admin Tools (Tier 2 - Requires Approval)
        # ============================================================
        Tool(
            name="force_reindex",
            description="강제 재인덱싱 - 기존 인덱스 무효화 후 전체 재인덱싱 (BALANCED 모드, 각 stage별 점진적 사용 가능) [Tier 2 - Requires Approval]",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_id": {
                        "type": "string",
                        "default": "default",
                        "description": "Repository ID",
                    },
                    "reason": {
                        "type": "string",
                        "description": "재인덱싱 이유 (logging용)",
                    },
                    "invalidate_cache": {
                        "type": "boolean",
                        "default": True,
                        "description": "캐시 무효화 여부",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["fast", "balanced", "deep"],
                        "default": "balanced",
                        "description": "인덱싱 모드 (fast=5s, balanced=2min, deep=30min)",
                    },
                },
                "required": [],
            },
        ),
        # ============================================================
        # Graph Semantics Tools (RFC-052 SOTA)
        # ============================================================
        Tool(
            name="graph_slice",
            description="Semantic Slicing - 버그/이슈의 Root Cause만 최소 단위로 추출 [Tier 0]",
            inputSchema={
                "type": "object",
                "properties": {
                    "anchor": {"type": "string", "description": "앵커 심볼 (변수/함수/클래스)"},
                    "direction": {
                        "type": "string",
                        "enum": ["backward", "forward", "both"],
                        "default": "backward",
                        "description": "슬라이스 방향",
                    },
                    "max_depth": {"type": "integer", "default": 5, "description": "최대 탐색 깊이"},
                    "max_lines": {"type": "integer", "default": 100, "description": "최대 라인 수"},
                    "session_id": {"type": "string", "description": "세션 ID (optional)"},
                    "repo_id": {"type": "string", "default": "default", "description": "리포지토리 ID"},
                    "file_scope": {"type": "string", "description": "파일 제한 (optional)"},
                },
                "required": ["anchor"],
            },
        ),
        Tool(
            name="graph_dataflow",
            description="Dataflow Analysis - source → sink 도달 가능성 증명 (RFC-052)",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "소스 심볼"},
                    "sink": {"type": "string", "description": "싱크 심볼"},
                    "policy": {"type": "string", "description": "정책 (sql_injection, xss 등)"},
                    "file_path": {"type": "string", "description": "분석할 파일 (optional)"},
                    "max_depth": {"type": "integer", "default": 10},
                    "session_id": {"type": "string"},
                    "repo_id": {"type": "string", "default": "default"},
                },
                "required": ["source", "sink"],
            },
        ),
        # ============================================================
        # Context Tools
        # ============================================================
        Tool(
            name="get_context",
            description="통합 컨텍스트 조회 (definition, usages, callers 등) [Tier 0]",
            inputSchema={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "symbol_id | fqn | file:line"},
                    "facets": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "definition",
                                "usages",
                                "references",
                                "docstring",
                                "skeleton",
                                "tests",
                                "callers",
                                "callees",
                            ],
                        },
                        "default": ["definition", "usages"],
                    },
                    "budget": {
                        "type": "object",
                        "properties": {
                            "max_chars": {"type": "integer", "default": 8000},
                            "max_items": {"type": "integer", "default": 20},
                        },
                    },
                },
                "required": ["target"],
            },
        ),
        Tool(
            name="get_definition",
            description="심볼 정의 조회",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "심볼 이름 또는 FQN"},
                    "repo_id": {"type": "string"},
                    "snapshot_id": {"type": "string", "default": "main"},
                    "include_body": {"type": "boolean", "default": True},
                },
                "required": ["symbol"],
            },
        ),
        Tool(
            name="get_references",
            description="참조 조회 (with pagination)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "심볼 이름 또는 FQN"},
                    "repo_id": {"type": "string"},
                    "snapshot_id": {"type": "string", "default": "main"},
                    "limit": {"type": "integer", "default": 50},
                    "cursor": {"type": "string"},
                },
                "required": ["symbol"],
            },
        ),
        # ============================================================
        # Preview Tools (Lightweight)
        # ============================================================
        Tool(
            name="preview_taint_path",
            description="Taint 경로 프리뷰 (1-2초, 존재성 확인)",
            inputSchema={
                "type": "object",
                "properties": {
                    "source_pattern": {"type": "string", "description": "Source 패턴"},
                    "sink_pattern": {"type": "string", "description": "Sink 패턴"},
                    "repo_id": {"type": "string"},
                    "snapshot_id": {"type": "string", "default": "main"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["source_pattern", "sink_pattern"],
            },
        ),
        Tool(
            name="preview_impact",
            description="Impact 프리뷰 (변경 영향도 근사)",
            inputSchema={
                "type": "object",
                "properties": {
                    "changed_symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "변경된 심볼 FQN 목록",
                    },
                    "repo_id": {"type": "string"},
                    "snapshot_id": {"type": "string", "default": "main"},
                    "top_k": {"type": "integer", "default": 20},
                },
                "required": ["changed_symbols"],
            },
        ),
        Tool(
            name="preview_callers",
            description="호출자 프리뷰 (상위 호출자만)",
            inputSchema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "심볼 FQN"},
                    "depth": {"type": "integer", "default": 2},
                    "top_k": {"type": "integer", "default": 50},
                    "repo_id": {"type": "string"},
                    "snapshot_id": {"type": "string", "default": "main"},
                },
                "required": ["symbol"],
            },
        ),
        # ============================================================
        # Verify Tools
        # ============================================================
        Tool(
            name="verify_patch_compile",
            description="패치 문법/타입/빌드 검증",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "수정된 파일 경로"},
                    "patch": {"type": "string", "description": "적용할 패치 또는 새 내용"},
                    "language": {"type": "string", "enum": ["python", "typescript", "javascript"], "default": "python"},
                    "check_types": {"type": "boolean", "default": True},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="verify_finding_resolved",
            description="Finding 해결 확인 (분석→수정→검증 루프)",
            inputSchema={
                "type": "object",
                "properties": {
                    "finding_id": {"type": "string", "description": "원래 finding ID"},
                    "finding_type": {"type": "string", "description": "Finding 유형 (taint, null_deref, etc.)"},
                    "original_location": {
                        "type": "object",
                        "properties": {
                            "file": {"type": "string"},
                            "line": {"type": "integer"},
                            "column": {"type": "integer"},
                        },
                        "required": ["file", "line"],
                    },
                    "patch": {"type": "string", "description": "적용된 패치"},
                    "repo_id": {"type": "string"},
                    "snapshot_id": {"type": "string", "default": "main"},
                },
                "required": ["finding_type", "original_location"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list:
    """
    도구 호출.

    Big Tech L11: 첫 요청 시 자동 인덱스 체크 (캐시 활용).
    """
    import json
    from mcp.types import TextContent

    # 첫 요청 시 자동 인덱스 체크
    await ensure_indexed()

    # RFC-053 Tier 0
    if name == "search":
        result = await search(search_service, arguments)
        return [TextContent(type="text", text=result)]
    # RFC-052: Graph Semantics Tools
    elif name == "graph_slice":
        result = await graph_slice(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "graph_dataflow":
        result = await graph_dataflow(arguments)
        return [TextContent(type="text", text=result)]
    # Legacy tools (backward compatibility via service layer)
    elif name == "search_chunks":
        # Redirect to search with types=["chunks"]
        arguments["types"] = ["chunks"]
        result = await search(search_service, arguments)
        return [TextContent(type="text", text=result)]
    elif name == "search_symbols":
        # Redirect to search with types=["symbols"]
        arguments["types"] = ["symbols"]
        result = await search(search_service, arguments)
        return [TextContent(type="text", text=result)]
    elif name == "get_chunk":
        # Direct service call
        chunk_id = arguments.get("chunk_id", "")
        chunk_result = await search_service.get_chunk(chunk_id)
        result = json.dumps(chunk_result.to_dict() if chunk_result else {"error": "Not found"})
        return [TextContent(type="text", text=result)]
    elif name == "get_symbol":
        # Direct service call
        symbol_id = arguments.get("symbol_id", "")
        symbol_result = await search_service.get_symbol(symbol_id)
        result = json.dumps(symbol_result.to_dict() if symbol_result else {"error": "Not found"})
        return [TextContent(type="text", text=result)]
    elif name == "get_callers":
        # Use ContextAdapter.get_call_graph
        symbol = arguments.get("symbol_id", "")
        depth = arguments.get("depth", 1)
        repo_id = arguments.get("repo_id", "default")
        snapshot_id = arguments.get("snapshot_id", "main")

        graph_result = await context_adapter.get_call_graph(
            function_name=symbol,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            depth=depth,
        )
        # Extract only callers
        callers = graph_result.get("callers", [])
        result = json.dumps(callers)
        return [TextContent(type="text", text=result)]
    elif name == "get_callees":
        # Use ContextAdapter.get_call_graph
        symbol = arguments.get("symbol_id", "")
        depth = arguments.get("depth", 1)
        repo_id = arguments.get("repo_id", "default")
        snapshot_id = arguments.get("snapshot_id", "main")

        graph_result = await context_adapter.get_call_graph(
            function_name=symbol,
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            depth=depth,
        )
        # Extract only callees
        callees = graph_result.get("callees", [])
        result = json.dumps(callees)
        return [TextContent(type="text", text=result)]
    # Analysis tools
    elif name == "analyze_cost":
        result = await analyze_cost(None, arguments)
        return [TextContent(type="text", text=result)]
    elif name == "analyze_race":
        result = await analyze_race(None, arguments)
        return [TextContent(type="text", text=result)]
    # Job tools (Async)
    elif name == "job_submit":
        result = await job_submit(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "job_status":
        result = await job_status(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "job_result":
        result = await job_result(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "job_cancel":
        result = await job_cancel(arguments)
        return [TextContent(type="text", text=result)]
    # Admin tools (Tier 2)
    elif name == "force_reindex":
        result = await force_reindex(arguments)
        return [TextContent(type="text", text=result)]
    # Context tools
    elif name == "get_context":
        result = await get_context(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "get_definition":
        result = await get_definition(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "get_references":
        result = await get_references(arguments)
        return [TextContent(type="text", text=result)]
    # Preview tools
    elif name == "preview_taint_path":
        result = await preview_taint_path(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "preview_impact":
        result = await preview_impact(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "preview_callers":
        result = await preview_callers(arguments)
        return [TextContent(type="text", text=result)]
    # Verify tools
    elif name == "verify_patch_compile":
        result = await verify_patch_compile(arguments)
        return [TextContent(type="text", text=result)]
    elif name == "verify_finding_resolved":
        result = await verify_finding_resolved(arguments)
        return [TextContent(type="text", text=result)]
    else:
        raise ValueError(f"Unknown tool: {name}")


# ============================================================
# MCP Resources (RFC-SEM-022 SOTA)
# ============================================================


@server.list_resources()
async def list_resources():
    """
    MCP Resources 목록 (RFC-SEM-022).

    Streaming Resources:
    - semantica://jobs/{job_id}/events
    - semantica://jobs/{job_id}/log
    - semantica://jobs/{job_id}/artifacts
    - semantica://executions/{execution_id}/findings
    - semantica://repo/{repo_id}/info
    """
    from mcp.types import Resource

    return [
        Resource(
            uri="semantica://repo/info",
            name="Repository Info",
            description=f"현재 분석 중인 레포지토리 정보 (Path: {TARGET_REPO_PATH})",
            mimeType="application/json",
        ),
        Resource(
            uri="semantica://jobs/{job_id}/events",
            name="Job Events Stream",
            description="실시간 Job 이벤트 스트림 (SSE)",
            mimeType="text/event-stream",
        ),
        Resource(
            uri="semantica://jobs/{job_id}/log",
            name="Job Log Stream",
            description="실시간 Job 로그",
            mimeType="text/plain",
        ),
        Resource(
            uri="semantica://jobs/{job_id}/artifacts",
            name="Job Artifacts",
            description="Job 실행 결과물",
            mimeType="application/json",
        ),
        Resource(
            uri="semantica://executions/{execution_id}/findings",
            name="Execution Findings",
            description="실행에서 발견된 취약점 목록",
            mimeType="application/json",
        ),
    ]


@server.list_prompts()
async def list_prompts():
    """
    MCP Prompts 목록 (RFC-SEM-022 SOTA).

    LLM Agent 자기비판 및 추론 가이드.
    """
    from apps.mcp.mcp.prompts import get_prompts

    return get_prompts()


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None):
    """
    Prompt 조회 및 템플릿 생성.

    Args:
        name: Prompt 이름
        arguments: Prompt 인자

    Returns:
        Prompt 텍스트 (구조화된 추론 가이드)
    """
    from apps.mcp.mcp.prompts import get_prompt_template

    if arguments is None:
        arguments = {}

    try:
        template = get_prompt_template(name, arguments)
        return {
            "description": f"Prompt: {name}",
            "messages": [{"role": "user", "content": {"type": "text", "text": template}}],
        }
    except Exception as e:
        raise ValueError(f"Failed to generate prompt: {e}")


@server.read_resource()
async def read_resource(uri: str) -> list:
    """
    MCP Resource 조회 (RFC-SEM-022).

    URI Format:
    - semantica://repo/info
    - semantica://jobs/{job_id}/events
    - semantica://jobs/{job_id}/log
    - semantica://jobs/{job_id}/artifacts
    - semantica://executions/{execution_id}/findings
    """
    import json
    import re
    from mcp.types import TextContent

    # Repo info
    if uri == "semantica://repo/info":
        result = json.dumps(
            {
                "uri": uri,
                "repo_path": TARGET_REPO_PATH,
                "repo_id": "default",
                "snapshot_id": "main",
                "indexed": False,  # TODO: Check actual index status
                "message": "Use CODEGRAPH_REPO_PATH env var to specify target repository",
            }
        )
        return [TextContent(type="text", text=result)]

    # Parse URI
    if match := re.match(r"semantica://jobs/([^/]+)/events", uri):
        job_id = match.group(1)
        # TODO: 실제 SSE 스트림 구현
        result = json.dumps(
            {
                "uri": uri,
                "job_id": job_id,
                "events": [],
                "message": "Streaming not yet implemented",
            }
        )
        return [TextContent(type="text", text=result)]

    elif match := re.match(r"semantica://jobs/([^/]+)/log", uri):
        job_id = match.group(1)
        result = json.dumps(
            {
                "uri": uri,
                "job_id": job_id,
                "log": [],
            }
        )
        return [TextContent(type="text", text=result)]

    elif match := re.match(r"semantica://jobs/([^/]+)/artifacts", uri):
        job_id = match.group(1)
        result = json.dumps(
            {
                "uri": uri,
                "job_id": job_id,
                "artifacts": {},
            }
        )
        return [TextContent(type="text", text=result)]

    elif match := re.match(r"semantica://executions/([^/]+)/findings", uri):
        execution_id = match.group(1)

        # ExecutionRepository에서 findings 조회
        try:
            from codegraph_shared.kernel.infrastructure.execution_repository import (
                get_execution_repository,
            )

            repo = get_execution_repository()
            findings = await repo.get_findings(execution_id)

            result = json.dumps(
                {
                    "uri": uri,
                    "execution_id": execution_id,
                    "findings": findings,
                    "count": len(findings),
                }
            )
            return [TextContent(type="text", text=result)]
        except Exception as e:
            result = json.dumps(
                {
                    "uri": uri,
                    "error": str(e),
                }
            )
            return [TextContent(type="text", text=result)]

    else:
        raise ValueError(f"Unknown resource URI: {uri}")


async def main():
    """메인 함수"""
    try:
        # Start file watcher (if enabled)
        if _file_watcher_service and ENABLE_FILE_WATCHING:
            await _file_watcher_service.start()

            # Watch target repository
            from pathlib import Path

            await _file_watcher_service.watch_repo(
                Path(TARGET_REPO_PATH),
                repo_id="default",
            )

            _logger.info(f"Watching repository: {TARGET_REPO_PATH}")

        # Run MCP server
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="codegraph",
                    server_version="0.1.0",
                    capabilities={
                        "tools": {},  # Enable tools support
                        "resources": {},  # Enable resources support
                    },
                ),
            )
    finally:
        # Cleanup: Stop file watcher
        if _file_watcher_service:
            await _file_watcher_service.stop()
            _logger.info("File watcher stopped")


if __name__ == "__main__":
    asyncio.run(main())
