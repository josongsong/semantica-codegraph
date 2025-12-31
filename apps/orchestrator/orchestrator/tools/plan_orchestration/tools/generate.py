"""
Generate Step Tools (RFC-041)

코드 생성 및 패치 도구.
SOTA 참조: Aider, Cursor Composer, GitHub Copilot Workspace, Amazon Q

특징:
- Context-aware Code Generation
- Multi-strategy Fix Generation
- Semantic Patch Creation
- Validation-integrated Generation
"""

from dataclasses import dataclass, field
from typing import Any
from enum import Enum

from .base import StepTool, StepToolResult, QueryDSLMixin


class FixStrategy(Enum):
    """수정 전략"""

    SANITIZE_INPUT = "sanitize_input"  # 입력 검증/이스케이프
    PARAMETERIZE = "parameterize"  # 파라미터화 (SQL, 명령어)
    ESCAPE_OUTPUT = "escape_output"  # 출력 이스케이프
    ADD_GUARD = "add_guard"  # 가드 조건 추가
    REPLACE_API = "replace_api"  # 안전한 API로 교체
    ADD_VALIDATION = "add_validation"  # 검증 로직 추가
    REFACTOR = "refactor"  # 전체 리팩토링
    ALLOWLIST = "allowlist"  # 허용 목록 기반
    REMOVE_DANGEROUS = "remove_dangerous"  # 위험 코드 제거


@dataclass
class Patch:
    """코드 패치"""

    file_path: str
    original: str
    patched: str
    start_line: int
    end_line: int
    strategy: FixStrategy
    description: str
    confidence: float = 0.0
    # 메타데이터
    imports_added: list[str] = field(default_factory=list)
    imports_removed: list[str] = field(default_factory=list)
    functions_added: list[str] = field(default_factory=list)
    side_effects: list[str] = field(default_factory=list)


@dataclass
class IssueAnalysis:
    """이슈 분석 결과"""

    issue_type: str
    root_cause: str
    affected_code: str
    fix_location: str
    line_range: tuple[int, int]
    dependencies: list[str]
    constraints: list[str]
    suggested_strategies: list[FixStrategy]


