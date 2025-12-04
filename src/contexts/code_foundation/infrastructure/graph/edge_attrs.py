"""
Typed Edge Attributes

EdgeKind별 타입이 정의된 속성 스키마입니다.

기존 dict[str, Any] 대신 타입 안전한 속성 클래스를 제공합니다.

사용 예시:
```python
# 생성
attrs = CallsEdgeAttrs(
    call_site_line=42,
    is_async=True,
    argument_count=3,
)

# 직렬화 (저장용)
attrs_dict = attrs.to_dict()

# 역직렬화 (로드용)
attrs = CallsEdgeAttrs.from_dict(attrs_dict)

# edge에 설정
edge = GraphEdge(
    id="...",
    kind=GraphEdgeKind.CALLS,
    source_id="...",
    target_id="...",
    attrs=attrs.to_dict(),
)
```
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from src.contexts.code_foundation.infrastructure.ir.models import Span

# ============================================================
# Base
# ============================================================


@dataclass
class EdgeAttrsBase:
    """Edge 속성 기본 클래스."""

    def to_dict(self) -> dict[str, Any]:
        """딕셔너리로 변환."""
        result = {}
        for k, v in asdict(self).items():
            if v is not None:  # None 값은 제외
                if isinstance(v, Span):
                    result[k] = {
                        "start_line": v.start_line,
                        "start_col": v.start_col,
                        "end_line": v.end_line,
                        "end_col": v.end_col,
                    }
                else:
                    result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EdgeAttrsBase":
        """딕셔너리에서 생성."""
        # Span 복원
        if "span" in data and isinstance(data["span"], dict):
            data["span"] = Span(**data["span"])
        if "call_site_span" in data and isinstance(data["call_site_span"], dict):
            data["call_site_span"] = Span(**data["call_site_span"])

        # 클래스 필드에 맞는 키만 추출
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}

        return cls(**filtered_data)


# ============================================================
# Structural Edges
# ============================================================


@dataclass
class ContainsEdgeAttrs(EdgeAttrsBase):
    """
    CONTAINS edge 속성.

    Parent-child 포함 관계 (File contains Class, Class contains Method).
    """

    # 자식 노드의 순서 (같은 부모 내에서)
    child_index: int | None = None

    # 자식 노드의 가시성
    visibility: str | None = None  # public, private, protected


@dataclass
class ImportsEdgeAttrs(EdgeAttrsBase):
    """
    IMPORTS edge 속성.

    모듈 import 관계.
    """

    # Import 구문 위치
    span: Span | None = None

    # Import 종류
    import_kind: str | None = None  # absolute, relative, from_import

    # Import alias (as 구문)
    alias: str | None = None

    # Relative import level (from .. import 의 dot 개수)
    level: int = 0

    # Import한 심볼 이름 (from x import y의 y)
    imported_name: str | None = None

    # 전체 import 여부 (from x import *)
    is_wildcard: bool = False


@dataclass
class InheritsEdgeAttrs(EdgeAttrsBase):
    """
    INHERITS edge 속성.

    클래스 상속 관계.
    """

    # MRO(Method Resolution Order)에서의 인덱스
    mro_index: int | None = None

    # Mixin 여부
    is_mixin: bool = False

    # Generic type arguments (List[int]의 int)
    type_arguments: list[str] = field(default_factory=list)


@dataclass
class ImplementsEdgeAttrs(EdgeAttrsBase):
    """
    IMPLEMENTS edge 속성.

    인터페이스/프로토콜 구현 관계.
    """

    # 구현하는 메서드 목록
    implemented_methods: list[str] = field(default_factory=list)

    # 완전 구현 여부
    is_complete: bool = True


# ============================================================
# Call/Reference Edges
# ============================================================


@dataclass
class CallsEdgeAttrs(EdgeAttrsBase):
    """
    CALLS edge 속성.

    함수/메서드 호출 관계.
    """

    # 호출 위치
    call_site_span: Span | None = None
    call_site_line: int | None = None
    call_site_col: int | None = None

    # 호출 특성
    is_async: bool = False  # await 호출
    is_method_call: bool = False  # obj.method() 형태
    is_constructor: bool = False  # 생성자 호출
    is_super_call: bool = False  # super() 호출

    # 인자 정보
    argument_count: int = 0
    has_kwargs: bool = False  # **kwargs 사용
    has_varargs: bool = False  # *args 사용

    # 조건부 호출 (if 문 내부 등)
    is_conditional: bool = False

    # 반복 호출 (for/while 내부)
    is_in_loop: bool = False


@dataclass
class ReferencesTypeEdgeAttrs(EdgeAttrsBase):
    """
    REFERENCES_TYPE edge 속성.

    타입 참조 관계 (변수 타입, 파라미터 타입, 반환 타입 등).
    """

    # 참조 위치
    span: Span | None = None

    # 참조 컨텍스트
    context: str | None = None  # variable_type, parameter_type, return_type, generic_arg

    # Nullable 여부
    is_nullable: bool = False

    # Generic parameter인지
    is_generic_param: bool = False


@dataclass
class ReferencesSymbolEdgeAttrs(EdgeAttrsBase):
    """
    REFERENCES_SYMBOL edge 속성.

    심볼(변수, 함수, 클래스 등) 참조 관계.
    """

    # 참조 위치
    span: Span | None = None

    # 참조 종류
    reference_kind: str | None = None  # read, write, call, type_hint

    # 어트리뷰트 접근인지
    is_attribute_access: bool = False

    # self/this 참조인지
    is_self_reference: bool = False


# ============================================================
# Data Flow Edges
# ============================================================


@dataclass
class ReadsEdgeAttrs(EdgeAttrsBase):
    """
    READS edge 속성.

    변수 읽기 관계.
    """

    # 읽기 위치
    span: Span | None = None

    # 읽기 컨텍스트
    context: str | None = None  # expression, condition, return, argument


@dataclass
class WritesEdgeAttrs(EdgeAttrsBase):
    """
    WRITES edge 속성.

    변수 쓰기 관계.
    """

    # 쓰기 위치
    span: Span | None = None

    # 쓰기 종류
    write_kind: str | None = None  # assign, augmented_assign, parameter, for_target

    # 첫 정의인지
    is_definition: bool = False

    # 재할당인지
    is_reassignment: bool = False


# ============================================================
# Control Flow Edges
# ============================================================


@dataclass
class CfgNextEdgeAttrs(EdgeAttrsBase):
    """
    CFG_NEXT edge 속성.

    순차 실행 관계.
    """

    # 항상 실행되는지 (vs 조건부)
    is_unconditional: bool = True


@dataclass
class CfgBranchEdgeAttrs(EdgeAttrsBase):
    """
    CFG_BRANCH edge 속성.

    조건 분기 관계.
    """

    # 분기 종류
    branch_kind: str | None = None  # true_branch, false_branch, case, default

    # 조건 표현식 (간략화)
    condition_summary: str | None = None


@dataclass
class CfgLoopEdgeAttrs(EdgeAttrsBase):
    """
    CFG_LOOP edge 속성.

    루프 백엣지 관계.
    """

    # 루프 종류
    loop_kind: str | None = None  # for, while, do_while

    # 반복 횟수 힌트 (정적 분석 가능한 경우)
    iteration_hint: int | None = None


@dataclass
class CfgHandlerEdgeAttrs(EdgeAttrsBase):
    """
    CFG_HANDLER edge 속성.

    예외 핸들러 관계.
    """

    # 처리하는 예외 타입
    exception_types: list[str] = field(default_factory=list)

    # finally 블록인지
    is_finally: bool = False


# ============================================================
# Framework/Architecture Edges
# ============================================================


@dataclass
class RouteHandlerEdgeAttrs(EdgeAttrsBase):
    """
    ROUTE_HANDLER edge 속성.

    라우트 → 핸들러 관계.
    """

    # HTTP 메서드
    http_method: str | None = None  # GET, POST, PUT, DELETE, etc.

    # 라우트 경로
    route_path: str | None = None

    # 미들웨어 적용 여부
    has_middleware: bool = False


@dataclass
class HandlesRequestEdgeAttrs(EdgeAttrsBase):
    """
    HANDLES_REQUEST edge 속성.

    핸들러 → 서비스 관계.
    """

    # 요청 처리 메서드
    handler_method: str | None = None


@dataclass
class UsesRepositoryEdgeAttrs(EdgeAttrsBase):
    """
    USES_REPOSITORY edge 속성.

    서비스 → 레포지토리 관계.
    """

    # 사용하는 레포지토리 메서드들
    used_methods: list[str] = field(default_factory=list)


@dataclass
class DecoratesEdgeAttrs(EdgeAttrsBase):
    """
    DECORATES edge 속성.

    데코레이터 적용 관계.
    """

    # 데코레이터 순서 (여러 개일 경우)
    decorator_order: int = 0

    # 데코레이터 인자
    decorator_args: list[str] = field(default_factory=list)


@dataclass
class InstantiatesEdgeAttrs(EdgeAttrsBase):
    """
    INSTANTIATES edge 속성.

    객체 생성 관계.
    """

    # 생성 위치
    span: Span | None = None

    # 생성자 인자 개수
    argument_count: int = 0


# ============================================================
# Documentation Edges
# ============================================================


@dataclass
class DocumentsEdgeAttrs(EdgeAttrsBase):
    """
    DOCUMENTS edge 속성.

    파일 → 문서 관계.
    """

    # 문서 타입
    doc_type: str | None = None  # readme, api_doc, tutorial, etc.


@dataclass
class ReferencesCodeEdgeAttrs(EdgeAttrsBase):
    """
    REFERENCES_CODE edge 속성.

    문서 → 코드 참조 관계.
    """

    # 참조 컨텍스트 (코드 블록, 링크 등)
    reference_context: str | None = None  # code_block, inline_code, link

    # 문서 내 위치
    doc_line: int | None = None


# ============================================================
# Factory / Helper
# ============================================================


# EdgeKind -> AttrsClass 매핑
EDGE_ATTRS_MAP: dict[str, type[EdgeAttrsBase]] = {
    "CONTAINS": ContainsEdgeAttrs,
    "IMPORTS": ImportsEdgeAttrs,
    "INHERITS": InheritsEdgeAttrs,
    "IMPLEMENTS": ImplementsEdgeAttrs,
    "CALLS": CallsEdgeAttrs,
    "REFERENCES_TYPE": ReferencesTypeEdgeAttrs,
    "REFERENCES_SYMBOL": ReferencesSymbolEdgeAttrs,
    "READS": ReadsEdgeAttrs,
    "WRITES": WritesEdgeAttrs,
    "CFG_NEXT": CfgNextEdgeAttrs,
    "CFG_BRANCH": CfgBranchEdgeAttrs,
    "CFG_LOOP": CfgLoopEdgeAttrs,
    "CFG_HANDLER": CfgHandlerEdgeAttrs,
    "ROUTE_HANDLER": RouteHandlerEdgeAttrs,
    "HANDLES_REQUEST": HandlesRequestEdgeAttrs,
    "USES_REPOSITORY": UsesRepositoryEdgeAttrs,
    "DECORATES": DecoratesEdgeAttrs,
    "INSTANTIATES": InstantiatesEdgeAttrs,
    "DOCUMENTS": DocumentsEdgeAttrs,
    "REFERENCES_CODE": ReferencesCodeEdgeAttrs,
}


def create_edge_attrs(edge_kind: str, **kwargs) -> EdgeAttrsBase:
    """
    EdgeKind에 맞는 attrs 인스턴스 생성.

    Args:
        edge_kind: Edge 종류 (GraphEdgeKind.value)
        **kwargs: 속성 값들

    Returns:
        해당 EdgeKind의 attrs 인스턴스
    """
    attrs_class = EDGE_ATTRS_MAP.get(edge_kind)

    if attrs_class is None:
        # 알 수 없는 EdgeKind → 기본 클래스
        return EdgeAttrsBase()

    return attrs_class(**kwargs)


def parse_edge_attrs(edge_kind: str, attrs_dict: dict[str, Any]) -> EdgeAttrsBase:
    """
    딕셔너리에서 EdgeKind에 맞는 attrs 인스턴스 파싱.

    Args:
        edge_kind: Edge 종류
        attrs_dict: 속성 딕셔너리

    Returns:
        해당 EdgeKind의 attrs 인스턴스
    """
    attrs_class = EDGE_ATTRS_MAP.get(edge_kind)

    if attrs_class is None:
        return EdgeAttrsBase()

    return attrs_class.from_dict(attrs_dict)
