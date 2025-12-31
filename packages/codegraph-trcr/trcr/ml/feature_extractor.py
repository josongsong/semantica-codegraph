"""
Feature Extractor for ML FP Filter

취약점 매치에서 머신러닝 피처를 추출합니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Match(Protocol):
    """매치 결과 프로토콜"""

    line: int
    specificity: float
    confidence: float
    tier: int
    rule_id: str


@dataclass
class MatchFeatures:
    """추출된 피처"""

    # 규칙 메타데이터 피처
    rule_specificity: float = 0.0  # 0.0 ~ 1.0
    rule_confidence: float = 0.0  # 0.0 ~ 1.0
    rule_tier: int = 3  # 1, 2, 3

    # 코드 컨텍스트 피처
    in_try_block: bool = False
    in_test_file: bool = False
    in_comment: bool = False
    has_guard_before: bool = False
    has_sanitizer_before: bool = False

    # 패턴 피처
    is_exact_match: bool = False
    is_regex_match: bool = False
    match_line_count: int = 1

    # 히스토리 피처
    rule_fp_rate: float = 0.0  # 이 규칙의 FP율
    file_fp_rate: float = 0.0  # 이 파일의 FP율

    # 코드 복잡도 피처
    function_complexity: int = 0  # Cyclomatic complexity
    function_line_count: int = 0
    nesting_depth: int = 0

    def to_vector(self) -> list[float]:
        """ML 모델용 벡터 변환"""
        return [
            self.rule_specificity,
            self.rule_confidence,
            float(self.rule_tier) / 3.0,
            float(self.in_try_block),
            float(self.in_test_file),
            float(self.in_comment),
            float(self.has_guard_before),
            float(self.has_sanitizer_before),
            float(self.is_exact_match),
            float(self.is_regex_match),
            min(self.match_line_count / 10.0, 1.0),
            self.rule_fp_rate,
            self.file_fp_rate,
            min(self.function_complexity / 20.0, 1.0),
            min(self.function_line_count / 100.0, 1.0),
            min(self.nesting_depth / 5.0, 1.0),
        ]

    @property
    def feature_names(self) -> list[str]:
        """피처 이름 목록"""
        return [
            "rule_specificity",
            "rule_confidence",
            "rule_tier_norm",
            "in_try_block",
            "in_test_file",
            "in_comment",
            "has_guard_before",
            "has_sanitizer_before",
            "is_exact_match",
            "is_regex_match",
            "match_line_count_norm",
            "rule_fp_rate",
            "file_fp_rate",
            "function_complexity_norm",
            "function_line_count_norm",
            "nesting_depth_norm",
        ]


class FeatureExtractor:
    """피처 추출기"""

    # 테스트 파일 패턴
    TEST_FILE_PATTERNS = [
        r"test_.*\.py$",
        r".*_test\.py$",
        r"tests?/.*\.py$",
        r".*\.test\.[jt]s$",
        r".*\.spec\.[jt]s$",
        r".*Test\.java$",
        r".*_test\.go$",
    ]

    # 가드 패턴 (보안 검사)
    GUARD_PATTERNS = [
        r"if\s+not\s+.*:",  # Python
        r"if\s+.*\s*==\s*None:",  # null check
        r"if\s+len\s*\(",  # length check
        r"if\s+isinstance\s*\(",  # type check
        r"if\s*\(\s*!",  # JS/Java negation
        r"if\s*\(\s*\w+\s*===?\s*null",  # JS null check
    ]

    # 새니타이저 패턴
    SANITIZER_PATTERNS = [
        r"escape\s*\(",
        r"sanitize\s*\(",
        r"clean\s*\(",
        r"validate\s*\(",
        r"filter\s*\(",
        r"quote\s*\(",
        r"html\.escape\s*\(",
        r"markupsafe\.escape\s*\(",
    ]

    def __init__(
        self,
        fp_history: dict[str, float] | None = None,
        file_fp_history: dict[str, float] | None = None,
    ) -> None:
        self.fp_history = fp_history or {}
        self.file_fp_history = file_fp_history or {}

    def extract(
        self,
        match: Match,
        code: str,
        file_path: str,
    ) -> MatchFeatures:
        """
        매치에서 피처 추출

        Args:
            match: 취약점 매치 결과
            code: 전체 소스 코드
            file_path: 파일 경로

        Returns:
            MatchFeatures: 추출된 피처
        """
        features = MatchFeatures()

        # 규칙 메타데이터
        features.rule_specificity = getattr(match, "specificity", 0.5)
        features.rule_confidence = getattr(match, "confidence", 0.5)
        features.rule_tier = getattr(match, "tier", 2)

        # 코드 컨텍스트
        match_line = getattr(match, "line", 0)
        lines = code.split("\n")

        if match_line > 0 and match_line <= len(lines):
            # Try 블록 체크
            features.in_try_block = self._is_in_try_block(lines, match_line)

            # 가드/새니타이저 체크
            features.has_guard_before = self._has_pattern_before(lines, match_line, self.GUARD_PATTERNS)
            features.has_sanitizer_before = self._has_pattern_before(lines, match_line, self.SANITIZER_PATTERNS)

            # 주석 체크
            features.in_comment = self._is_in_comment(lines[match_line - 1])

            # 중첩 깊이
            features.nesting_depth = self._get_nesting_depth(lines, match_line)

        # 테스트 파일 체크
        features.in_test_file = self._is_test_file(file_path)

        # 히스토리
        rule_id = getattr(match, "rule_id", "")
        features.rule_fp_rate = self.fp_history.get(rule_id, 0.0)
        features.file_fp_rate = self.file_fp_history.get(file_path, 0.0)

        # 함수 복잡도
        features.function_complexity = self._estimate_complexity(code)
        features.function_line_count = len(lines)

        return features

    def extract_from_dict(
        self,
        match_data: dict[str, Any],
        code: str,
        file_path: str,
    ) -> MatchFeatures:
        """딕셔너리에서 피처 추출"""

        class DictMatch:
            def __init__(self, data: dict[str, Any]) -> None:
                for k, v in data.items():
                    setattr(self, k, v)

        return self.extract(DictMatch(match_data), code, file_path)

    def _is_in_try_block(self, lines: list[str], line_no: int) -> bool:
        """Try 블록 내부인지 확인"""
        # 위로 올라가면서 try 찾기
        indent = self._get_indent(lines[line_no - 1])

        for i in range(line_no - 2, max(0, line_no - 20), -1):
            line = lines[i]
            if not line.strip():
                continue

            line_indent = self._get_indent(line)
            if line_indent < indent and "try:" in line:
                return True
            if line_indent <= indent and "try" not in line:
                break

        return False

    def _has_pattern_before(
        self,
        lines: list[str],
        line_no: int,
        patterns: list[str],
    ) -> bool:
        """이전 라인에 패턴이 있는지"""
        check_range = min(10, line_no - 1)

        for i in range(line_no - 2, line_no - 2 - check_range, -1):
            if i < 0:
                break

            line = lines[i]
            for pattern in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    return True

        return False

    def _is_in_comment(self, line: str) -> bool:
        """라인이 주석인지"""
        stripped = line.strip()
        return stripped.startswith("#") or stripped.startswith("//")

    def _is_test_file(self, file_path: str) -> bool:
        """테스트 파일인지"""
        return any(re.search(pattern, file_path) for pattern in self.TEST_FILE_PATTERNS)

    def _get_nesting_depth(self, lines: list[str], line_no: int) -> int:
        """중첩 깊이 계산"""
        if line_no <= 0 or line_no > len(lines):
            return 0

        indent = self._get_indent(lines[line_no - 1])
        # 4 spaces = 1 level (일반적인 규칙)
        return indent // 4

    def _get_indent(self, line: str) -> int:
        """라인 들여쓰기"""
        return len(line) - len(line.lstrip())

    def _estimate_complexity(self, code: str) -> int:
        """순환 복잡도 추정 (간단 버전)"""
        # if, for, while, try, except 등 카운트
        complexity_keywords = [
            r"\bif\b",
            r"\bfor\b",
            r"\bwhile\b",
            r"\btry\b",
            r"\bexcept\b",
            r"\bcase\b",
            r"\bcatch\b",
            r"\?",  # ternary
        ]

        count = 1  # 기본 복잡도
        for pattern in complexity_keywords:
            count += len(re.findall(pattern, code))

        return min(count, 50)  # 상한
