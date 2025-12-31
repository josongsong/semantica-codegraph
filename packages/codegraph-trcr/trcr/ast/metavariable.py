"""
Metavariable System

Semgrep-style 메타변수 지원 ($VAR, $FUNC, $... 등).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum, auto


class MetavariableType(Enum):
    """메타변수 타입"""

    IDENTIFIER = auto()  # $VAR - 단일 식별자
    EXPRESSION = auto()  # $EXPR - 표현식
    STATEMENT = auto()  # $STMT - 문장
    ELLIPSIS = auto()  # $... - 0개 이상의 요소
    TYPED = auto()  # $VAR:type - 타입 제약
    FUNCTION = auto()  # $FUNC - 함수명
    STRING = auto()  # $STR - 문자열
    NUMBER = auto()  # $NUM - 숫자
    ANY = auto()  # $_ - 와일드카드


@dataclass
class Metavariable:
    """
    메타변수 정의

    Pattern에서 사용되는 플레이스홀더로, 코드의 특정 부분과 매칭됨.

    Examples:
        $QUERY   - 단일 식별자/표현식
        $...ARGS - 가변 인자
        $FUNC    - 함수명
        $_       - 와일드카드 (무시)
    """

    name: str
    var_type: MetavariableType = MetavariableType.ANY
    type_constraint: str | None = None
    is_ellipsis: bool = False

    # 패턴 상수
    PATTERN = re.compile(r"\$(\.\.\.|_|[A-Z][A-Z0-9_]*)(?::(\w+))?")

    @classmethod
    def parse(cls, text: str) -> Metavariable | None:
        """
        문자열에서 메타변수 파싱

        Args:
            text: 메타변수 문자열 (e.g., "$QUERY", "$...ARGS")

        Returns:
            Metavariable 또는 None
        """
        match = cls.PATTERN.match(text)
        if not match:
            return None

        name = match.group(1)
        type_constraint = match.group(2)

        # 특수 메타변수 타입 결정
        if name == "...":
            return cls(
                name=name,
                var_type=MetavariableType.ELLIPSIS,
                is_ellipsis=True,
            )
        elif name == "_":
            return cls(
                name=name,
                var_type=MetavariableType.ANY,
            )
        elif name.startswith("..."):
            return cls(
                name=name[3:],
                var_type=MetavariableType.ELLIPSIS,
                is_ellipsis=True,
            )
        elif type_constraint:
            return cls(
                name=name,
                var_type=MetavariableType.TYPED,
                type_constraint=type_constraint,
            )
        else:
            # 이름 기반 타입 추론
            var_type = cls._infer_type(name)
            return cls(name=name, var_type=var_type)

    @staticmethod
    def _infer_type(name: str) -> MetavariableType:
        """이름에서 타입 추론"""
        name_upper = name.upper()

        if name_upper in ("FUNC", "FUNCTION", "FN"):
            return MetavariableType.FUNCTION
        elif name_upper in ("EXPR", "EXPRESSION"):
            return MetavariableType.EXPRESSION
        elif name_upper in ("STMT", "STATEMENT"):
            return MetavariableType.STATEMENT
        elif name_upper in ("STR", "STRING"):
            return MetavariableType.STRING
        elif name_upper in ("NUM", "NUMBER", "INT", "FLOAT"):
            return MetavariableType.NUMBER
        else:
            return MetavariableType.IDENTIFIER

    def matches_type(self, node_type: str) -> bool:
        """
        노드 타입이 메타변수 제약과 일치하는지 확인

        Args:
            node_type: AST 노드 타입

        Returns:
            일치 여부
        """
        if self.var_type == MetavariableType.ANY:
            return True

        if self.var_type == MetavariableType.ELLIPSIS:
            return True

        if self.type_constraint:
            return node_type == self.type_constraint

        # 타입별 허용 노드
        type_map: dict[MetavariableType, set[str]] = {
            MetavariableType.IDENTIFIER: {"identifier", "name", "variable"},
            MetavariableType.EXPRESSION: {
                "expression",
                "call",
                "binary_expression",
                "unary_expression",
                "attribute",
                "subscript",
            },
            MetavariableType.STATEMENT: {
                "statement",
                "expression_statement",
                "assignment",
                "if_statement",
                "for_statement",
                "while_statement",
            },
            MetavariableType.FUNCTION: {"identifier", "name", "function_name"},
            MetavariableType.STRING: {"string", "string_literal"},
            MetavariableType.NUMBER: {"number", "integer", "float"},
        }

        allowed = type_map.get(self.var_type, set())
        return node_type in allowed or not allowed


@dataclass
class MetavariableBinding:
    """
    메타변수 바인딩

    패턴 매칭 결과로 메타변수가 실제 코드에 바인딩된 결과.
    """

    metavar: Metavariable
    value: str
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0
    node_type: str = ""

    def __hash__(self) -> int:
        return hash((self.metavar.name, self.value))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MetavariableBinding):
            return False
        return self.metavar.name == other.metavar.name and self.value == other.value


@dataclass
class BindingSet:
    """
    메타변수 바인딩 집합

    하나의 패턴 매칭에서 발생한 모든 바인딩.
    """

    bindings: dict[str, MetavariableBinding] = field(default_factory=dict)

    def add(self, binding: MetavariableBinding) -> bool:
        """
        바인딩 추가

        같은 메타변수가 다른 값으로 바인딩되면 False 반환.

        Args:
            binding: 추가할 바인딩

        Returns:
            성공 여부
        """
        name = binding.metavar.name

        if name in self.bindings:
            # 같은 메타변수가 다른 값으로 바인딩되면 실패
            if self.bindings[name].value != binding.value:
                return False

        self.bindings[name] = binding
        return True

    def get(self, name: str) -> MetavariableBinding | None:
        """바인딩 조회"""
        return self.bindings.get(name)

    def to_dict(self) -> dict[str, str]:
        """dict로 변환"""
        return {name: b.value for name, b in self.bindings.items()}

    def merge(self, other: BindingSet) -> BindingSet | None:
        """
        두 바인딩 집합 병합

        충돌 시 None 반환.
        """
        result = BindingSet(bindings=dict(self.bindings))

        for binding in other.bindings.values():
            if not result.add(binding):
                return None

        return result


def extract_metavariables(pattern: str) -> list[Metavariable]:
    """
    패턴에서 모든 메타변수 추출

    Args:
        pattern: 패턴 문자열

    Returns:
        메타변수 목록
    """
    result: list[Metavariable] = []

    for match in Metavariable.PATTERN.finditer(pattern):
        metavar = Metavariable.parse(match.group(0))
        if metavar:
            result.append(metavar)

    return result
