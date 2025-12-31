"""
AST Pattern Matcher

Semgrep-style AST 패턴 매칭 엔진.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from trcr.ast.metavariable import (
    BindingSet,
    Metavariable,
    MetavariableBinding,
)
from trcr.ast.pattern_ir import ASTPatternIR, PatternMatch


class ASTParser(Protocol):
    """AST 파서 프로토콜"""

    def parse(self, code: str, language: str) -> list[dict]: ...


@dataclass
class MatcherConfig:
    """매처 설정"""

    case_sensitive: bool = True
    allow_partial_match: bool = False
    max_matches: int = 1000


class ASTPatternMatcher:
    """
    AST 패턴 매처

    Semgrep-style 패턴으로 코드 매칭.

    tree-sitter가 없는 환경에서도 정규식 기반 폴백 제공.

    Usage:
        >>> matcher = ASTPatternMatcher()
        >>> matches = matcher.match(
        ...     "cursor.execute($QUERY)",
        ...     "cursor.execute(user_input)",
        ...     "python"
        ... )
        >>> matches[0].get_binding("QUERY")
        'user_input'
    """

    def __init__(
        self,
        config: MatcherConfig | None = None,
        parser: ASTParser | None = None,
    ) -> None:
        self.config = config or MatcherConfig()
        self._parser = parser
        self._pattern_cache: dict[str, ASTPatternIR] = {}

    def match(
        self,
        pattern: str,
        code: str,
        language: str = "python",
    ) -> list[PatternMatch]:
        """
        패턴 매칭 수행

        Args:
            pattern: Semgrep-style 패턴
            code: 대상 코드
            language: 언어

        Returns:
            매칭 결과 목록
        """
        # 패턴 파싱 (캐시)
        cache_key = f"{language}:{pattern}"
        if cache_key not in self._pattern_cache:
            self._pattern_cache[cache_key] = ASTPatternIR.parse(pattern, language)

        pattern_ir = self._pattern_cache[cache_key]

        # tree-sitter 사용 가능하면 AST 기반 매칭
        if self._parser:
            return self._match_with_ast(pattern_ir, code)

        # 폴백: 정규식 기반 매칭
        return self._match_with_regex(pattern_ir, code)

    def compile_pattern(self, pattern: str, language: str = "python") -> ASTPatternIR:
        """
        패턴 컴파일

        Args:
            pattern: 패턴 문자열
            language: 언어

        Returns:
            컴파일된 패턴 IR
        """
        return ASTPatternIR.parse(pattern, language)

    def match_compiled(
        self,
        pattern_ir: ASTPatternIR,
        code: str,
    ) -> list[PatternMatch]:
        """
        컴파일된 패턴으로 매칭

        Args:
            pattern_ir: 컴파일된 패턴
            code: 대상 코드

        Returns:
            매칭 결과 목록
        """
        if self._parser:
            return self._match_with_ast(pattern_ir, code)
        return self._match_with_regex(pattern_ir, code)

    # =========================================================================
    # Regex-based Matching (Fallback)
    # =========================================================================

    def _match_with_regex(
        self,
        pattern_ir: ASTPatternIR,
        code: str,
    ) -> list[PatternMatch]:
        """정규식 기반 매칭"""
        regex = self._pattern_to_regex(pattern_ir)

        matches: list[PatternMatch] = []
        lines = code.split("\n")

        for line_no, line in enumerate(lines, 1):
            for m in regex.finditer(line):
                bindings = self._extract_bindings(pattern_ir, m, line_no)

                match = PatternMatch(
                    pattern=pattern_ir,
                    matched_code=m.group(0),
                    start_line=line_no,
                    end_line=line_no,
                    start_col=m.start(),
                    end_col=m.end(),
                    bindings=bindings,
                )
                matches.append(match)

                if len(matches) >= self.config.max_matches:
                    return matches

        return matches

    def _pattern_to_regex(self, pattern_ir: ASTPatternIR) -> re.Pattern:
        """패턴을 정규식으로 변환"""
        pattern = pattern_ir.raw_pattern

        # 특수문자 이스케이프 (메타변수 제외)
        result = ""
        i = 0

        while i < len(pattern):
            char = pattern[i]

            if char == "$":
                # 메타변수 처리
                metavar_match = Metavariable.PATTERN.match(pattern[i:])
                if metavar_match:
                    metavar_str = metavar_match.group(0)
                    metavar = Metavariable.parse(metavar_str)

                    if metavar:
                        if metavar.is_ellipsis:
                            # $... 또는 $...ARGS
                            result += r"(?P<" + self._safe_group_name(metavar.name) + r">.*?)"
                        else:
                            # 일반 메타변수
                            result += (
                                r"(?P<"
                                + self._safe_group_name(metavar.name)
                                + r">[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*|\"[^\"]*\"|\'[^\']*\'|\d+)"
                            )

                        i += len(metavar_str)
                        continue

            # 특수문자 이스케이프
            if char in r"\.^$*+?{}[]|()":
                result += "\\" + char
            else:
                result += char

            i += 1

        # 공백 유연하게
        result = re.sub(r"\s+", r"\\s*", result)

        flags = 0 if self.config.case_sensitive else re.IGNORECASE

        return re.compile(result, flags)

    def _safe_group_name(self, name: str) -> str:
        """정규식 그룹 이름으로 사용할 수 있게 변환"""
        # ...을 ellipsis로 변환
        if name == "...":
            return "ellipsis"
        # 시작이 숫자인 경우 처리
        if name[0].isdigit():
            return f"var_{name}"
        return name

    def _extract_bindings(
        self,
        pattern_ir: ASTPatternIR,
        match: re.Match,
        line_no: int,
    ) -> BindingSet:
        """정규식 매치에서 바인딩 추출"""
        bindings = BindingSet()

        for metavar in pattern_ir.metavariables:
            group_name = self._safe_group_name(metavar.name)

            try:
                value = match.group(group_name)
                if value:
                    binding = MetavariableBinding(
                        metavar=metavar,
                        value=value,
                        start_line=line_no,
                        end_line=line_no,
                        start_col=match.start(group_name),
                        end_col=match.end(group_name),
                    )
                    bindings.add(binding)
            except IndexError:
                pass

        return bindings

    # =========================================================================
    # AST-based Matching (with tree-sitter)
    # =========================================================================

    def _match_with_ast(
        self,
        pattern_ir: ASTPatternIR,
        code: str,
    ) -> list[PatternMatch]:
        """AST 기반 매칭 (tree-sitter 필요)"""
        if not self._parser:
            return self._match_with_regex(pattern_ir, code)

        # TODO: tree-sitter 기반 구현
        # 현재는 정규식 폴백 사용
        return self._match_with_regex(pattern_ir, code)


def quick_match(pattern: str, code: str, language: str = "python") -> list[dict]:
    """
    빠른 패턴 매칭 (편의 함수)

    Args:
        pattern: 패턴
        code: 코드
        language: 언어

    Returns:
        매칭 결과 (dict 형태)
    """
    matcher = ASTPatternMatcher()
    matches = matcher.match(pattern, code, language)
    return [m.to_dict() for m in matches]
