"""
Trace Tools (RFC-041)

실행/데이터 흐름 추적을 위한 Step Tools.

SOTA References:
- Infer: Points-to Analysis (Facebook)
- CodeQL: Alias Analysis
- Semgrep: Entry Point Detection
"""

from dataclasses import dataclass, field
from typing import Any

from codegraph_shared.common.observability import get_logger
from codegraph_engine.shared_kernel.contracts.levels import RiskLevel

from .base import QueryDSLMixin, StepTool, StepToolResult
from .entry_types import EntryPointType

logger = get_logger(__name__)


# ================================================================
# Data Models
# ================================================================


@dataclass
class AliasInfo:
    """Alias 정보"""

    variable: str
    aliases: list[str]
    alias_type: str  # "must", "may"
    confidence: float
    source_locations: list[dict[str, Any]]


@dataclass
class EntryPoint:
    """진입점 정보"""

    name: str
    file_path: str
    line: int
    entry_type: EntryPointType
    route: str | None  # HTTP route if applicable
    method: str | None  # HTTP method if applicable
    parameters: list[dict[str, Any]]
    is_authenticated: bool
    risk_level: RiskLevel


# ================================================================
# Tools
# ================================================================


class TraceAliasTool(StepTool, QueryDSLMixin):
    """
    Alias 추적 Tool

    SOTA: Infer/CodeQL의 Points-to Analysis

    분석 내용:
    - 변수의 별칭(alias) 관계 추적
    - Must-alias vs May-alias 구분
    - 포인터/참조 분석
    """

    @property
    def name(self) -> str:
        return "trace_alias"

    @property
    def description(self) -> str:
        return "변수의 별칭(alias) 관계를 추적합니다"

    def __init__(self, ir_analyzer: Any = None, points_to_analyzer: Any = None):
        self.ir_analyzer = ir_analyzer
        self.points_to_analyzer = points_to_analyzer

    def execute(
        self,
        target: str = "",
        from_find_data_dependency: Any = None,
        **kwargs,
    ) -> StepToolResult:
        """
        Alias 추적

        Args:
            target: 추적할 변수명
            from_find_data_dependency: 이전 Step 결과
        """
        if not target:
            return StepToolResult(success=False, error="No target variable provided")

        try:
            # Points-to 분석기 사용
            if self.points_to_analyzer:
                return self._analyze_with_points_to(target)

            # Fallback: 데이터 의존성 기반 추론
            if from_find_data_dependency:
                return self._infer_from_data_dependency(target, from_find_data_dependency)

            # 최소한의 분석: 직접 할당 추적
            return self._simple_alias_tracking(target)

        except Exception as e:
            logger.exception("Alias tracking failed")
            return StepToolResult(success=False, error=str(e))

    def _analyze_with_points_to(self, target: str) -> StepToolResult:
        """Points-to 분석기 사용"""
        try:
            # Points-to 분석 실행
            result = self.points_to_analyzer.analyze(target)

            aliases: list[AliasInfo] = []

            # Must-alias
            for alias in result.get("must_aliases", []):
                aliases.append(
                    AliasInfo(
                        variable=target,
                        aliases=[alias],
                        alias_type="must",
                        confidence=0.95,
                        source_locations=result.get("locations", {}).get(alias, []),
                    )
                )

            # May-alias
            for alias in result.get("may_aliases", []):
                aliases.append(
                    AliasInfo(
                        variable=target,
                        aliases=[alias],
                        alias_type="may",
                        confidence=0.7,
                        source_locations=result.get("locations", {}).get(alias, []),
                    )
                )

            return StepToolResult(
                success=True,
                data={
                    "variable": target,
                    "must_aliases": [a.aliases[0] for a in aliases if a.alias_type == "must"],
                    "may_aliases": [a.aliases[0] for a in aliases if a.alias_type == "may"],
                    "total_aliases": len(aliases),
                    "details": [
                        {
                            "alias": a.aliases[0],
                            "type": a.alias_type,
                            "confidence": a.confidence,
                            "locations": a.source_locations[:3],
                        }
                        for a in aliases
                    ],
                },
                confidence=0.9,
            )

        except Exception as e:
            logger.warning(f"Points-to analysis failed: {e}")
            return self._simple_alias_tracking(target)

    def _infer_from_data_dependency(self, target: str, dep_data: Any) -> StepToolResult:
        """데이터 의존성에서 alias 추론"""
        dependencies = dep_data.get("dependencies", [])

        aliases: list[str] = []
        may_aliases: list[str] = []

        for dep in dependencies:
            # 직접 할당 패턴: x = y
            if " = " in dep or " := " in dep:
                # 우변에서 변수 추출
                parts = dep.replace(":=", "=").split("=")
                if len(parts) == 2:
                    rhs = parts[1].strip()
                    # 단순 변수 할당
                    if rhs.isidentifier():
                        aliases.append(rhs)
                    # 표현식의 경우 may-alias
                    elif target in rhs:
                        may_aliases.append(f"expr_{len(may_aliases)}")

        return StepToolResult(
            success=True,
            data={
                "variable": target,
                "must_aliases": list(set(aliases)),
                "may_aliases": list(set(may_aliases)),
                "total_aliases": len(aliases) + len(may_aliases),
                "inference_method": "data_dependency",
            },
            confidence=0.7,
        )

    def _simple_alias_tracking(self, target: str) -> StepToolResult:
        """간단한 alias 추적 (Fallback)"""
        return StepToolResult(
            success=True,
            data={
                "variable": target,
                "must_aliases": [],
                "may_aliases": [],
                "total_aliases": 0,
                "note": "Points-to analysis not available. Run full IR analysis for accurate alias tracking.",
            },
            confidence=0.5,
        )


