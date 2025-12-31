"""
Expression Ports

Expression.attrs의 타입 안전한 계약 정의.

이 파일은 Expression IR의 attrs 필드가 가져야 하는 구조를 명시합니다.
각 ExprKind별로 필요한 attrs 필드가 다르며, 이를 TypedDict로 정의합니다.

🔥 핵심 문제:
- 기존: attrs: dict[str, Any] → 어떤 필드가 있는지 알 수 없음
- 해결: ExprKind별 TypedDict 정의 → 타입 안전성 + IDE 지원

사용 예:
    if expr.kind == ExprKind.CALL:
        attrs: CallExprAttrs = expr.attrs  # 타입 힌트
        callee = attrs.get("callee_name")  # IDE 자동완성 지원
"""

from typing import Any, Literal, TypedDict


# =============================================================================
# 공통 Expression Attrs
# =============================================================================


class CommonExprAttrs(TypedDict, total=False):
    """
    모든 Expression이 가질 수 있는 공통 attrs.

    이 필드들은 Pyright/LSP 통합 시 ExpressionBuilder가 추가합니다.
    """

    # Pyright/LSP에서 추가되는 타입 정보
    definition_file: str  # 심볼 정의 파일 경로
    definition_line: int  # 심볼 정의 라인
    definition_fqn: str  # Fully Qualified Name (예: "sqlite3.Connection.execute")

    # 타입 정보 (🔥 Taint Analysis 핵심)
    receiver_type: str  # 메서드 호출 대상 타입 (예: "(variable) conn: Connection")
    lsp_type: str  # LSP에서 반환한 원본 타입 문자열
    inferred_type: str  # 추론된 타입 (예: "sqlite3.Cursor")

    # TypeInfo 객체 (runtime)
    type_info: Any  # TypeInfo 인스턴스

    # 제네릭 파라미터
    generic_params: list[str]  # 예: ["T", "K"]


# =============================================================================
# CALL Expression Attrs
# =============================================================================


class CallExprAttrs(CommonExprAttrs, total=False):
    """
    CALL Expression (함수/메서드 호출)의 attrs.

    필수 필드:
        - callee_name: 호출되는 함수/메서드 이름

    선택 필드:
        - callee_id: IR Node ID
        - arg_expr_ids: 인자 Expression ID 리스트
        - receiver_type: 메서드 호출 시 receiver 타입 (🔥 HCG/Taint 핵심)
        - receiver_name: receiver 변수명
        - receiver_span: receiver 위치 정보

    Usage:
        ```python
        # TypeAwareAtomMatcher.match_call()
        callee_name = expr.attrs.get("callee_name")  # 필수
        receiver_type = expr.attrs.get("receiver_type")  # Taint matching에 중요
        ```
    """

    # 🔥 필수 (AtomMatcher가 반드시 필요)
    callee_name: str  # 예: "execute", "os.system", "request.args.get"

    # 호출 대상 정보
    callee_id: str  # IR Node ID of the callee
    callee_expr_id: str  # Callee Expression ID

    # 인자 정보
    arg_expr_ids: list[str]  # 인자 Expression ID 리스트
    arg_types: list[str]  # 인자 타입 리스트 (Pyright에서)
    call_args: list[dict[str, Any]]  # 상세 인자 정보

    # Receiver 정보 (메서드 호출 시) - 🔥 HCG/Taint 핵심
    receiver_name: str  # 예: "conn", "cursor", "request"
    receiver_span: dict[str, int]  # {"line": 10, "col": 5}
    receiver_expr_id: str  # Receiver Expression ID

    # 반환 타입
    return_type: str  # 함수 반환 타입


class CallExprAttrsRequired(TypedDict):
    """CALL Expression 필수 attrs (total=True)."""

    callee_name: str


# =============================================================================
# ATTRIBUTE Expression Attrs
# =============================================================================


class AttributeExprAttrs(CommonExprAttrs, total=False):
    """
    ATTRIBUTE Expression (속성 접근)의 attrs.

    예: obj.attr, request.args, self.field

    필수 필드:
        - attr_name: 속성 이름
        - base_expr_id: 베이스 객체 Expression ID
    """

    # 🔥 필수
    attr_name: str  # 예: "args", "field", "value"
    base_expr_id: str  # 베이스 객체 Expression ID

    # 추가 정보
    base_type: str  # 베이스 객체 타입
    attr_type: str  # 속성 타입


