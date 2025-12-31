"""
Constitution

안전성 및 품질 규칙 정의.
"""

from collections.abc import Callable
from dataclasses import dataclass

from .constitutional_models import RuleSeverity


@dataclass
class Rule:
    """규칙"""

    rule_id: str
    name: str
    description: str
    severity: RuleSeverity
    check_fn: Callable[[str], bool]  # True = 위반


class Constitution:
    """헌법 (규칙 모음)"""

    def __init__(self):
        self.rules: list[Rule] = []
        self._initialize_default_rules()

    def _initialize_default_rules(self) -> None:
        """기본 규칙 초기화"""

        # 보안 규칙 (개선: 실제 하드코딩만 탐지)
        def check_hardcoded_secrets(content: str) -> bool:
            """하드코딩된 비밀 탐지 (환경변수는 제외)"""
            # os.getenv, os.environ 사용은 안전
            if "os.getenv" in content or "os.environ" in content:
                return False

            # 실제 하드코딩된 값 (= "..." 또는 = '...' 패턴)
            patterns = [
                'password = "',
                "password = '",
                'api_key = "',
                "api_key = '",
                'secret = "',
                "secret = '",
                'admin_password = "',
                "admin_password = '",
                'secret_key = "',
                "secret_key = '",
            ]
            return any(pattern in content.lower() for pattern in patterns)

        self.add_rule(
            Rule(
                rule_id="SEC-001",
                name="No hardcoded secrets",
                description="코드에 하드코딩된 비밀번호/토큰 금지",
                severity=RuleSeverity.CRITICAL,
                check_fn=check_hardcoded_secrets,
            )
        )

        # SQL injection 탐지 (개선: 다양한 패턴 커버)
        def check_sql_injection(content: str) -> bool:
            """SQL injection 취약점 탐지"""
            content_lower = content.lower()

            # SQL 키워드
            sql_keywords = ["select", "insert", "update", "delete", "drop", "create"]
            has_sql = any(keyword in content_lower for keyword in sql_keywords)

            if not has_sql:
                return False

            # 위험 패턴들
            dangerous_patterns = [
                # 문자열 연결 (+)
                (
                    "+" in content
                    and ("select" in content_lower or "delete" in content_lower or "update" in content_lower)
                ),
                # f-string으로 SQL 생성
                ("f'" in content or 'f"' in content) and has_sql,
                # .format()으로 SQL 생성
                (".format(" in content and has_sql),
                # % formatting
                ("%" in content and "(" in content and has_sql),
            ]

            return any(dangerous_patterns)

        self.add_rule(
            Rule(
                rule_id="SEC-002",
                name="No SQL injection",
                description="SQL injection 취약점 금지 (문자열 연결, f-string, format 등)",
                severity=RuleSeverity.CRITICAL,
                check_fn=check_sql_injection,
            )
        )

        # 품질 규칙
        self.add_rule(
            Rule(
                rule_id="QUAL-001",
                name="No excessive complexity",
                description="과도한 복잡도 금지 (함수 100줄 이상)",
                severity=RuleSeverity.WARNING,
                check_fn=lambda content: content.count("\n") > 100,
            )
        )

        self.add_rule(
            Rule(
                rule_id="QUAL-002",
                name="No print statements",
                description="print() 사용 금지 (로거 사용 권장)",
                severity=RuleSeverity.INFO,
                check_fn=lambda content: "print(" in content,
            )
        )

        # 스타일 규칙
        self.add_rule(
            Rule(
                rule_id="STYLE-001",
                name="No TODO comments",
                description="TODO 주석은 이슈로 등록 필요",
                severity=RuleSeverity.INFO,
                check_fn=lambda content: "TODO" in content.upper(),
            )
        )

    def add_rule(self, rule: Rule) -> None:
        """
        규칙 추가

        Args:
            rule: 규칙
        """
        self.rules.append(rule)

    def get_rules(self) -> list[Rule]:
        """
        모든 규칙 반환

        Returns:
            규칙 리스트
        """
        return self.rules

    def get_rules_by_severity(self, severity: RuleSeverity) -> list[Rule]:
        """
        심각도별 규칙 반환

        Args:
            severity: 심각도

        Returns:
            규칙 리스트
        """
        return [r for r in self.rules if r.severity == severity]
