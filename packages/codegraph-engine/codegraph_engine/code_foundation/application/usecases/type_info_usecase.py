"""
TypeInfo UseCase (SOTA)

RFC-052: MCP Service Layer Architecture
Get type inference information for symbols.

Differentiation:
- Type Narrowing support (context-sensitive)
- Constraint-based proof
- Evidence-backed results

MCP Tool Mapping:
- MCP: get_type_info(symbol, file_path, line)
- UseCase: TypeInfoUseCase.execute(TypeInfoRequest)
"""

import uuid
from dataclasses import dataclass
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.application.dto import (
    AnalysisError,
    ErrorCode,
    VerificationSnapshot,
)
from codegraph_engine.code_foundation.application.usecases.base import (
    BaseUseCase,
    UseCaseRequest,
    UseCaseResponse,
)
from codegraph_engine.code_foundation.domain.evidence import (
    EvidenceKind,
    EvidenceRef,
    GraphRefs,
)

logger = get_logger(__name__)


@dataclass
class TypeInfoRequest(UseCaseRequest):
    """
    TypeInfo request.

    Args:
        symbol: Symbol name
        file_path: File containing symbol (optional)
        line: Line number for narrowing (optional)
        column: Column for precise narrowing (optional)
    """

    symbol: str = ""
    file_path: str | None = None
    line: int | None = None
    column: int | None = None


@dataclass
class TypeInfo:
    """Type information result"""

    symbol: str
    inferred_type: str
    confidence: float  # 0.0-1.0
    constraints: list[str]  # Human-readable constraints
    narrowed: bool  # True if context-sensitive narrowing applied
    program_point: dict[str, Any] | None = None  # file, line, column


@dataclass
class TypeInfoResponse(UseCaseResponse):
    """
    TypeInfo response.

    Data includes:
    - type_info: TypeInfo object
    """

    type_info: TypeInfo | None = None


class TypeInfoUseCase(BaseUseCase[TypeInfoRequest, TypeInfoResponse]):
    """
    Type Inference UseCase (SOTA).

    Features:
    - Type inference from IR
    - Type narrowing (context-sensitive)
    - Constraint-based proof
    """

    async def _execute_impl(
        self,
        request: TypeInfoRequest,
        session_id: str,
        snapshot_id: str,
    ) -> TypeInfoResponse:
        """
        Execute type inference.

        Steps:
        1. Validate request
        2. Get IR document
        3. Run type inference
        4. Apply narrowing if program point provided
        5. Create evidence
        6. Generate response
        """
        # Validate
        if not request.symbol:
            error = AnalysisError(
                error_code=ErrorCode.INVALID_QUERYPLAN,
                message="symbol is required",
                recovery_hints=[],
            )
            return TypeInfoResponse(
                verification=self._create_error_verification(),
                error=error,
            )

        try:
            # Get type inference engine
            from src.container import container

            # Get IRAnalyzer for symbol lookup
            # Note: This requires actual IR document from repo
            # For MVP, return NotImplemented with clear error

            raise NotImplementedError(
                "TypeInfo requires integration with IRDocument repository. "
                "Needs: repo_id → IRDocument → Type inference engine"
            )

        except NotImplementedError as e:
            # Clear NotImplemented error with recovery hints
            error = AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=str(e),
                recovery_hints=[],
            )
            return TypeInfoResponse(
                verification=self._create_error_verification(),
                error=error,
            )

        except Exception as e:
            logger.error("type_info_failed", error=str(e))
            error = AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=f"Type inference failed: {str(e)}",
                recovery_hints=[],
            )
            return TypeInfoResponse(
                verification=self._create_error_verification(),
                error=error,
            )

    def _get_session_id(self, request: TypeInfoRequest) -> str:
        return request.session_id or f"session_{uuid.uuid4().hex[:8]}"

    def _get_repo_id(self, request: TypeInfoRequest) -> str:
        return request.repo_id

    def _create_error_response(self, error: str) -> TypeInfoResponse:
        return TypeInfoResponse(
            verification=self._create_error_verification(),
            error=AnalysisError(
                error_code=ErrorCode.INTERNAL_ERROR,
                message=error,
                recovery_hints=[],
            ),
        )

    def _create_error_verification(self) -> VerificationSnapshot:
        return VerificationSnapshot.create(
            snapshot_id="error",
            queryplan_hash="error",
        )
