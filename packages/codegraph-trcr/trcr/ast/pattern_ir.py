"""
AST Pattern IR

AST 패턴의 중간 표현.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

from trcr.ast.metavariable import BindingSet, Metavariable, extract_metavariables


class PatternNodeType(Enum):
    """패턴 노드 타입"""

    LITERAL = auto()  # 리터럴 문자열
    METAVAR = auto()  # 메타변수 ($VAR)
    CALL = auto()  # 함수 호출 (func($ARGS))
    ATTRIBUTE = auto()  # 속성 접근 (obj.attr)
    SEQUENCE = auto()  # 시퀀스
    ALTERNATIVE = auto()  # 대안 (|)


@dataclass
class PatternNode:
    """
    패턴 AST 노드

    패턴을 파싱한 결과의 트리 구조.
    """

    node_type: PatternNodeType
    value: str = ""
    metavar: Metavariable | None = None
    children: list[PatternNode] = field(default_factory=list)

    def is_metavar(self) -> bool:
        return self.node_type == PatternNodeType.METAVAR

    def is_literal(self) -> bool:
        return self.node_type == PatternNodeType.LITERAL


@dataclass
class ASTPatternIR:
    """
    AST 패턴 중간 표현

    Semgrep-style 패턴을 파싱하여 매칭에 사용할 수 있는 형태로 변환.

    Supported patterns:
        - cursor.execute($QUERY)
        - subprocess.call($..., shell=True)
        - eval($X)
        - $OBJ.read()
        - open($FILE, "w")
    """

    raw_pattern: str
    language: str
    root: PatternNode | None = None
    metavariables: list[Metavariable] = field(default_factory=list)

    # 매칭 힌트
    function_name: str = ""
    method_name: str = ""
    has_ellipsis: bool = False
    min_args: int = 0
    max_args: int = -1  # -1 means unlimited

    @classmethod
    def parse(cls, pattern: str, language: str = "python") -> ASTPatternIR:
        """
        패턴 문자열 파싱

        Args:
            pattern: Semgrep-style 패턴
            language: 대상 언어

        Returns:
            ASTPatternIR
        """
        metavars = extract_metavariables(pattern)

        ir = cls(
            raw_pattern=pattern,
            language=language,
            metavariables=metavars,
        )

        # 패턴 분석
        ir._analyze_pattern()
        ir.root = ir._parse_to_tree()

        return ir

    def _analyze_pattern(self) -> None:
        """패턴 분석하여 힌트 추출"""
        pattern = self.raw_pattern.strip()

        # 함수 호출 패턴 분석: func(...) 또는 obj.method(...)
        import re

        # obj.method($ARGS) 형태
        method_match = re.match(
            r"(\$?[A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            pattern,
        )
        if method_match:
            obj = method_match.group(1)
            self.method_name = method_match.group(2)
            if not obj.startswith("$"):
                self.function_name = obj

        # func($ARGS) 형태
        func_match = re.match(
            r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(",
            pattern,
        )
        if func_match and not method_match:
            self.function_name = func_match.group(1)

        # 인자 분석
        args_match = re.search(r"\(([^)]*)\)", pattern)
        if args_match:
            args_str = args_match.group(1)
            args = [a.strip() for a in args_str.split(",") if a.strip()]

            self.has_ellipsis = any("..." in a for a in args)
            non_ellipsis = [a for a in args if "..." not in a]
            self.min_args = len(non_ellipsis)

            if self.has_ellipsis:
                self.max_args = -1
            else:
                self.max_args = len(args)

    def _parse_to_tree(self) -> PatternNode:
        """패턴을 트리로 파싱"""
        pattern = self.raw_pattern.strip()

        # 함수 호출
        if "(" in pattern and pattern.endswith(")"):
            # func(args) 형태
            paren_idx = pattern.index("(")
            func_part = pattern[:paren_idx].strip()
            args_part = pattern[paren_idx + 1 : -1].strip()

            func_node = self._parse_expr(func_part)

            arg_nodes = []
            if args_part:
                for arg in self._split_args(args_part):
                    arg_nodes.append(self._parse_expr(arg.strip()))

            return PatternNode(
                node_type=PatternNodeType.CALL,
                value=func_part,
                children=[func_node] + arg_nodes,
            )

        return self._parse_expr(pattern)

    def _parse_expr(self, expr: str) -> PatternNode:
        """표현식 파싱"""
        expr = expr.strip()

        # 메타변수 체크
        metavar = Metavariable.parse(expr)
        if metavar and expr == f"${metavar.name}":
            return PatternNode(
                node_type=PatternNodeType.METAVAR,
                value=expr,
                metavar=metavar,
            )

        # 속성 접근
        if "." in expr and not expr.startswith("$"):
            parts = expr.split(".")
            if len(parts) == 2:
                return PatternNode(
                    node_type=PatternNodeType.ATTRIBUTE,
                    value=expr,
                    children=[
                        self._parse_expr(parts[0]),
                        PatternNode(
                            node_type=PatternNodeType.LITERAL,
                            value=parts[1],
                        ),
                    ],
                )

        # 리터럴
        return PatternNode(
            node_type=PatternNodeType.LITERAL,
            value=expr,
        )

    def _split_args(self, args_str: str) -> list[str]:
        """인자 문자열 분리 (괄호 고려)"""
        result = []
        current = ""
        depth = 0

        for char in args_str:
            if char == "(":
                depth += 1
                current += char
            elif char == ")":
                depth -= 1
                current += char
            elif char == "," and depth == 0:
                result.append(current)
                current = ""
            else:
                current += char

        if current:
            result.append(current)

        return result


@dataclass
class PatternMatch:
    """
    패턴 매칭 결과

    코드에서 패턴이 매칭된 위치와 바인딩 정보.
    """

    pattern: ASTPatternIR
    matched_code: str
    start_line: int
    end_line: int
    start_col: int = 0
    end_col: int = 0
    bindings: BindingSet = field(default_factory=BindingSet)
    confidence: float = 1.0

    def get_binding(self, name: str) -> str | None:
        """메타변수 바인딩 값 조회"""
        binding = self.bindings.get(name)
        return binding.value if binding else None

    def to_dict(self) -> dict[str, Any]:
        """dict로 변환"""
        return {
            "pattern": self.pattern.raw_pattern,
            "matched_code": self.matched_code,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "bindings": self.bindings.to_dict(),
            "confidence": self.confidence,
        }
