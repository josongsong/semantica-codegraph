"""
Vector Index Handler (L4).

청크 결과를 사용하여 벡터 인덱싱 수행.
L2 (Chunk Build) 완료 후에만 실행 가능 - 청크 콘텐츠 필요.

Embedding Strategy (SOTA):
- Doc Index: Class, Module (docstrings만)
- Code Index: Function, Method (≥5줄)
"""

from typing import Any

from codegraph_shared.infra.jobs.handler import JobHandler, JobResult
from codegraph_shared.infra.jobs.handlers.config import (
    DEFAULT_CONFIG,
    ErrorCategory,
    ErrorCode,
    IndexingConfig,
)
from codegraph_shared.infra.observability.logging import get_logger

logger = get_logger(__name__)

# ============================================================
# Embedding Configuration (SOTA)
# ============================================================

# 임베딩 대상 청크 kind (PascalCase - Python NodeKind.value와 일치)
# 대소문자 무관하게 비교하도록 lowercase로 저장하고 비교 시 lower() 사용
EMBEDDABLE_CODE_KINDS = {"function", "method", "Function", "Method"}  # Code Index
EMBEDDABLE_DOC_KINDS = {"class", "module", "Class", "Module"}  # Doc Index (docstring만)

# 최소 라인 수 (너무 짧은 청크 제외)
MIN_LINES_FOR_CODE = 5
MIN_LINES_FOR_DOC = 1


def should_embed_chunk(chunk: Any) -> bool:
    """
    청크가 임베딩 대상인지 판단.

    권장 범위:
    - function (Function/Method): ≥5줄
    - class, module: docstring 있는 경우

    Supports both dict and Pydantic Chunk model.
    Note: Chunk model uses 'kind' field, not 'chunk_type'.
    """
    # Support both dict and object access
    if isinstance(chunk, dict):
        # Try both 'kind' and 'chunk_type' for compatibility
        chunk_kind = chunk.get("kind") or chunk.get("chunk_type", "")
        start_line = chunk.get("start_line") or 0
        end_line = chunk.get("end_line") or 0
        content = chunk.get("content", "")
    else:
        # Chunk model uses 'kind' field
        chunk_kind = getattr(chunk, "kind", None) or getattr(chunk, "chunk_type", "") or ""
        start_line = getattr(chunk, "start_line", 0) or 0
        end_line = getattr(chunk, "end_line", 0) or 0
        content = getattr(chunk, "content", "") or ""

    lines = end_line - start_line

    # Code Index: function (includes methods)
    if chunk_kind in EMBEDDABLE_CODE_KINDS:
        return lines >= MIN_LINES_FOR_CODE

    # Doc Index: class, module (docstring 있는 경우)
    if chunk_kind in EMBEDDABLE_DOC_KINDS:
        # docstring 존재 여부 확인
        has_docstring = '"""' in content or "'''" in content
        return has_docstring or lines >= MIN_LINES_FOR_DOC

    return False


def get_chunk_text_for_embedding(chunk: Any) -> str:
    """
    임베딩용 텍스트 추출.

    class/module은 docstring 우선, 나머지는 전체 content.
    content가 없으면 파일에서 직접 읽음.

    Supports both dict and Pydantic Chunk model.
    """
    from pathlib import Path

    # Support both dict and object access
    if isinstance(chunk, dict):
        chunk_kind = chunk.get("kind") or chunk.get("chunk_type", "")
        content = chunk.get("content", "")
        file_path = chunk.get("file_path", "")
        start_line = chunk.get("start_line") or 0
        end_line = chunk.get("end_line") or 0
    else:
        chunk_kind = getattr(chunk, "kind", None) or getattr(chunk, "chunk_type", "") or ""
        content = getattr(chunk, "content", "") or ""
        file_path = getattr(chunk, "file_path", "") or ""
        start_line = getattr(chunk, "start_line", 0) or 0
        end_line = getattr(chunk, "end_line", 0) or 0

    # Content 없으면 파일에서 읽기
    if not content and file_path and start_line and end_line:
        try:
            fp = Path(file_path)
            if fp.exists():
                lines = fp.read_text().splitlines()
                content = "\n".join(lines[start_line - 1 : end_line])
        except Exception:
            pass

    if chunk_kind in EMBEDDABLE_DOC_KINDS:
        # docstring만 추출 시도
        import re

        docstring_match = re.search(r'"""(.+?)"""|\'\'\'(.+?)\'\'\'', content, re.DOTALL)
        if docstring_match:
            return docstring_match.group(1) or docstring_match.group(2) or content

    return content


