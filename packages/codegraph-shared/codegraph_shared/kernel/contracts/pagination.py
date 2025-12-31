"""
Pagination Models (SOTA MCP Protocol)

공통 페이지네이션 타입.
모든 API 응답에서 일관된 페이징을 보장.

Architecture:
- Domain Layer (Pure model)
- Immutable (frozen=True)
- Type-safe (Pydantic)
- JSON serializable

Usage:
    # 단순 페이징
    result = PagedResponse(
        items=[...],
        total=150,
        limit=50,
        next_cursor="cursor_abc123"
    )

    # 요약 포함
    result = PagedResponse(
        items=[...],
        total=1542,
        limit=20,
        next_cursor="cursor_xyz",
        summary=ResultSummary(
            description="총 호출자 1,542건, 상위 모듈: A(430), B(310)",
            top_groups={"A": 430, "B": 310, "C": 120}
        )
    )
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResultSummary(BaseModel):
    """
    결과 요약 (LLM 컨텍스트 최적화)

    대량 결과를 LLM이 이해하기 쉽게 요약.

    Fields:
    - description: 자연어 요약 (3줄 이내)
    - top_groups: 상위 그룹별 카운트 (module/package/file 기준)
    - stats: 추가 통계 (선택)

    Example:
        ResultSummary(
            description="총 호출자 1,542건, 상위 모듈: A(430), B(310), C(120)",
            top_groups={"auth": 430, "api": 310, "utils": 120},
            stats={"max_depth": 5, "critical_paths": 3}
        )
    """

    description: str = Field(..., min_length=1, max_length=500, description="Natural language summary")
    top_groups: dict[str, int] = Field(default_factory=dict, description="Top groups with counts")
    stats: dict[str, Any] = Field(default_factory=dict, description="Additional statistics")

    model_config = {"frozen": True}


class PagedResponse(BaseModel, Generic[T]):
    """
    공통 페이지네이션 응답

    모든 리스트 반환 API의 표준 응답 형식.

    Fields:
    - items: 현재 페이지 아이템들
    - total: 전체 아이템 수 (None이면 unknown)
    - limit: 페이지당 최대 아이템 수
    - next_cursor: 다음 페이지 커서 (None이면 마지막)
    - prev_cursor: 이전 페이지 커서 (선택)
    - summary: 결과 요약 (LLM 컨텍스트 최적화)

    Cursor Strategy:
    - Opaque string (클라이언트가 해석하지 않음)
    - Base64 encoded (offset:timestamp 등)
    - None = 마지막 페이지

    Example:
        PagedResponse(
            items=[{"id": 1}, {"id": 2}],
            total=100,
            limit=50,
            next_cursor="cursor_abc123",
            summary=ResultSummary(description="Found 100 items")
        )
    """

    items: list[Any] = Field(default_factory=list, description="Current page items")
    total: int | None = Field(None, ge=0, description="Total count (None if unknown)")
    limit: int = Field(50, ge=1, le=1000, description="Items per page")
    next_cursor: str | None = Field(None, description="Next page cursor (None if last)")
    prev_cursor: str | None = Field(None, description="Previous page cursor (optional)")
    summary: ResultSummary | None = Field(None, description="Result summary for LLM")

    model_config = {"frozen": True}

    def has_more(self) -> bool:
        """다음 페이지 존재 여부"""
        return self.next_cursor is not None

    def is_empty(self) -> bool:
        """결과 없음"""
        return len(self.items) == 0

    def to_dict(self) -> dict[str, Any]:
        """JSON 직렬화"""
        return {
            "items": self.items,
            "total": self.total,
            "limit": self.limit,
            "next_cursor": self.next_cursor,
            "prev_cursor": self.prev_cursor,
            "summary": self.summary.model_dump() if self.summary else None,
        }


class PaginationParams(BaseModel):
    """
    페이지네이션 요청 파라미터

    모든 리스트 API 요청의 표준 파라미터.

    Fields:
    - limit: 페이지당 최대 아이템 수 (기본 50)
    - cursor: 페이지 커서 (None이면 첫 페이지)
    - summarize: 요약 포함 여부 (기본 True)
    - group_by: 그룹화 기준 (module/package/file)
    - sort: 정렬 기준 (relevance/fanout/churn/risk)

    Example:
        params = PaginationParams(
            limit=20,
            cursor="cursor_abc",
            summarize=True,
            group_by="module",
            sort="relevance"
        )
    """

    limit: int = Field(50, ge=1, le=1000, description="Items per page")
    cursor: str | None = Field(None, description="Page cursor")
    summarize: bool = Field(True, description="Include summary")
    group_by: str | None = Field(None, description="Group by: module/package/file")
    sort: str = Field("relevance", description="Sort: relevance/fanout/churn/risk")

    model_config = {"frozen": True}


def encode_cursor(offset: int, timestamp: str | None = None) -> str:
    """
    커서 인코딩

    Args:
        offset: 오프셋
        timestamp: 타임스탬프 (선택)

    Returns:
        Base64 인코딩된 커서
    """
    import base64

    data = f"{offset}"
    if timestamp:
        data = f"{offset}:{timestamp}"
    return base64.urlsafe_b64encode(data.encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, str | None]:
    """
    커서 디코딩

    Args:
        cursor: Base64 인코딩된 커서

    Returns:
        (offset, timestamp) 튜플

    Raises:
        ValueError: 잘못된 커서
    """
    import base64

    try:
        data = base64.urlsafe_b64decode(cursor.encode()).decode()
        parts = data.split(":", 1)
        offset = int(parts[0])
        timestamp = parts[1] if len(parts) > 1 else None
        return offset, timestamp
    except Exception as e:
        raise ValueError(f"Invalid cursor: {cursor}") from e