# =============================================================================
# LITERAL Expression Attrs
# =============================================================================


class LiteralExprAttrs(CommonExprAttrs, total=False):
    """
    LITERAL Expression (상수 값)의 attrs.

    예: 42, "hello", True, None
    """

    # 🔥 필수
    value: Any  # 리터럴 값
    value_type: str  # "int", "str", "bool", "None", "float"


# =============================================================================
# NAME_LOAD Expression Attrs
# =============================================================================


class NameLoadExprAttrs(CommonExprAttrs, total=False):
    """
    NAME_LOAD Expression (변수 읽기)의 attrs.

    예: x, user_input, config
    """

    # 🔥 필수
    var_name: str  # 변수 이름

    # 추가 정보
    var_type: str  # 변수 타입 (Pyright)
    is_global: bool  # 전역 변수 여부
    is_nonlocal: bool  # nonlocal 변수 여부


# =============================================================================
# SUBSCRIPT Expression Attrs
# =============================================================================


class SubscriptExprAttrs(CommonExprAttrs, total=False):
    """
    SUBSCRIPT Expression (인덱스 접근)의 attrs.

    예: arr[0], dict["key"], matrix[i][j]
    """

    base_expr_id: str  # 베이스 객체 Expression ID
    index_expr_id: str  # 인덱스 Expression ID
    index_value: Any  # 인덱스가 상수인 경우 값
    slice_info: dict[str, Any]  # 슬라이스 정보 (start, stop, step)


# =============================================================================
# BIN_OP Expression Attrs
# =============================================================================


class BinOpExprAttrs(CommonExprAttrs, total=False):
    """
    BIN_OP Expression (이항 연산)의 attrs.

    예: a + b, x * y, s1 + s2
    """

    operator: str  # "+", "-", "*", "/", "//", "%", "**", etc.
    left_expr_id: str  # 왼쪽 피연산자 Expression ID
    right_expr_id: str  # 오른쪽 피연산자 Expression ID
    result_type: str  # 연산 결과 타입


# =============================================================================
# UNARY_OP Expression Attrs
# =============================================================================


class UnaryOpExprAttrs(CommonExprAttrs, total=False):
    """
    UNARY_OP Expression (단항 연산)의 attrs.

    예: -x, not y, ~z
    """

    operator: str  # "-", "+", "not", "~"
    operand_expr_id: str  # 피연산자 Expression ID


# =============================================================================
# COMPARE Expression Attrs
# =============================================================================


class CompareExprAttrs(CommonExprAttrs, total=False):
    """
    COMPARE Expression (비교 연산)의 attrs.

    예: a < b, x == y, 1 <= n < 10
    """

    operators: list[str]  # ["<", "<=", "==", "!=", ">", ">=", "in", "not in", "is", "is not"]
    comparator_expr_ids: list[str]  # 비교 대상 Expression ID 리스트


# =============================================================================
# BOOL_OP Expression Attrs
# =============================================================================


class BoolOpExprAttrs(CommonExprAttrs, total=False):
    """
    BOOL_OP Expression (논리 연산)의 attrs.

    예: a and b, x or y
    """

    operator: Literal["and", "or"]
    operand_expr_ids: list[str]  # 피연산자 Expression ID 리스트


# =============================================================================
# COLLECTION Expression Attrs
# =============================================================================


class CollectionExprAttrs(CommonExprAttrs, total=False):
    """
    COLLECTION Expression (컬렉션 리터럴)의 attrs.

    예: [1, 2, 3], {"a": 1}, {1, 2, 3}
    """

    collection_type: Literal["list", "dict", "set", "tuple"]
    element_expr_ids: list[str]  # 요소 Expression ID 리스트
    key_expr_ids: list[str] | None  # dict인 경우 키 Expression ID 리스트


# =============================================================================
# LAMBDA Expression Attrs
# =============================================================================


class LambdaExprAttrs(CommonExprAttrs, total=False):
    """
    LAMBDA Expression (람다 함수)의 attrs.

    예: lambda x: x + 1
    """

    param_names: list[str]  # 파라미터 이름 리스트
    body_expr_id: str  # 본문 Expression ID


# =============================================================================
# COMPREHENSION Expression Attrs
# =============================================================================