class FindEntryPointsTool(StepTool):
    """
    진입점 탐지 Tool

    SOTA: Semgrep/CodeQL의 Entry Point Detection

    탐지 대상:
    - HTTP Endpoints (Flask, Django, FastAPI, Express)
    - CLI Commands
    - Main functions
    - Event handlers
    - Test functions
    """

    @property
    def name(self) -> str:
        return "find_entry_points"

    @property
    def description(self) -> str:
        return "코드의 진입점(HTTP endpoint, main, CLI 등)을 찾습니다"

    def __init__(self, ir_analyzer: Any = None):
        self.ir_analyzer = ir_analyzer

        # 프레임워크별 패턴
        self.http_patterns = {
            # Flask
            "flask": [
                r"@app\.route\(['\"]([^'\"]+)['\"]\s*(?:,\s*methods=\[([^\]]+)\])?",
                r"@blueprint\.route\(['\"]([^'\"]+)['\"]",
            ],
            # Django
            "django": [
                r"path\(['\"]([^'\"]+)['\"]",
                r"re_path\(['\"]([^'\"]+)['\"]",
            ],
            # FastAPI
            "fastapi": [
                r"@app\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]",
                r"@router\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]",
            ],
        }

        self.cli_patterns = [
            r"@click\.command\(\)",
            r"@app\.command\(\)",
            r"argparse\.ArgumentParser",
            r"if __name__ == ['\"]__main__['\"]",
        ]

        self.event_patterns = [
            r"@on_event\(['\"]([^'\"]+)['\"]",
            r"\.on\(['\"]([^'\"]+)['\"]",
            r"addEventListener\(['\"]([^'\"]+)['\"]",
        ]

    def execute(
        self,
        target: str = "",
        **kwargs,
    ) -> StepToolResult:
        """
        진입점 탐지

        Args:
            target: 분석 대상 파일/디렉토리
        """
        if not target:
            return StepToolResult(success=False, error="No target path provided")

        try:
            import os
            import re

            entry_points: list[EntryPoint] = []

            # 파일 목록 수집
            files_to_scan: list[str] = []
            if os.path.isdir(target):
                for root, _, files in os.walk(target):
                    for f in files:
                        if f.endswith((".py", ".ts", ".js")):
                            files_to_scan.append(os.path.join(root, f))
            else:
                files_to_scan = [target]

            # 각 파일 스캔
            for file_path in files_to_scan[:100]:  # 최대 100개
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        lines = content.splitlines()

                    # HTTP Endpoints
                    for framework, patterns in self.http_patterns.items():
                        for pattern in patterns:
                            for match in re.finditer(pattern, content):
                                line_num = content[: match.start()].count("\n") + 1
                                entry = self._create_http_entry_point(file_path, line_num, match, framework, lines)
                                if entry:
                                    entry_points.append(entry)

                    # CLI Commands
                    for pattern in self.cli_patterns:
                        for match in re.finditer(pattern, content):
                            line_num = content[: match.start()].count("\n") + 1
                            entry = self._create_cli_entry_point(file_path, line_num, lines)
                            if entry:
                                entry_points.append(entry)

                    # Main functions
                    main_entry = self._find_main_function(file_path, content, lines)
                    if main_entry:
                        entry_points.append(main_entry)

                    # Test functions
                    test_entries = self._find_test_functions(file_path, content, lines)
                    entry_points.extend(test_entries)

                except Exception as e:
                    logger.warning(f"Failed to scan {file_path}: {e}")

            # 위험도별 분류
            high_risk = [e for e in entry_points if e.risk_level == RiskLevel.HIGH]
            medium_risk = [e for e in entry_points if e.risk_level == RiskLevel.MEDIUM]

            return StepToolResult(
                success=True,
                data={
                    "total_entry_points": len(entry_points),
                    "by_type": {
                        "http_endpoint": len([e for e in entry_points if e.entry_type == EntryPointType.HTTP_ENDPOINT]),
                        "cli_command": len([e for e in entry_points if e.entry_type == EntryPointType.CLI_COMMAND]),
                        "main": len([e for e in entry_points if e.entry_type == EntryPointType.MAIN]),
                        "test": len([e for e in entry_points if e.entry_type == EntryPointType.TEST]),
                        "event_handler": len([e for e in entry_points if e.entry_type == EntryPointType.EVENT_HANDLER]),
                    },
                    "high_risk_count": len(high_risk),
                    "entry_points": [
                        {
                            "name": e.name,
                            "file": e.file_path,
                            "line": e.line,
                            "type": e.entry_type,
                            "route": e.route,
                            "method": e.method,
                            "is_authenticated": e.is_authenticated,
                            "risk_level": e.risk_level,
                        }
                        for e in entry_points[:50]
                    ],
                },
                confidence=0.85,
            )

        except Exception as e:
            logger.exception("Entry point detection failed")
            return StepToolResult(success=False, error=str(e))

    def _create_http_entry_point(
        self, file_path: str, line_num: int, match: Any, framework: str, lines: list[str]
    ) -> EntryPoint | None:
        """HTTP 엔드포인트 생성"""
        try:
            groups = match.groups()
            route = groups[0] if groups else ""
            method = groups[1] if len(groups) > 1 and groups[1] else "GET"

            # 함수명 찾기 (다음 def 라인)
            func_name = "unknown"
            for i in range(line_num, min(line_num + 5, len(lines))):
                line = lines[i] if i < len(lines) else ""
                if "def " in line:
                    import re

                    func_match = re.search(r"def\s+(\w+)", line)
                    if func_match:
                        func_name = func_match.group(1)
                    break

            # 인증 여부 확인
            context = "\n".join(lines[max(0, line_num - 3) : line_num + 10])
            is_authenticated = any(
                kw in context.lower()
                for kw in ["login_required", "authenticated", "jwt", "token", "auth", "permission"]
            )

            # 위험도 평가
            risk_level = self._assess_endpoint_risk(route, method, is_authenticated)

            return EntryPoint(
                name=func_name,
                file_path=file_path,
                line=line_num,
                entry_type=EntryPointType.HTTP_ENDPOINT,
                route=route,
                method=method.upper() if method else "GET",
                parameters=[],
                is_authenticated=is_authenticated,
                risk_level=risk_level,
            )

        except Exception:
            return None

    def _create_cli_entry_point(self, file_path: str, line_num: int, lines: list[str]) -> EntryPoint | None:
        """CLI 엔드포인트 생성"""
        try:
            func_name = "cli_command"
            for i in range(line_num, min(line_num + 5, len(lines))):
                line = lines[i] if i < len(lines) else ""
                if "def " in line:
                    import re

                    func_match = re.search(r"def\s+(\w+)", line)
                    if func_match:
                        func_name = func_match.group(1)
                    break

            return EntryPoint(
                name=func_name,
                file_path=file_path,
                line=line_num,
                entry_type=EntryPointType.CLI_COMMAND,
                route=None,
                method=None,
                parameters=[],
                is_authenticated=False,
                risk_level=RiskLevel.MEDIUM,
            )

        except Exception:
            return None

    def _find_main_function(self, file_path: str, content: str, lines: list[str]) -> EntryPoint | None:
        """Main 함수 찾기"""
        import re

        # if __name__ == "__main__" 패턴
        match = re.search(r'if\s+__name__\s*==\s*[\'"]__main__[\'"]\s*:', content)
        if match:
            line_num = content[: match.start()].count("\n") + 1
            return EntryPoint(
                name="__main__",
                file_path=file_path,
                line=line_num,
                entry_type=EntryPointType.MAIN,
                route=None,
                method=None,
                parameters=[],
                is_authenticated=False,
                risk_level=RiskLevel.LOW,
            )

        # def main() 패턴
        match = re.search(r"def\s+main\s*\(", content)
        if match:
            line_num = content[: match.start()].count("\n") + 1
            return EntryPoint(
                name="main",
                file_path=file_path,
                line=line_num,
                entry_type=EntryPointType.MAIN,
                route=None,
                method=None,
                parameters=[],
                is_authenticated=False,
                risk_level=RiskLevel.LOW,
            )

        return None

    def _find_test_functions(self, file_path: str, content: str, lines: list[str]) -> list[EntryPoint]:
        """테스트 함수 찾기"""
        import re

        entries: list[EntryPoint] = []

        # test_ 또는 _test 패턴
        for match in re.finditer(r"def\s+(test_\w+|_test\w*)\s*\(", content):
            line_num = content[: match.start()].count("\n") + 1
            func_name = match.group(1)

            entries.append(
                EntryPoint(
                    name=func_name,
                    file_path=file_path,
                    line=line_num,
                    entry_type=EntryPointType.TEST,
                    route=None,
                    method=None,
                    parameters=[],
                    is_authenticated=False,
                    risk_level=RiskLevel.LOW,
                )
            )

        from codegraph_engine.shared_kernel.contracts.thresholds import SCALE

        return entries[: SCALE.MAX_TEST_ENTRIES]

    def _assess_endpoint_risk(self, route: str, method: str, is_authenticated: bool) -> RiskLevel:
        """엔드포인트 위험도 평가"""
        # 인증 없는 POST/PUT/DELETE는 high
        if not is_authenticated and method in ["POST", "PUT", "DELETE", "PATCH"]:
            return RiskLevel.HIGH

        # 민감한 경로
        sensitive_paths = ["admin", "user", "password", "token", "auth", "payment", "transfer"]
        if any(p in route.lower() for p in sensitive_paths):
            if not is_authenticated:
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        # 인증 없는 GET
        if not is_authenticated:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW
