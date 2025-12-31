"""
Rule Validator for LLM-generated rules

생성된 규칙의 유효성을 검증하고 품질을 평가합니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import yaml


class ValidationSeverity(str, Enum):
    """검증 결과 심각도"""

    ERROR = "error"  # 사용 불가
    WARNING = "warning"  # 사용 가능하나 개선 필요
    INFO = "info"  # 참고 사항


@dataclass
class ValidationIssue:
    """검증 이슈"""

    severity: ValidationSeverity
    code: str
    message: str
    location: str = ""
    suggestion: str = ""


@dataclass
class ValidationResult:
    """검증 결과"""

    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    quality_score: float = 0.0  # 0.0 ~ 1.0

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    def add_error(self, code: str, message: str, **kwargs: str) -> None:
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.ERROR,
                code=code,
                message=message,
                **kwargs,
            )
        )
        self.is_valid = False

    def add_warning(self, code: str, message: str, **kwargs: str) -> None:
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.WARNING,
                code=code,
                message=message,
                **kwargs,
            )
        )

    def add_info(self, code: str, message: str, **kwargs: str) -> None:
        self.issues.append(
            ValidationIssue(
                severity=ValidationSeverity.INFO,
                code=code,
                message=message,
                **kwargs,
            )
        )


class RuleValidator:
    """규칙 검증기"""

    # 유효한 kind 값
    VALID_KINDS = {"source", "sink", "sanitizer", "propagator", "passthrough"}

    # 유효한 severity 값
    VALID_SEVERITIES = {"critical", "high", "medium", "low"}

    # ID 패턴
    ID_PATTERN = re.compile(r"^[a-z][a-z0-9._-]*$")

    # CWE 패턴
    CWE_PATTERN = re.compile(r"^cwe-\d+$", re.IGNORECASE)

    # Tier 패턴
    TIER_PATTERN = re.compile(r"^tier:[1-4]$")

    def validate_yaml(self, yaml_text: str) -> tuple[ValidationResult, list[dict[str, Any]]]:
        """YAML 텍스트 검증 및 파싱"""
        result = ValidationResult(is_valid=True)
        rules: list[dict[str, Any]] = []

        # YAML 파싱
        try:
            parsed = yaml.safe_load(yaml_text)
        except yaml.YAMLError as e:
            result.add_error(
                code="YAML_PARSE_ERROR",
                message=f"YAML 파싱 실패: {e}",
            )
            return result, rules

        # 리스트 형태 확인
        if not isinstance(parsed, list):
            result.add_error(
                code="NOT_A_LIST",
                message="규칙은 리스트 형태여야 합니다",
            )
            return result, rules

        # 각 규칙 검증
        for i, rule in enumerate(parsed):
            if not isinstance(rule, dict):
                result.add_error(
                    code="INVALID_RULE_TYPE",
                    message=f"규칙 {i}: dict 타입이어야 합니다",
                    location=f"rules[{i}]",
                )
                continue

            rule_result = self._validate_rule(rule, i)
            result.issues.extend(rule_result.issues)
            if not rule_result.is_valid:
                result.is_valid = False
            else:
                rules.append(rule)

        # 품질 점수 계산
        if rules:
            result.quality_score = self._calculate_quality_score(rules, result)

        return result, rules

    def _validate_rule(self, rule: dict[str, Any], index: int) -> ValidationResult:
        """개별 규칙 검증"""
        result = ValidationResult(is_valid=True)
        location = f"rules[{index}]"

        # 필수 필드 확인 - id 또는 rule_id
        rule_id = rule.get("id") or rule.get("rule_id")
        if not rule_id:
            result.add_error(
                code="MISSING_ID",
                message="id 또는 rule_id 필드 필수",
                location=location,
            )

        if "match" not in rule:
            result.add_error(
                code="MISSING_MATCH",
                message="match 필드 필수",
                location=location,
            )

        # ID 형식 검증
        if rule_id:
            if not isinstance(rule_id, str):
                result.add_error(
                    code="INVALID_ID_TYPE",
                    message="id는 문자열이어야 합니다",
                    location=location,
                )
            elif not self.ID_PATTERN.match(rule_id):
                result.add_warning(
                    code="INVALID_ID_FORMAT",
                    message=f"ID 형식 권장: {rule_id}",
                    location=location,
                    suggestion="lowercase, dots, dashes만 사용",
                )

        # Kind 검증
        if "kind" in rule:
            if rule["kind"] not in self.VALID_KINDS:
                result.add_error(
                    code="INVALID_KIND",
                    message=f"유효하지 않은 kind: {rule['kind']}",
                    location=location,
                    suggestion=f"유효값: {self.VALID_KINDS}",
                )

        # Severity 검증
        if "severity" in rule:
            if rule["severity"] not in self.VALID_SEVERITIES:
                result.add_warning(
                    code="INVALID_SEVERITY",
                    message=f"유효하지 않은 severity: {rule['severity']}",
                    location=location,
                    suggestion=f"유효값: {self.VALID_SEVERITIES}",
                )

        # Tags 검증
        if "tags" in rule:
            if not isinstance(rule["tags"], list):
                result.add_error(
                    code="INVALID_TAGS_TYPE",
                    message="tags는 리스트여야 합니다",
                    location=location,
                )

        # Match 검증
        if "match" in rule:
            match = rule["match"]
            if not isinstance(match, list):
                result.add_error(
                    code="INVALID_MATCH_TYPE",
                    message="match는 리스트여야 합니다",
                    location=location,
                )
            elif not match:
                result.add_error(
                    code="EMPTY_MATCH",
                    message="match 리스트가 비어있습니다",
                    location=location,
                )
            else:
                for j, clause in enumerate(match):
                    if not isinstance(clause, dict):
                        result.add_error(
                            code="INVALID_CLAUSE_TYPE",
                            message=f"match[{j}]는 dict여야 합니다",
                            location=f"{location}.match[{j}]",
                        )
                    else:
                        # 최소한 하나의 매칭 필드 필요
                        has_matcher = any(
                            [
                                clause.get("call"),
                                clause.get("call_pattern"),
                                clause.get("base_type"),
                                clause.get("base_type_pattern"),
                                clause.get("read"),
                                clause.get("type"),  # LLM이 생성할 수 있는 형태
                            ]
                        )
                        if not has_matcher:
                            result.add_error(
                                code="MISSING_MATCHER",
                                message="call, base_type, 또는 read 필드 필요",
                                location=f"{location}.match[{j}]",
                            )

        return result

    def _calculate_quality_score(
        self,
        rules: list[dict[str, Any]],
        result: ValidationResult,
    ) -> float:
        """품질 점수 계산 (0.0 ~ 1.0)"""
        if not rules:
            return 0.0

        total_score = 0.0

        for rule in rules:
            score = 1.0

            # ID 형식 (-0.1)
            rule_id = rule.get("id") or rule.get("rule_id") or ""
            if not self.ID_PATTERN.match(rule_id):
                score -= 0.1

            # Tags 유무 (-0.1 each)
            tags = rule.get("tags", [])
            if not any(self.CWE_PATTERN.match(str(t)) for t in tags):
                score -= 0.1
            if not any(self.TIER_PATTERN.match(str(t)) for t in tags):
                score -= 0.1

            # Severity 유무 (-0.1)
            if "severity" not in rule:
                score -= 0.1

            # Kind 유무 (-0.2)
            if "kind" not in rule:
                score -= 0.2

            total_score += max(0.0, score)

        # Warning 페널티
        warning_penalty = len(result.warnings) * 0.02

        return max(0.0, (total_score / len(rules)) - warning_penalty)