class ComprehensionExprAttrs(CommonExprAttrs, total=False):
    """
    COMPREHENSION Expression (컴프리헨션)의 attrs.

    예: [x*2 for x in items], {k: v for k, v in d.items()}
    """

    comprehension_type: Literal["list", "dict", "set", "generator"]
    element_expr_id: str  # 요소 Expression ID
    generators: list[dict[str, Any]]  # for/if 절 정보


# =============================================================================
# ASSIGN Expression Attrs
# =============================================================================


class AssignExprAttrs(CommonExprAttrs, total=False):
    """
    ASSIGN Expression (할당 대상)의 attrs.

    예: x = value (x 부분)
    """

    target_name: str  # 할당 대상 변수명
    target_type: str  # 할당 대상 타입
    is_augmented: bool  # +=, -= 등 증강 할당 여부


# =============================================================================
# Union Type for All Expression Attrs
# =============================================================================

ExpressionAttrs = (
    CallExprAttrs
    | AttributeExprAttrs
    | LiteralExprAttrs
    | NameLoadExprAttrs
    | SubscriptExprAttrs
    | BinOpExprAttrs
    | UnaryOpExprAttrs
    | CompareExprAttrs
    | BoolOpExprAttrs
    | CollectionExprAttrs
    | LambdaExprAttrs
    | ComprehensionExprAttrs
    | AssignExprAttrs
    | CommonExprAttrs
)
"""
Expression.attrs의 Union 타입.

실제 타입은 Expression.kind에 따라 결정됩니다:
- ExprKind.CALL → CallExprAttrs
- ExprKind.ATTRIBUTE → AttributeExprAttrs
- ExprKind.LITERAL → LiteralExprAttrs
- etc.
"""


# =============================================================================
# Validation Helpers
# =============================================================================


def validate_call_expr_attrs(attrs: dict[str, Any]) -> bool:
    """
    CALL Expression attrs 유효성 검증.

    Args:
        attrs: Expression.attrs

    Returns:
        True if valid, False otherwise
    """
    # callee_name은 필수
    if "callee_name" not in attrs:
        return False
    if not isinstance(attrs["callee_name"], str):
        return False
    if not attrs["callee_name"].strip():
        return False
    return True


def validate_attribute_expr_attrs(attrs: dict[str, Any]) -> bool:
    """
    ATTRIBUTE Expression attrs 유효성 검증.
    """
    if "attr_name" not in attrs:
        return False
    if "base_expr_id" not in attrs:
        return False
    return True


def validate_literal_expr_attrs(attrs: dict[str, Any]) -> bool:
    """
    LITERAL Expression attrs 유효성 검증.
    """
    # value는 필수 (None도 유효한 값)
    return "value" in attrs


def get_required_attrs_for_kind(kind: str) -> list[str]:
    """
    ExprKind별 필수 attrs 필드 반환.

    Args:
        kind: ExprKind 문자열 (예: "Call", "Attribute")

    Returns:
        필수 attrs 필드 이름 리스트
    """
    required_map = {
        "Call": ["callee_name"],
        "Attribute": ["attr_name", "base_expr_id"],
        "Literal": ["value"],
        "NameLoad": ["var_name"],
        "Subscript": ["base_expr_id"],
        "BinOp": ["operator", "left_expr_id", "right_expr_id"],
        "UnaryOp": ["operator", "operand_expr_id"],
        "Compare": ["operators", "comparator_expr_ids"],
        "BoolOp": ["operator", "operand_expr_ids"],
        "Collection": ["collection_type"],
        "Lambda": ["param_names", "body_expr_id"],
        "Comprehension": ["comprehension_type", "element_expr_id"],
        "Assign": ["target_name"],
    }
    return required_map.get(kind, [])


# =============================================================================
# Type Guard for Expression Attrs
# =============================================================================


def is_call_expr_attrs(attrs: dict[str, Any]) -> bool:
    """CallExprAttrs 타입 가드."""
    return "callee_name" in attrs


def is_attribute_expr_attrs(attrs: dict[str, Any]) -> bool:
    """AttributeExprAttrs 타입 가드."""
    return "attr_name" in attrs and "base_expr_id" in attrs


def is_literal_expr_attrs(attrs: dict[str, Any]) -> bool:
    """LiteralExprAttrs 타입 가드."""
    return "value" in attrs


def is_name_load_expr_attrs(attrs: dict[str, Any]) -> bool:
    """NameLoadExprAttrs 타입 가드."""
    return "var_name" in attrs
