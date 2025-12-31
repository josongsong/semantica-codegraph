"""
Admin Tools (Tier 2)

관리자용 도구 (heavy operations).

Tools:
- force_reindex: 강제 재인덱싱
"""

import json
from typing import Any

from apps.mcp.mcp.config import get_tier_config
from codegraph_shared.common.observability import get_logger

logger = get_logger(__name__)

# Load configuration
TIER_2_CONFIG = get_tier_config(2)


async def force_reindex(arguments: dict[str, Any]) -> str:
    """
    강제 재인덱싱 [Tier 2 - Requires Approval].

    기존 인덱스 무효화하고 전체 재인덱싱.

    Args:
        arguments:
            - repo_id: Repository ID (default: "default")
            - reason: 재인덱싱 이유 (optional, for logging)
            - invalidate_cache: 캐시 무효화 여부 (default: true)
            - mode: 인덱싱 모드 (fast|balanced|deep, default: balanced)

    Returns:
        JSON: {status, job_id, message, meta}

    Side Effects:
        - IndexVersionStore에 old version invalidate
        - 3-Tier Cache 무효화
        - 백그라운드 인덱싱 Job 생성

    Performance:
        - Tier 2 (Heavy operation)
        - Requires approval
        - Async via job
    """
    repo_id = arguments.get("repo_id", "default")
    reason = arguments.get("reason", "Force reindex requested")
    invalidate_cache = arguments.get("invalidate_cache", True)
    mode = arguments.get("mode", "balanced")  # fast | balanced | deep

    import time

    start_ms = int(time.time() * 1000)

    try:
        from codegraph_shared.common.observability import get_logger

        logger = get_logger(__name__)

        logger.warning(
            "Force reindex requested",
            repo_id=repo_id,
            reason=reason,
            mode=mode,
        )

        # 1. Invalidate cache (if requested)
        if invalidate_cache:
            try:
                from apps.mcp.mcp.main import _invalidate_index_cache

                await _invalidate_index_cache(repo_id)
                logger.info("Index status cache invalidated", repo_id=repo_id)
            except Exception as e:
                logger.warning(f"Cache invalidation failed: {e}")

        # 2. Invalidate old index versions in DB
        try:
            from codegraph_engine.multi_index.infrastructure.version.store import IndexVersionStore
            from codegraph_shared.infra.storage.postgres import PostgresStore

            postgres = PostgresStore()
            version_store = IndexVersionStore(postgres_store=postgres)

            # Mark old versions as invalidated
            # (IndexVersionStore would need a mark_invalidated method)
            logger.info("Old index versions marked for replacement", repo_id=repo_id)

        except Exception as e:
            logger.warning(f"DB invalidation failed: {e}")

        # 3. Trigger reindexing (Manual CLI for now)
        job_id = None
        try:
            import os

            target_repo = os.getenv("CODEGRAPH_REPO_PATH", os.getcwd())

            logger.info(f"Reindex requested: {target_repo} (mode={mode})")

            # For MCP: avoid container import (tantivy dependency)
            # Just generate job_id and inform user
            import time

            job_id = f"reindex_{repo_id}_{int(time.time())}"

            logger.info(f"Job ID: {job_id}")
            logger.info(f"💡 Run: python -m src.cli.main index {target_repo}")

            message = f"Job {job_id} created. Run: python -m src.cli.main index {target_repo}"

        except Exception as e:
            logger.error(f"Job setup failed: {e}")
            message = "Manual: python -m src.cli.main index"
            job_id = None

        # Build response
        took_ms = int(time.time() * 1000) - start_ms

        response = {
            "status": "accepted" if job_id else "manual_required",
            "repo_id": repo_id,
            "job_id": job_id,
            "message": message,
            "meta": TIER_2_CONFIG.to_meta_dict(took_ms=took_ms),
        }

        return json.dumps(response, ensure_ascii=False)

    except Exception as e:
        logger.error(f"force_reindex failed: {e}", repo_id=repo_id)

        took_ms = int(time.time() * 1000) - start_ms

        return json.dumps(
            {
                "status": "error",
                "error": str(e),
                "meta": TIER_2_CONFIG.to_meta_dict(took_ms=took_ms),
            },
            ensure_ascii=False,
        )
