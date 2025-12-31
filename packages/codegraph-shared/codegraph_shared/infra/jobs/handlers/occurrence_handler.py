"""
Occurrence Build Handler (L2).

SCIP-compatible occurrence 생성.
L1 (IR Build) 결과를 받아서 occurrence index 생성.
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


class OccurrenceHandler(JobHandler):
    """
    Occurrence Build Handler.

    Payload:
        {
            "repo_id": "repo-123",
            "snapshot_id": "main",
            "ir_cache_key": "ir:repo-123:main",  # L1에서 생성된 IR 캐시 키
        }

    Result:
        {
            "occurrences_created": 5000,
            "occurrence_cache_key": "occ:repo-123:main",
        }

    Error Classification:
        - TRANSIENT: 일시적 메모리 부족
        - PERMANENT: IR 캐시 없음
    """

    def __init__(
        self,
        ir_cache: dict[str, Any] | None = None,
        occurrence_cache: dict[str, Any] | None = None,
        config: IndexingConfig | None = None,
    ):
        """
        Args:
            ir_cache: IR 캐시 (L1에서 생성)
            occurrence_cache: Occurrence 결과 저장 캐시
            config: 인덱싱 설정
        """
        self.ir_cache = ir_cache if ir_cache is not None else {}
        self.occurrence_cache = occurrence_cache if occurrence_cache is not None else {}
        self.config = config or DEFAULT_CONFIG

    async def execute(self, payload: dict[str, Any]) -> JobResult:
        """Occurrence 빌드 실행."""
        repo_id = payload.get("repo_id")
        snapshot_id = payload.get("snapshot_id", self.config.defaults.snapshot_id)
        ir_cache_key = payload.get("ir_cache_key")

        # Validation
        if not repo_id:
            return JobResult.fail(
                error="Missing required field: repo_id",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        if not ir_cache_key:
            return JobResult.fail(
                error="Missing required field: ir_cache_key",
                data={"error_code": ErrorCode.INVALID_PAYLOAD, "error_category": ErrorCategory.PERMANENT},
            )

        # Get IR from cache
        ir_data = self.ir_cache.get(ir_cache_key)
        if not ir_data:
            return JobResult.fail(
                error=f"IR cache not found: {ir_cache_key}",
                data={"error_code": ErrorCode.CACHE_MISS, "error_category": ErrorCategory.PERMANENT},
            )

        logger.info(
            "occurrence_build_started",
            repo_id=repo_id,
            ir_cache_key=ir_cache_key,
        )

        try:
            ir_documents = ir_data["ir_documents"]

            # 🚀 SOTA: Check if Rust L1 already generated occurrences
            # This eliminates the 113s Python L2 overhead entirely
            rust_occurrences_available = False
            total_occurrences = 0

            for file_path, ir_doc in ir_documents.items():
                if hasattr(ir_doc, "occurrences") and ir_doc.occurrences:
                    rust_occurrences_available = True
                    total_occurrences += len(ir_doc.occurrences)

            if rust_occurrences_available:
                # 🚀 Use Rust-generated occurrences (already in ir_doc.occurrences)
                logger.info(
                    "occurrence_using_rust",
                    repo_id=repo_id,
                    message="Using occurrences from Rust L1 (skipping Python generation)",
                    occurrences_count=total_occurrences,
                )
            else:
                # Fallback: Generate occurrences with Python
                logger.info(
                    "occurrence_using_python",
                    repo_id=repo_id,
                    message="Rust occurrences not available, using Python generator",
                )

                from codegraph_engine.code_foundation.infrastructure.ir.occurrence_generator import OccurrenceGenerator

                generator = OccurrenceGenerator()
                total_occurrences = 0

                # Generate occurrences for each file
                for file_path, ir_doc in ir_documents.items():
                    occurrences, _ = generator.generate(ir_doc)

                    # Store occurrences back in IR document
                    if hasattr(ir_doc, "occurrences"):
                        ir_doc.occurrences = occurrences
                        total_occurrences += len(occurrences)

            # Cache occurrences
            cache_key = self.config.cache_keys.make_occurrence_key(repo_id, snapshot_id)
            self.occurrence_cache[cache_key] = {
                "ir_documents": ir_documents,  # Updated with occurrences
                "repo_id": repo_id,
                "snapshot_id": snapshot_id,
            }

            logger.info(
                "occurrence_build_completed",
                repo_id=repo_id,
                occurrences_created=total_occurrences,
                source="rust" if rust_occurrences_available else "python",
            )

            return JobResult.ok(
                data={
                    "occurrences_created": total_occurrences,
                    "occurrence_cache_key": cache_key,
                    "source": "rust" if rust_occurrences_available else "python",
                }
            )

        except ImportError as e:
            logger.warning(
                "occurrence_generator_not_available",
                error=str(e),
                message="Skipping occurrence generation",
            )
            # Graceful degradation - return success with 0 occurrences
            cache_key = self.config.cache_keys.make_occurrence_key(repo_id, snapshot_id)
            self.occurrence_cache[cache_key] = ir_data  # Pass through without occurrences

            return JobResult.ok(
                data={
                    "occurrences_created": 0,
                    "occurrence_cache_key": cache_key,
                    "warning": "OccurrenceGenerator not available",
                }
            )

        except Exception as e:
            logger.error("occurrence_build_failed", repo_id=repo_id, error=str(e), exc_info=True)

            error_str = str(e).lower()
            if "memory" in error_str:
                error_category = ErrorCategory.INFRASTRUCTURE
                error_code = ErrorCode.OUT_OF_MEMORY
            else:
                error_category = ErrorCategory.TRANSIENT
                error_code = ErrorCode.OCCURRENCE_BUILD_ERROR

            return JobResult.fail(
                error=f"Occurrence build failed: {e}",
                data={"error_code": error_code, "error_category": error_category},
            )
