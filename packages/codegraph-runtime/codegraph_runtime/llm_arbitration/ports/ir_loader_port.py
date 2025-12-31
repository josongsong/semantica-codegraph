"""
IR Loader Port - Hexagonal Architecture Interface

SOTA L11 원칙:
- Port/Adapter 패턴 (Hexagonal Architecture)
- Protocol (구조적 타이핑, No ABC overhead)
- 명확한 Contract (docstring + type hints)
- No implementation details (순수 인터페이스)
"""

from typing import Protocol, runtime_checkable

from codegraph_engine.code_foundation.infrastructure.ir.models import IRDocument


@runtime_checkable
class IRLoaderPort(Protocol):
    """
    IR Document 로더 Port (Hexagonal Architecture).

    책임:
        - scope (repo_id, snapshot_id) → IRDocument 로드
        - 실패 시 None 반환 (예외 던지지 않음)

    구현체:
        - IndexingContextIRLoader: StageContext에서 로드
        - CachedIRLoader: 캐시 레이어 (향후)
        - PostgresIRLoader: DB에서 로드 (향후)

    SOLID 원칙:
        - S: 단일 책임 (IR 로드만)
        - O: 확장 가능 (새 구현체 추가 가능)
        - L: Liskov 치환 (모든 구현체 교체 가능)
        - I: 인터페이스 분리 (최소 메서드)
        - D: 의존성 역전 (ExecuteExecutor는 Port에만 의존)
    """

    async def load_ir(
        self,
        repo_id: str,
        snapshot_id: str,
    ) -> IRDocument | None:
        """
        Load IR Document by scope.

        Args:
            repo_id: Repository identifier
            snapshot_id: Snapshot identifier (commit hash, timestamp, etc.)

        Returns:
            IRDocument if found, None otherwise

        Raises:
            Never raises (failures return None)

        Contract:
            - MUST return None on failure (no exceptions)
            - MUST be idempotent (same input → same output)
            - MUST NOT mutate input parameters
            - SHOULD log errors internally

        Performance:
            - SHOULD complete within 100ms (cached)
            - MAY take longer on first load (indexing)
        """
        ...