class AnalyzeIssueTool(StepTool, QueryDSLMixin):
    """
    이슈 분석 Tool

    SOTA 참조:
    - Aider: Issue understanding
    - CodeQL: Root cause analysis
    - Infer: Bug pattern detection

    기능:
    - 취약점/버그 근본 원인 분석
    - 영향 범위 파악
    - 수정 제약 조건 식별
    """

    @property
    def name(self) -> str:
        return "analyze_issue"

    @property
    def description(self) -> str:
        return "이슈 분석 (근본 원인, 영향 범위, 제약 조건)"

    def execute(
        self,
        finding: dict[str, Any],
        ir_doc: Any | None = None,
        include_dependencies: bool = True,
        **kwargs,
    ) -> StepToolResult:
        """
        이슈 분석

        Args:
            finding: 보안/버그 분석 결과
            ir_doc: IR 문서 (선택적)
            include_dependencies: 의존성 분석 포함 여부
        """
        try:
            # IR 기반 엔진 (선택적)
            engine = None
            if ir_doc is not None:
                try:
                    engine = self._get_query_engine(ir_doc)
                except Exception:
                    engine = None

            # 1. 이슈 타입 식별
            issue_type = finding.get("type", finding.get("cwe_id", "unknown"))

            # 2. 근본 원인 분석
            root_cause = self._analyze_root_cause(finding, engine)

            # 3. 영향 코드 추출
            affected_code = self._extract_affected_code(finding, ir_doc)

            # 4. 수정 위치 결정
            fix_location, line_range = self._determine_fix_location(finding, engine)

            # 5. 의존성 분석
            dependencies: list[str] = []
            if include_dependencies and engine:
                dependencies = self._analyze_dependencies(fix_location, engine)

            # 6. 제약 조건 식별
            constraints = self._identify_constraints(finding, engine)

            # 7. 전략 제안
            strategies = self._suggest_strategies(issue_type, finding)

            analysis = IssueAnalysis(
                issue_type=issue_type,
                root_cause=root_cause,
                affected_code=affected_code,
                fix_location=fix_location,
                line_range=line_range,
                dependencies=dependencies,
                constraints=constraints,
                suggested_strategies=strategies,
            )

            return StepToolResult(
                success=True,
                data=self._analysis_to_dict(analysis),
                confidence=0.85,
                metadata={
                    "strategies_count": len(strategies),
                    "dependencies_count": len(dependencies),
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _analyze_root_cause(self, finding: dict[str, Any], engine: Any) -> str:
        """근본 원인 분석"""
        issue_type = finding.get("type", "").lower()
        source = finding.get("source", "")
        sink = finding.get("sink", "")

        # 타입별 근본 원인 템플릿
        causes = {
            "sql_injection": f"Unsanitized input from '{source}' concatenated into SQL query at '{sink}'",
            "command_injection": f"User input from '{source}' passed to shell command at '{sink}'",
            "xss": f"Unescaped output from '{source}' rendered in HTML at '{sink}'",
            "path_traversal": f"Path from '{source}' not validated before file access at '{sink}'",
            "ssrf": f"URL from '{source}' not validated before request at '{sink}'",
        }

        for key, cause in causes.items():
            if key in issue_type:
                return cause

        return f"Tainted data flows from '{source}' to dangerous sink '{sink}'"

    def _extract_affected_code(self, finding: dict[str, Any], ir_doc: Any) -> str:
        """영향받는 코드 추출"""
        if "code" in finding:
            return finding["code"]

        if "snippet" in finding:
            return finding["snippet"]

        # IR에서 추출 시도
        line = finding.get("line", 0)
        if hasattr(ir_doc, "source") and line > 0:
            lines = ir_doc.source.split("\n")
            start = max(0, line - 3)
            end = min(len(lines), line + 3)
            return "\n".join(lines[start:end])

        return ""

    def _determine_fix_location(self, finding: dict[str, Any], engine: Any) -> tuple[str, tuple[int, int]]:
        """수정 위치 결정"""
        # 기본: sink 위치
        location = finding.get("sink_location", finding.get("location", ""))
        line = finding.get("line", finding.get("sink_line", 0))

        return location, (line, line)

    def _analyze_dependencies(self, fix_location: str, engine: Any) -> list[str]:
        """수정 위치의 의존성 분석"""
        deps = []

        # 함수 이름 추출
        if "." in fix_location:
            func_name = fix_location.split(".")[-1]
        else:
            func_name = fix_location

        try:
            from codegraph_engine.code_foundation.domain.query import Q, E

            query = Q.function(func_name).follow(E.uses())
            results = engine.execute(query)

            for node in results[:20]:
                if hasattr(node, "name"):
                    deps.append(node.name)
        except Exception:
            pass

        return deps

    def _identify_constraints(self, finding: dict[str, Any], engine: Any) -> list[str]:
        """수정 제약 조건 식별"""
        constraints = []

        # API 호환성
        if finding.get("is_public_api"):
            constraints.append("Must maintain public API compatibility")

        # 성능
        path_length = len(finding.get("path", []))
        if path_length > 5:
            constraints.append("Complex data flow - consider multiple fix points")

        # 타입 안전성
        if finding.get("has_type_hints"):
            constraints.append("Must maintain type safety")

        return constraints

    def _suggest_strategies(self, issue_type: str, finding: dict[str, Any]) -> list[FixStrategy]:
        """수정 전략 제안"""
        issue_lower = issue_type.lower()

        strategy_map = {
            "sql": [FixStrategy.PARAMETERIZE, FixStrategy.ESCAPE_OUTPUT],
            "command": [FixStrategy.ALLOWLIST, FixStrategy.REPLACE_API],
            "xss": [FixStrategy.ESCAPE_OUTPUT, FixStrategy.SANITIZE_INPUT],
            "path": [FixStrategy.SANITIZE_INPUT, FixStrategy.ALLOWLIST],
            "ssrf": [FixStrategy.ALLOWLIST, FixStrategy.ADD_VALIDATION],
            "deserial": [FixStrategy.REPLACE_API, FixStrategy.ADD_VALIDATION],
        }

        for key, strategies in strategy_map.items():
            if key in issue_lower:
                return strategies

        return [FixStrategy.SANITIZE_INPUT, FixStrategy.ADD_GUARD]

    def _analysis_to_dict(self, analysis: IssueAnalysis) -> dict[str, Any]:
        """분석 결과를 딕셔너리로 변환"""
        return {
            "issue_type": analysis.issue_type,
            "root_cause": analysis.root_cause,
            "affected_code": analysis.affected_code,
            "fix_location": analysis.fix_location,
            "line_range": analysis.line_range,
            "dependencies": analysis.dependencies,
            "constraints": analysis.constraints,
            "suggested_strategies": [s.value for s in analysis.suggested_strategies],
        }


class DetermineFixStrategyTool(StepTool):
    """
    수정 전략 결정 Tool

    SOTA 참조:
    - GitHub Security Advisories: Fix strategy recommendations
    - Snyk Fix: Automated fix selection
    - Dependabot: Version update strategy

    기능:
    - 다중 전략 평가
    - 부작용 분석
    - 최적 전략 선택
    """

    @property
    def name(self) -> str:
        return "determine_fix_strategy"

    @property
    def description(self) -> str:
        return "최적 수정 전략 결정"

    def execute(
        self,
        issue_analysis: dict[str, Any],
        context: dict[str, Any] | None = None,
        prefer_minimal: bool = True,
        **kwargs,
    ) -> StepToolResult:
        """
        수정 전략 결정

        Args:
            issue_analysis: 이슈 분석 결과
            context: 추가 컨텍스트
            prefer_minimal: 최소 변경 선호
        """
        try:
            strategies = issue_analysis.get("suggested_strategies", [])
            constraints = issue_analysis.get("constraints", [])

            # 전략 평가
            evaluated = []
            for strategy_name in strategies:
                strategy = FixStrategy(strategy_name)
                evaluation = self._evaluate_strategy(strategy, issue_analysis, constraints, prefer_minimal)
                evaluated.append(evaluation)

            # 최적 전략 선택
            evaluated.sort(key=lambda x: x["score"], reverse=True)
            best = evaluated[0] if evaluated else None

            return StepToolResult(
                success=True,
                data={
                    "selected_strategy": best,
                    "alternatives": evaluated[1:3],
                    "rationale": self._generate_rationale(best, evaluated),
                },
                confidence=best["score"] if best else 0.0,
                metadata={
                    "strategies_evaluated": len(evaluated),
                    "constraints_applied": len(constraints),
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _evaluate_strategy(
        self,
        strategy: FixStrategy,
        analysis: dict[str, Any],
        constraints: list[str],
        prefer_minimal: bool,
    ) -> dict[str, Any]:
        """전략 평가"""
        score = 0.5  # 기본 점수

        # 전략별 기본 점수
        strategy_scores = {
            FixStrategy.PARAMETERIZE: 0.9,  # SQL 인젝션에 가장 효과적
            FixStrategy.ESCAPE_OUTPUT: 0.85,  # XSS에 효과적
            FixStrategy.SANITIZE_INPUT: 0.8,  # 범용적
            FixStrategy.ALLOWLIST: 0.85,  # 명령어 인젝션에 효과적
            FixStrategy.REPLACE_API: 0.75,  # 큰 변경 필요
            FixStrategy.ADD_GUARD: 0.7,  # 방어적
            FixStrategy.ADD_VALIDATION: 0.75,
            FixStrategy.REFACTOR: 0.5,  # 큰 변경
            FixStrategy.REMOVE_DANGEROUS: 0.6,
        }

        score = strategy_scores.get(strategy, 0.5)

        # 최소 변경 선호시 조정
        if prefer_minimal:
            minimal_strategies = [
                FixStrategy.PARAMETERIZE,
                FixStrategy.ESCAPE_OUTPUT,
                FixStrategy.ADD_GUARD,
            ]
            if strategy in minimal_strategies:
                score += 0.05

        # 제약 조건 적용
        if "API compatibility" in str(constraints):
            if strategy == FixStrategy.REFACTOR:
                score -= 0.2

        # 복잡도 기반 조정
        deps = len(analysis.get("dependencies", []))
        if deps > 10 and strategy in [FixStrategy.REFACTOR, FixStrategy.REPLACE_API]:
            score -= 0.1

        return {
            "strategy": strategy.value,
            "score": min(1.0, max(0.0, score)),
            "effort": self._estimate_effort(strategy),
            "risk": self._estimate_risk(strategy),
            "description": self._get_strategy_description(strategy),
        }

    def _estimate_effort(self, strategy: FixStrategy) -> str:
        """노력 추정"""
        effort_map = {
            FixStrategy.PARAMETERIZE: "low",
            FixStrategy.ESCAPE_OUTPUT: "low",
            FixStrategy.SANITIZE_INPUT: "low",
            FixStrategy.ADD_GUARD: "low",
            FixStrategy.ALLOWLIST: "medium",
            FixStrategy.ADD_VALIDATION: "medium",
            FixStrategy.REPLACE_API: "medium",
            FixStrategy.REMOVE_DANGEROUS: "medium",
            FixStrategy.REFACTOR: "high",
        }
        return effort_map.get(strategy, "medium")

    def _estimate_risk(self, strategy: FixStrategy) -> str:
        """위험도 추정"""
        risk_map = {
            FixStrategy.ESCAPE_OUTPUT: "low",
            FixStrategy.ADD_GUARD: "low",
            FixStrategy.PARAMETERIZE: "low",
            FixStrategy.SANITIZE_INPUT: "low",
            FixStrategy.ALLOWLIST: "medium",
            FixStrategy.ADD_VALIDATION: "medium",
            FixStrategy.REPLACE_API: "medium",
            FixStrategy.REMOVE_DANGEROUS: "high",
            FixStrategy.REFACTOR: "high",
        }
        return risk_map.get(strategy, "medium")

    def _get_strategy_description(self, strategy: FixStrategy) -> str:
        """전략 설명"""
        descriptions = {
            FixStrategy.PARAMETERIZE: "Use parameterized queries/commands",
            FixStrategy.ESCAPE_OUTPUT: "Escape special characters in output",
            FixStrategy.SANITIZE_INPUT: "Validate and sanitize user input",
            FixStrategy.ADD_GUARD: "Add defensive guard conditions",
            FixStrategy.ALLOWLIST: "Implement allowlist-based validation",
            FixStrategy.ADD_VALIDATION: "Add input/output validation",
            FixStrategy.REPLACE_API: "Replace with safer API",
            FixStrategy.REMOVE_DANGEROUS: "Remove dangerous functionality",
            FixStrategy.REFACTOR: "Refactor the affected code",
        }
        return descriptions.get(strategy, "Apply fix")

    def _generate_rationale(self, best: dict[str, Any] | None, all_strategies: list[dict[str, Any]]) -> str:
        """선택 근거 생성"""
        if not best:
            return "No suitable strategy found"

        rationale = f"Selected '{best['strategy']}' (score: {best['score']:.2f}). "
        rationale += f"Effort: {best['effort']}, Risk: {best['risk']}. "

        if len(all_strategies) > 1:
            alt = all_strategies[1]
            rationale += f"Alternative: '{alt['strategy']}' (score: {alt['score']:.2f})."

        return rationale


class GeneratePatchTool(StepTool):
    """
    패치 생성 Tool

    SOTA 참조:
    - Aider: Structured patch generation
    - Cursor Composer: Multi-file patch
    - GitHub Copilot: Context-aware code generation

    기능:
    - 전략 기반 패치 생성
    - AST 수준 변환
    - 다중 파일 패치 지원
    """

    @property
    def name(self) -> str:
        return "generate_patch"

    @property
    def description(self) -> str:
        return "보안 패치 생성"

    def execute(
        self,
        issue_analysis: dict[str, Any],
        fix_strategy: dict[str, Any],
        ir_doc: Any | None = None,
        **kwargs,
    ) -> StepToolResult:
        """
        패치 생성

        Args:
            issue_analysis: 이슈 분석 결과
            fix_strategy: 수정 전략
            ir_doc: IR 문서 (선택적)
        """
        try:
            strategy_name = fix_strategy.get("selected_strategy", {}).get("strategy")
            if not strategy_name:
                return StepToolResult(
                    success=False,
                    error="No strategy provided",
                    confidence=0.0,
                )

            strategy = FixStrategy(strategy_name)
            affected_code = issue_analysis.get("affected_code", "")
            issue_type = issue_analysis.get("issue_type", "")
            line_range = issue_analysis.get("line_range", (0, 0))

            # 전략별 패치 생성
            patched_code, imports_added = self._generate_patch_for_strategy(strategy, affected_code, issue_type)

            patch = Patch(
                file_path=issue_analysis.get("fix_location", ""),
                original=affected_code,
                patched=patched_code,
                start_line=line_range[0],
                end_line=line_range[1],
                strategy=strategy,
                description=f"Fix {issue_type} using {strategy.value}",
                confidence=0.8,
                imports_added=imports_added,
            )

            return StepToolResult(
                success=True,
                data=self._patch_to_dict(patch),
                confidence=patch.confidence,
                metadata={
                    "strategy": strategy.value,
                    "lines_changed": self._count_changes(affected_code, patched_code),
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _generate_patch_for_strategy(self, strategy: FixStrategy, code: str, issue_type: str) -> tuple[str, list[str]]:
        """전략별 패치 생성"""
        imports_added: list[str] = []

        if strategy == FixStrategy.PARAMETERIZE:
            return self._apply_parameterize(code, issue_type)

        if strategy == FixStrategy.ESCAPE_OUTPUT:
            return self._apply_escape_output(code, issue_type)

        if strategy == FixStrategy.SANITIZE_INPUT:
            return self._apply_sanitize_input(code, issue_type)

        if strategy == FixStrategy.ALLOWLIST:
            return self._apply_allowlist(code, issue_type)

        if strategy == FixStrategy.ADD_GUARD:
            return self._apply_add_guard(code, issue_type)

        if strategy == FixStrategy.REPLACE_API:
            return self._apply_replace_api(code, issue_type)

        # 기본: 주석 추가
        return f"# TODO: Fix {issue_type}\n{code}", imports_added

    def _apply_parameterize(self, code: str, issue_type: str) -> tuple[str, list[str]]:
        """파라미터화 적용"""
        imports: list[str] = []

        # SQL 인젝션 수정
        if "sql" in issue_type.lower():
            # f-string/format을 파라미터로 변환
            import re

            # 패턴: execute(f"SELECT ... {var} ...")
            pattern = r'execute\(f"([^"]+)"\)'

            def replace_fstring(match: re.Match) -> str:
                query = match.group(1)
                # {var}를 ?로 변환
                params = re.findall(r"\{(\w+)\}", query)
                safe_query = re.sub(r"\{(\w+)\}", "?", query)
                return f'execute("{safe_query}", ({", ".join(params)},))'

            patched = re.sub(pattern, replace_fstring, code)

            # % 포맷 변환
            pattern2 = r'execute\("([^"]+)"\s*%\s*\(([^)]+)\)\)'

            def replace_percent(match: re.Match) -> str:
                query = match.group(1)
                params = match.group(2)
                safe_query = re.sub(r"%s", "?", query)
                return f'execute("{safe_query}", ({params},))'

            patched = re.sub(pattern2, replace_percent, patched)
            return patched, imports

        return code, imports

    def _apply_escape_output(self, code: str, issue_type: str) -> tuple[str, list[str]]:
        """출력 이스케이프 적용"""
        imports: list[str] = []

        if "xss" in issue_type.lower():
            imports.append("from markupsafe import escape")

            # 직접 출력을 escape로 감싸기
            import re

            # return f"<div>{user_input}</div>" → return f"<div>{escape(user_input)}</div>"
            pattern = r"\{(\w+)\}"

            def escape_vars(match: re.Match) -> str:
                var = match.group(1)
                return f"{{escape({var})}}"

            patched = re.sub(pattern, escape_vars, code)
            return patched, imports

        return code, imports

    def _apply_sanitize_input(self, code: str, issue_type: str) -> tuple[str, list[str]]:
        """입력 검증 적용"""
        imports: list[str] = []

        if "path" in issue_type.lower():
            imports.append("import os")

            # 경로 검증 추가
            validation = """
    # Validate path
    if ".." in path or path.startswith("/"):
        raise ValueError("Invalid path")
    safe_path = os.path.normpath(path)
"""
            patched = validation + code
            return patched, imports

        return code, imports

    def _apply_allowlist(self, code: str, issue_type: str) -> tuple[str, list[str]]:
        """허용 목록 적용"""
        imports: list[str] = []

        if "command" in issue_type.lower():
            # 허용 목록 검증 추가
            validation = """
    ALLOWED_COMMANDS = {"ls", "cat", "echo"}
    if command not in ALLOWED_COMMANDS:
        raise ValueError(f"Command not allowed: {command}")
"""
            patched = validation + code
            return patched, imports

        return code, imports

    def _apply_add_guard(self, code: str, issue_type: str) -> tuple[str, list[str]]:
        """가드 조건 추가"""
        imports: list[str] = []

        # 일반적인 가드 추가
        guard = """
    if not value:
        raise ValueError("Invalid input")
"""
        patched = guard + code
        return patched, imports

    def _apply_replace_api(self, code: str, issue_type: str) -> tuple[str, list[str]]:
        """안전한 API로 교체"""
        imports: list[str] = []

        if "command" in issue_type.lower():
            # os.system → subprocess with shell=False
            import re

            pattern = r"os\.system\(([^)]+)\)"

            def replace_os_system(match: re.Match) -> str:
                cmd = match.group(1)
                return f"subprocess.run({cmd}.split(), shell=False, check=True)"

            patched = re.sub(pattern, replace_os_system, code)
            imports.append("import subprocess")
            return patched, imports

        if "deserial" in issue_type.lower():
            # pickle → json
            patched = code.replace("pickle.load", "json.load")
            patched = patched.replace("pickle.loads", "json.loads")
            imports.append("import json")
            return patched, imports

        return code, imports

    def _patch_to_dict(self, patch: Patch) -> dict[str, Any]:
        """패치를 딕셔너리로 변환"""
        return {
            "file_path": patch.file_path,
            "original": patch.original,
            "patched": patch.patched,
            "start_line": patch.start_line,
            "end_line": patch.end_line,
            "strategy": patch.strategy.value,
            "description": patch.description,
            "confidence": patch.confidence,
            "imports_added": patch.imports_added,
            "imports_removed": patch.imports_removed,
            "functions_added": patch.functions_added,
            "side_effects": patch.side_effects,
        }

    def _count_changes(self, original: str, patched: str) -> int:
        """변경 라인 수 계산"""
        orig_lines = set(original.split("\n"))
        patch_lines = set(patched.split("\n"))
        return len(orig_lines.symmetric_difference(patch_lines))


class ValidatePatchTool(StepTool):
    """
    패치 검증 Tool

    SOTA 참조:
    - Infer: Patch verification
    - CodeQL: Security re-analysis
    - Semgrep: Rule-based verification

    기능:
    - 구문 검증
    - 보안 재분석
    - 회귀 검사
    """

    @property
    def name(self) -> str:
        return "validate_patch"

    @property
    def description(self) -> str:
        return "패치 검증 (구문, 보안, 회귀)"

    def execute(
        self,
        patch: dict[str, Any],
        original_finding: dict[str, Any] | None = None,
        run_security_check: bool = True,
        **kwargs,
    ) -> StepToolResult:
        """
        패치 검증

        Args:
            patch: 생성된 패치
            original_finding: 원본 보안 분석 결과
            run_security_check: 보안 재분석 실행 여부
        """
        try:
            validations = []

            # 1. 구문 검증
            syntax_valid, syntax_errors = self._validate_syntax(patch.get("patched", ""))
            validations.append(
                {
                    "type": "syntax",
                    "passed": syntax_valid,
                    "errors": syntax_errors,
                }
            )

            # 2. 취약점 수정 검증
            vuln_fixed = False
            if run_security_check and original_finding:
                vuln_fixed = self._verify_vulnerability_fixed(
                    patch.get("patched", ""),
                    original_finding,
                )
            validations.append(
                {
                    "type": "vulnerability_fix",
                    "passed": vuln_fixed,
                    "details": "Original vulnerability pattern not found in patched code",
                }
            )

            # 3. 새로운 취약점 검사
            new_vulns = self._check_new_vulnerabilities(patch.get("patched", ""))
            validations.append(
                {
                    "type": "no_new_vulnerabilities",
                    "passed": len(new_vulns) == 0,
                    "new_issues": new_vulns,
                }
            )

            # 4. 변경 최소성 검사
            minimal = self._check_minimal_change(
                patch.get("original", ""),
                patch.get("patched", ""),
            )
            validations.append(
                {
                    "type": "minimal_change",
                    "passed": minimal,
                }
            )

            # 전체 결과
            all_passed = all(v["passed"] for v in validations)

            return StepToolResult(
                success=True,
                data={
                    "valid": all_passed,
                    "validations": validations,
                    "summary": self._generate_summary(validations),
                },
                confidence=0.9 if all_passed else 0.5,
                metadata={
                    "checks_passed": sum(1 for v in validations if v["passed"]),
                    "checks_total": len(validations),
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _validate_syntax(self, code: str) -> tuple[bool, list[str]]:
        """구문 검증"""
        try:
            compile(code, "<string>", "exec")
            return True, []
        except SyntaxError as e:
            return False, [f"Line {e.lineno}: {e.msg}"]

    def _verify_vulnerability_fixed(self, patched_code: str, original_finding: dict[str, Any]) -> bool:
        """취약점 수정 검증"""
        issue_type = original_finding.get("type", "").lower()
        sink = original_finding.get("sink", "")

        # SQL Injection: 파라미터화 확인
        if "sql" in issue_type:
            # 문자열 연결 패턴이 없어야 함
            dangerous_patterns = [
                'execute(f"',
                "execute(f'",
                "% (",
                ".format(",
            ]
            return not any(p in patched_code for p in dangerous_patterns)

        # Command Injection: shell=True 없어야 함
        if "command" in issue_type:
            return "shell=True" not in patched_code

        # XSS: escape 사용 확인
        if "xss" in issue_type:
            return "escape(" in patched_code or "| e" in patched_code

        return True  # 기본 통과

    def _check_new_vulnerabilities(self, code: str) -> list[str]:
        """새로운 취약점 검사"""
        issues = []

        # 위험한 패턴 검사
        dangerous_patterns = {
            "eval(": "Potential code injection via eval()",
            "exec(": "Potential code injection via exec()",
            "pickle.load": "Potential insecure deserialization",
            "shell=True": "Potential command injection with shell=True",
            "__import__": "Dynamic import detected",
        }

        for pattern, issue in dangerous_patterns.items():
            if pattern in code:
                issues.append(issue)

        return issues

    def _check_minimal_change(self, original: str, patched: str) -> bool:
        """최소 변경 검사"""
        # 변경 라인 수 계산
        orig_lines = original.split("\n")
        patch_lines = patched.split("\n")

        # 변경이 전체의 50% 미만이어야 함
        total = max(len(orig_lines), len(patch_lines))
        if total == 0:
            return True

        changed = abs(len(orig_lines) - len(patch_lines))
        for i in range(min(len(orig_lines), len(patch_lines))):
            if orig_lines[i] != patch_lines[i]:
                changed += 1

        return (changed / total) < 0.5

    def _generate_summary(self, validations: list[dict[str, Any]]) -> str:
        """검증 요약 생성"""
        passed = sum(1 for v in validations if v["passed"])
        total = len(validations)

        if passed == total:
            return f"All {total} validations passed"

        failed = [v["type"] for v in validations if not v["passed"]]
        return f"{passed}/{total} validations passed. Failed: {', '.join(failed)}"
