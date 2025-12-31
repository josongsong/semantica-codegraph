"""
Lexical Index Handler (L3).

Tantivy를 사용하여 렉시컬 인덱싱 수행.
병렬 파이프라인에서 L1 (IR)과 동시 실행 가능 - 파일 경로만 필요.
"""

from pathlib import Path
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


class LexicalIndexHandler(JobHandler):
    """
    Lexical Index Handler.

    Payload:
        {
            "repo_path": "/path/to/repo",
            "repo_id": "repo-123",
            "index_dir": "data/tantivy_index",
            "file_patterns": ["*.py"],
            "batch_size": 100,
        }

    Result:
        {
            "files_indexed": 100,
            "failed_files": 2,
            "duration_seconds": 5.3,
        }

    Error Classification:
        - TRANSIENT: 인덱스 잠금 충돌, 일시적 IO 오류
        - PERMANENT: 잘못된 인덱스 경로, 손상된 인덱스
        - INFRASTRUCTURE: 디스크 부족, Tantivy 라이브러리 오류
    """

    def __init__(
        self,
        index_dir: str | None = None,
        config: IndexingConfig | None = None,
    ):
        """
        Args:
            index_dir: Tantivy 인덱스 디렉토리 (기본: config에서)
            config: 인덱싱 설정 (기본: DEFAULT_CONFIG)
        """
        self.config = config or DEFAULT_CONFIG
        self.default_index_dir = index_dir or self.config.defaults.tantivy_index_dir

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """렉시컬 인덱싱 실행."""
        repo_path = payload.get("repo_path")
        repo_id = payload.get("repo_id")
        index_dir = payload.get("index_dir", self.default_index_dir)
        file_patterns = payload.get("file_patterns", list(self.config.defaults.file_patterns))
        batch_size = payload.get("batch_size", self.config.batch.lexical_batch_size)

        # Validation
        if not repo_path:
            return JobResult.fail(
                error="Missing required field: repo_path",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        if not repo_id:
            return JobResult.fail(
                error="Missing required field: repo_id",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        repo_path = Path(repo_path).resolve()
        if not repo_path.exists():
            return JobResult.fail(
                error=f"Repository path does not exist: {repo_path}",
                data={"error_code": ErrorCode.PATH_NOT_FOUND, "error_category": ErrorCategory.PERMANENT},
            )

        logger.info(
            "lexical_index_started",
            repo_id=repo_id,
            repo_path=str(repo_path),
            index_dir=index_dir,
        )

        try:
            from datetime import datetime

            start_time = datetime.now()

            # Import Tantivy adapter
            from codegraph_engine.multi_index.domain.ports import FileToIndex, IndexingMode
            from codegraph_engine.multi_index.infrastructure.lexical.tantivy import TantivyCodeIndex

            # Create index adapter
            indexing_mode = IndexingMode[self.config.lexical.indexing_mode]
            index_adapter = TantivyCodeIndex(
                index_dir=index_dir,
                chunk_store=None,  # L3는 청크 불필요
                mode=indexing_mode,
                batch_size=batch_size,
            )

            # Scan files
            files = []
            for pattern in file_patterns:
                files.extend(repo_path.rglob(pattern))

            # Exclude patterns (config에서 가져옴)
            exclude_patterns = self.config.exclude_patterns.get_lexical_excludes()
            files = [f for f in files if not any(p in str(f) for p in exclude_patterns)]

            if not files:
                return JobResult.ok(
                    data={
                        "files_indexed": 0,
                        "failed_files": 0,
                        "duration_seconds": 0.0,
                        "warning": "No files found matching patterns",
                    }
                )

            # Build FileToIndex list
            files_to_index: list[FileToIndex] = []
            for file_path in files:
                try:
                    content = file_path.read_text(errors=self.config.lexical.file_read_errors)
                    files_to_index.append(
                        FileToIndex(
                            repo_id=repo_id,
                            file_path=str(file_path),
                            content=content,
                        )
                    )
                except Exception as e:
                    logger.warning("file_read_failed", file_path=str(file_path), error=str(e))

            # Batch index
            if files_to_index:
                result = await index_adapter.index_files_batch(files_to_index, fail_fast=False)

                duration = (datetime.now() - start_time).total_seconds()

                logger.info(
                    "lexical_index_completed",
                    repo_id=repo_id,
                    files_indexed=result.success_count,
                    failed_files=len(result.failed_files),
                    duration_seconds=duration,
                )

                # Close index
                await index_adapter.close()

                return JobResult.ok(
                    data={
                        "files_indexed": result.success_count,
                        "failed_files": len(result.failed_files),
                        "duration_seconds": duration,
                        "throughput_files_per_sec": result.success_count
                        / max(duration, self.config.metrics.min_duration_epsilon),
                    }
                )
            else:
                return JobResult.ok(
                    data={
                        "files_indexed": 0,
                        "failed_files": 0,
                        "duration_seconds": 0.0,
                    }
                )

        except OSError as e:
            error_str = str(e).lower()
            if "no space" in error_str or "disk" in error_str:
                error_category = ErrorCategory.INFRASTRUCTURE
                error_code = ErrorCode.DISK_FULL
            elif "lock" in error_str:
                error_category = ErrorCategory.TRANSIENT  # 인덱스 잠금 → 재시도
                error_code = ErrorCode.INDEX_LOCKED
            else:
                error_category = ErrorCategory.TRANSIENT
                error_code = ErrorCode.IO_ERROR

            logger.error("lexical_index_os_error", repo_id=repo_id, error=str(e))
            return JobResult.fail(
                error=f"Lexical indexing OS error: {e}",
                data={"error_code": error_code, "error_category": error_category},
            )

        except Exception as e:
            logger.error("lexical_index_failed", repo_id=repo_id, error=str(e), exc_info=True)

            # Classify error
            error_str = str(e).lower()
            if "corrupt" in error_str or "invalid" in error_str:
                error_category = ErrorCategory.PERMANENT
                error_code = ErrorCode.INDEX_CORRUPTED
            else:
                error_category = ErrorCategory.TRANSIENT
                error_code = ErrorCode.LEXICAL_INDEX_ERROR

            return JobResult.fail(
                error=f"Lexical indexing failed: {e}",
                data={"error_code": error_code, "error_category": error_category},
            )