def get_chunk_attr(chunk: Any, attr: str, default: Any = None) -> Any:
    """Helper to get attribute from dict or object."""
    if isinstance(chunk, dict):
        return chunk.get(attr, default)
    return getattr(chunk, attr, default)


class VectorIndexHandler(JobHandler):
    """
    Vector Index Handler.

    Payload:
        {
            "repo_id": "repo-123",
            "snapshot_id": "main",
            "chunk_cache_key": "chunks:repo-123:main",  # L2에서 생성된 캐시 키
            "embedding_model": "text-embedding-3-small",
            "batch_size": 100,
        }

    Result:
        {
            "vectors_indexed": 500,
            "duration_seconds": 10.5,
        }

    Error Classification:
        - TRANSIENT: API rate limit, 일시적 네트워크 오류
        - PERMANENT: 청크 캐시 없음 (L2 실패), 잘못된 임베딩 모델
        - INFRASTRUCTURE: Qdrant 연결 실패, 메모리 부족
    """

    def __init__(
        self,
        chunk_cache: dict[str, Any] | None = None,
        config: IndexingConfig | None = None,
    ):
        """
        Args:
            chunk_cache: L2에서 생성된 청크 캐시 (ChunkBuildHandler와 공유)
            config: 인덱싱 설정 (기본: DEFAULT_CONFIG)
        """
        self.chunk_cache = chunk_cache if chunk_cache is not None else {}
        self.config = config or DEFAULT_CONFIG

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """벡터 인덱싱 실행."""
        repo_id = payload.get("repo_id")
        snapshot_id = payload.get("snapshot_id", self.config.defaults.snapshot_id)
        chunk_cache_key = payload.get("chunk_cache_key")
        embedding_model = payload.get("embedding_model", self.config.defaults.embedding_model)
        batch_size = payload.get("batch_size", self.config.batch.vector_batch_size)

        # Validation
        if not repo_id:
            return JobResult.fail(
                error="Missing required field: repo_id",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        if not chunk_cache_key:
            return JobResult.fail(
                error="Missing required field: chunk_cache_key",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        # Get chunks from cache or DB
        db_path = payload.get("db_path", self.config.defaults.db_path)
        use_db = payload.get("use_db", False)  # DB에서 직접 읽기 옵션

        chunks = []
        repo_path = payload.get("repo_path", "")

        if use_db and db_path:
            # DB에서 직접 청크 읽기 (Rust IR 호환성 문제 우회)
            try:
                import sqlite3
                from pathlib import Path

                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                # repo_id가 경로로 저장될 수 있어서 LIKE 사용
                cursor.execute("""
                    SELECT chunk_id, kind, fqn, file_path, start_line, end_line, content_hash
                    FROM chunks 
                    WHERE kind IN ('function', 'class', 'module')
                    AND is_deleted = 0
                    LIMIT 20000
                """)

                for row in cursor.fetchall():
                    chunk_id, kind, fqn, file_path, start_line, end_line, content_hash = row

                    # 파일에서 content 읽기
                    content = ""
                    if file_path and start_line and end_line:
                        try:
                            fp = Path(file_path)
                            if fp.exists():
                                lines = fp.read_text().splitlines()
                                content = "\n".join(lines[start_line - 1 : end_line])
                        except Exception:
                            pass

                    chunks.append(
                        {
                            "id": chunk_id,
                            "kind": kind,
                            "fqn": fqn,
                            "file_path": file_path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "content": content,
                            "content_hash": content_hash,
                        }
                    )
                conn.close()
                logger.info("chunks_loaded_from_db", repo_id=repo_id, chunks_count=len(chunks))
            except Exception as e:
                logger.warning("db_chunk_load_failed", error=str(e))

        if not chunks:
            # Fallback to cache
            chunk_data = self.chunk_cache.get(chunk_cache_key)
            if not chunk_data:
                return JobResult.fail(
                    error=f"Chunk cache not found: {chunk_cache_key}. L2 (Chunk Build) may have failed.",
                    data={"error_code": ErrorCode.CHUNK_CACHE_MISS, "error_category": ErrorCategory.PERMANENT},
                )
            chunks = chunk_data.get("chunks", [])

        if not chunks:
            return JobResult.ok(
                data={
                    "vectors_indexed": 0,
                    "duration_seconds": 0.0,
                    "warning": "No chunks to index",
                }
            )

        logger.info(
            "vector_index_started",
            repo_id=repo_id,
            chunks_count=len(chunks),
            embedding_model=embedding_model,
        )

        try:
            from datetime import datetime

            start_time = datetime.now()

            # 1. 청크 필터링 (권장 범위)
            embeddable_chunks = [c for c in chunks if should_embed_chunk(c)]
            filtered_count = len(chunks) - len(embeddable_chunks)

            logger.info(
                "vector_filtering_complete",
                repo_id=repo_id,
                total_chunks=len(chunks),
                embeddable_chunks=len(embeddable_chunks),
                filtered_out=filtered_count,
            )

            if not embeddable_chunks:
                return JobResult.ok(
                    data={
                        "vectors_indexed": 0,
                        "duration_seconds": 0.0,
                        "filtered_out": filtered_count,
                        "warning": "No embeddable chunks after filtering",
                    }
                )

            # 2. 임베딩용 텍스트 추출
            texts = [get_chunk_text_for_embedding(c) for c in embeddable_chunks]
            chunk_ids = [get_chunk_attr(c, "id", f"chunk_{i}") for i, c in enumerate(embeddable_chunks)]

            # 3. 실제 임베딩 생성 (OpenAI API 호출)
            from codegraph_engine.multi_index.infrastructure.vector.embedding_provider import (
                OpenAIEmbeddingProvider,
            )

            provider = OpenAIEmbeddingProvider(model=embedding_model, concurrency=4)

            # 배치 처리
            all_embeddings: list[list[float]] = []
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i : i + batch_size]
                batch_embeddings = await provider.embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)

                logger.debug(
                    "vector_batch_complete",
                    batch_num=i // batch_size + 1,
                    total_batches=(len(texts) + batch_size - 1) // batch_size,
                    batch_size=len(batch_texts),
                )

            # 4. 벡터 캐시에 저장 (Qdrant 대신 메모리 캐시)
            vector_cache_key = f"vectors:{repo_id}:{snapshot_id}"
            self.chunk_cache[vector_cache_key] = {
                "embeddings": [
                    {
                        "chunk_id": chunk_ids[i],
                        "embedding": all_embeddings[i],
                        "kind": get_chunk_attr(embeddable_chunks[i], "kind"),
                        "file_path": get_chunk_attr(embeddable_chunks[i], "file_path"),
                    }
                    for i in range(len(all_embeddings))
                ],
                "model": embedding_model,
                "dimension": len(all_embeddings[0]) if all_embeddings else 0,
            }

            duration = (datetime.now() - start_time).total_seconds()

            logger.info(
                "vector_index_completed",
                repo_id=repo_id,
                vectors_indexed=len(all_embeddings),
                filtered_out=filtered_count,
                duration_seconds=duration,
                embedding_model=embedding_model,
            )

            return JobResult.ok(
                data={
                    "vectors_indexed": len(all_embeddings),
                    "filtered_out": filtered_count,
                    "duration_seconds": duration,
                    "embedding_model": embedding_model,
                    "dimension": len(all_embeddings[0]) if all_embeddings else 0,
                    "throughput_vectors_per_sec": len(all_embeddings)
                    / max(duration, self.config.metrics.min_duration_epsilon),
                    "vector_cache_key": vector_cache_key,
                }
            )

        except Exception as e:
            logger.error("vector_index_failed", repo_id=repo_id, error=str(e), exc_info=True)

            # Classify error
            error_str = str(e).lower()
            if "rate limit" in error_str or "429" in error_str:
                error_category = ErrorCategory.TRANSIENT  # Rate limit → 재시도
                error_code = ErrorCode.RATE_LIMITED
            elif "connection" in error_str or "timeout" in error_str:
                error_category = ErrorCategory.TRANSIENT  # 네트워크 오류 → 재시도
                error_code = ErrorCode.NETWORK_ERROR
            elif "qdrant" in error_str or "grpc" in error_str:
                error_category = ErrorCategory.INFRASTRUCTURE
                error_code = ErrorCode.QDRANT_ERROR
            elif "model" in error_str or "embedding" in error_str:
                error_category = ErrorCategory.PERMANENT  # 잘못된 모델
                error_code = ErrorCode.INVALID_MODEL
            else:
                error_category = ErrorCategory.TRANSIENT
                error_code = ErrorCode.VECTOR_INDEX_ERROR

            return JobResult.fail(
                error=f"Vector indexing failed: {e}",
                data={"error_code": error_code, "error_category": error_category},
            )
