"""
Explain Step Tools (RFC-041)

LLM 기반 설명 생성 도구.
SOTA 참조: GitHub Copilot Explain, Cursor Composer, Sourcegraph Cody

특징:
- Contextual Explanation: 코드 컨텍스트 기반 설명
- Multi-level Detail: 요약/상세/전문가 수준 지원
- Evidence-based: 코드 증거 기반 설명
"""

from dataclasses import dataclass, field
from typing import Any

from .base import StepTool, StepToolResult, QueryDSLMixin


@dataclass
class CodeContext:
    """코드 컨텍스트 정보"""

    symbol_name: str
    symbol_type: str  # function, class, method, variable
    file_path: str
    line_range: tuple[int, int]
    source_code: str
    docstring: str | None = None
    signature: str | None = None
    # 관계 정보
    callers: list[str] = field(default_factory=list)
    callees: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    dependents: list[str] = field(default_factory=list)
    # 타입 정보
    parameter_types: dict[str, str] = field(default_factory=dict)
    return_type: str | None = None
    # 보안/품질 메타데이터
    complexity: int = 0
    has_tests: bool = False
    security_notes: list[str] = field(default_factory=list)


@dataclass
class FindingContext:
    """보안/분석 결과 컨텍스트"""

    finding_type: str  # vulnerability, bug, code_smell, etc.
    severity: str  # critical, high, medium, low, info
    location: str
    line_number: int
    code_snippet: str
    # 흐름 정보
    source: str | None = None
    sink: str | None = None
    taint_path: list[str] = field(default_factory=list)
    # 분석 정보
    cwe_id: str | None = None
    rule_id: str | None = None
    confidence: float = 0.0
    # 수정 제안
    fix_suggestions: list[str] = field(default_factory=list)
    similar_fixes: list[dict[str, Any]] = field(default_factory=list)


class ExtractContextTool(StepTool, QueryDSLMixin):
    """
    코드 컨텍스트 추출 Tool

    SOTA 참조:
    - Sourcegraph Cody: Context-aware code understanding
    - GitHub Copilot: Contextual code explanation
    - Cursor: Smart context extraction

    기능:
    - 심볼 정의 및 시그니처 추출
    - 호출 관계 분석
    - 의존성 그래프 구축
    - 타입 정보 수집
    """

    @property
    def name(self) -> str:
        return "extract_context"

    @property
    def description(self) -> str:
        return "코드 컨텍스트 추출 (심볼, 관계, 타입, 메타데이터)"

    def execute(
        self,
        symbol_name: str,
        ir_doc: Any,
        depth: int = 2,
        include_source: bool = True,
        include_callers: bool = True,
        include_callees: bool = True,
        **kwargs,
    ) -> StepToolResult:
        """
        심볼의 전체 컨텍스트 추출

        Args:
            symbol_name: 대상 심볼 이름
            ir_doc: IR 문서
            depth: 관계 탐색 깊이
            include_source: 소스 코드 포함 여부
            include_callers: 호출자 포함 여부
            include_callees: 피호출자 포함 여부
        """
        try:
            engine = self._get_query_engine(ir_doc)

            # 1. 심볼 정의 찾기
            symbol_info = self._find_symbol_definition(engine, symbol_name, ir_doc)
            if not symbol_info:
                return StepToolResult(
                    success=False,
                    error=f"Symbol not found: {symbol_name}",
                    confidence=0.0,
                )

            # 2. 컨텍스트 구축
            context = CodeContext(
                symbol_name=symbol_name,
                symbol_type=symbol_info.get("type", "unknown"),
                file_path=symbol_info.get("file_path", ""),
                line_range=symbol_info.get("line_range", (0, 0)),
                source_code=symbol_info.get("source", "") if include_source else "",
                docstring=symbol_info.get("docstring"),
                signature=symbol_info.get("signature"),
            )

            # 3. 호출 관계 수집
            if include_callers:
                context.callers = self._find_callers(engine, symbol_name, depth)

            if include_callees:
                context.callees = self._find_callees(engine, symbol_name, depth)

            # 4. 의존성 분석
            context.dependencies = self._find_dependencies(engine, symbol_name)
            context.dependents = self._find_dependents(engine, symbol_name)

            # 5. 타입 정보 추출
            type_info = self._extract_type_info(symbol_info)
            context.parameter_types = type_info.get("parameters", {})
            context.return_type = type_info.get("return_type")

            # 6. 메타데이터 수집
            context.complexity = self._calculate_complexity(symbol_info)
            context.has_tests = self._check_has_tests(engine, symbol_name)
            context.security_notes = self._collect_security_notes(symbol_info)

            return StepToolResult(
                success=True,
                data={
                    "context": self._context_to_dict(context),
                    "summary": self._generate_summary(context),
                },
                confidence=0.95,
                metadata={
                    "callers_count": len(context.callers),
                    "callees_count": len(context.callees),
                    "depth": depth,
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _find_symbol_definition(self, engine: Any, symbol_name: str, ir_doc: Any) -> dict[str, Any] | None:
        """심볼 정의 찾기"""
        from codegraph_engine.code_foundation.domain.query import Q

        # 함수/메서드 찾기
        query = Q.function(symbol_name)
        results = engine.execute(query)

        if results:
            node = results[0] if isinstance(results, list) else results
            return self._node_to_info(node, ir_doc)

        # 클래스 찾기
        query = Q.cls(symbol_name)
        results = engine.execute(query)

        if results:
            node = results[0] if isinstance(results, list) else results
            return self._node_to_info(node, ir_doc)

        return None

    def _node_to_info(self, node: Any, ir_doc: Any) -> dict[str, Any]:
        """노드를 정보 딕셔너리로 변환"""
        info: dict[str, Any] = {
            "type": getattr(node, "node_type", "unknown"),
            "file_path": getattr(ir_doc, "file_path", ""),
            "line_range": (
                getattr(node, "start_line", 0),
                getattr(node, "end_line", 0),
            ),
        }

        # 소스 코드
        if hasattr(node, "source"):
            info["source"] = node.source
        elif hasattr(node, "text"):
            info["source"] = node.text

        # 시그니처
        if hasattr(node, "signature"):
            info["signature"] = node.signature

        # 독스트링
        if hasattr(node, "docstring"):
            info["docstring"] = node.docstring

        # 파라미터
        if hasattr(node, "parameters"):
            info["parameters"] = node.parameters

        # 반환 타입
        if hasattr(node, "return_type"):
            info["return_type"] = node.return_type

        return info

    def _find_callers(self, engine: Any, symbol_name: str, depth: int) -> list[str]:
        """호출자 찾기"""
        from codegraph_engine.code_foundation.domain.query import Q, E

        callers = []
        try:
            query = Q.any().where(E.calls(symbol_name))
            results = engine.execute(query)

            for node in results[:50]:  # 최대 50개
                if hasattr(node, "name"):
                    callers.append(node.name)
        except Exception:
            pass

        return callers

    def _find_callees(self, engine: Any, symbol_name: str, depth: int) -> list[str]:
        """피호출자 찾기"""
        from codegraph_engine.code_foundation.domain.query import Q, E

        callees = []
        try:
            query = Q.function(symbol_name).follow(E.calls())
            results = engine.execute(query)

            for node in results[:50]:
                if hasattr(node, "name"):
                    callees.append(node.name)
        except Exception:
            pass

        return callees

    def _find_dependencies(self, engine: Any, symbol_name: str) -> list[str]:
        """의존성 찾기 (import 기반)"""
        deps = []
        try:
            from codegraph_engine.code_foundation.domain.query import Q, E

            query = Q.function(symbol_name).follow(E.uses())
            results = engine.execute(query)

            for node in results[:30]:
                if hasattr(node, "module"):
                    deps.append(node.module)
        except Exception:
            pass

        return deps

    def _find_dependents(self, engine: Any, symbol_name: str) -> list[str]:
        """역의존성 찾기"""
        return []  # 추후 구현

    def _extract_type_info(self, symbol_info: dict[str, Any]) -> dict[str, Any]:
        """타입 정보 추출"""
        result: dict[str, Any] = {"parameters": {}, "return_type": None}

        if "parameters" in symbol_info:
            for param in symbol_info["parameters"]:
                if isinstance(param, dict):
                    name = param.get("name", "")
                    ptype = param.get("type", "Any")
                    result["parameters"][name] = ptype

        if "return_type" in symbol_info:
            result["return_type"] = symbol_info["return_type"]

        return result

    def _calculate_complexity(self, symbol_info: dict[str, Any]) -> int:
        """복잡도 계산 (Cyclomatic Complexity 추정)"""
        source = symbol_info.get("source", "")
        if not source:
            return 0

        # 분기문 카운트
        complexity = 1
        keywords = ["if", "elif", "else", "for", "while", "except", "with", "and", "or"]
        for kw in keywords:
            complexity += source.count(f" {kw} ") + source.count(f"\n{kw} ")

        return complexity

    def _check_has_tests(self, engine: Any, symbol_name: str) -> bool:
        """테스트 존재 여부 확인"""
        try:
            from codegraph_engine.code_foundation.domain.query import Q

            test_patterns = [f"test_{symbol_name}", f"{symbol_name}_test", f"Test{symbol_name}"]
            for pattern in test_patterns:
                query = Q.function(pattern)
                results = engine.execute(query)
                if results:
                    return True
        except Exception:
            pass

        return False

    def _collect_security_notes(self, symbol_info: dict[str, Any]) -> list[str]:
        """보안 관련 노트 수집"""
        notes = []
        source = symbol_info.get("source", "")

        # 보안 관련 패턴 감지
        security_patterns = {
            "eval(": "Dynamic code execution detected",
            "exec(": "Dynamic code execution detected",
            "subprocess": "Shell command execution detected",
            "os.system": "Shell command execution detected",
            "pickle.load": "Unsafe deserialization detected",
            "yaml.load": "Potentially unsafe YAML loading",
            "sql": "SQL operations detected",
            "password": "Password handling detected",
            "secret": "Secret handling detected",
            "token": "Token handling detected",
        }

        for pattern, note in security_patterns.items():
            if pattern.lower() in source.lower():
                notes.append(note)

        return notes

    def _context_to_dict(self, context: CodeContext) -> dict[str, Any]:
        """CodeContext를 딕셔너리로 변환"""
        return {
            "symbol_name": context.symbol_name,
            "symbol_type": context.symbol_type,
            "file_path": context.file_path,
            "line_range": context.line_range,
            "source_code": context.source_code,
            "docstring": context.docstring,
            "signature": context.signature,
            "callers": context.callers,
            "callees": context.callees,
            "dependencies": context.dependencies,
            "dependents": context.dependents,
            "parameter_types": context.parameter_types,
            "return_type": context.return_type,
            "complexity": context.complexity,
            "has_tests": context.has_tests,
            "security_notes": context.security_notes,
        }

    def _generate_summary(self, context: CodeContext) -> str:
        """컨텍스트 요약 생성"""
        parts = [f"{context.symbol_type.capitalize()} '{context.symbol_name}'"]

        if context.callers:
            parts.append(f"called by {len(context.callers)} functions")

        if context.callees:
            parts.append(f"calls {len(context.callees)} functions")

        if context.complexity > 10:
            parts.append(f"high complexity ({context.complexity})")

        if context.security_notes:
            parts.append(f"{len(context.security_notes)} security notes")

        if not context.has_tests:
            parts.append("no tests found")

        return ", ".join(parts)


class ExplainFindingTool(StepTool):
    """
    분석 결과 설명 Tool (LLM 기반)

    SOTA 참조:
    - Snyk Explain: Vulnerability explanation
    - SonarQube: Issue explanation with fix suggestions
    - CodeQL: Query result explanation

    기능:
    - 취약점/이슈 설명 생성
    - 수정 제안 생성
    - 증거 기반 설명
    - 다중 상세도 레벨 지원
    """

    @property
    def name(self) -> str:
        return "explain_finding"

    @property
    def description(self) -> str:
        return "분석 결과 설명 생성 (LLM 기반)"

    def execute(
        self,
        finding: dict[str, Any],
        context: dict[str, Any] | None = None,
        detail_level: str = "standard",  # brief, standard, detailed, expert
        include_fix: bool = True,
        include_references: bool = True,
        **kwargs,
    ) -> StepToolResult:
        """
        분석 결과에 대한 설명 생성

        Args:
            finding: 분석 결과 (taint flow, vulnerability 등)
            context: 추가 컨텍스트 정보
            detail_level: 설명 상세도 (brief/standard/detailed/expert)
            include_fix: 수정 제안 포함 여부
            include_references: 참조 문서 포함 여부
        """
        try:
            # 1. Finding 컨텍스트 구축
            finding_ctx = self._build_finding_context(finding, context)

            # 2. 설명 생성 (규칙 기반 + 템플릿)
            explanation = self._generate_explanation(finding_ctx, detail_level)

            # 3. 수정 제안 생성
            fix_suggestions = []
            if include_fix:
                fix_suggestions = self._generate_fix_suggestions(finding_ctx)

            # 4. 참조 문서 수집
            references = []
            if include_references:
                references = self._collect_references(finding_ctx)

            # 5. 증거 수집
            evidence = self._collect_evidence(finding_ctx)

            return StepToolResult(
                success=True,
                data={
                    "explanation": explanation,
                    "fix_suggestions": fix_suggestions,
                    "references": references,
                    "evidence": evidence,
                    "severity": finding_ctx.severity,
                    "confidence": finding_ctx.confidence,
                },
                confidence=finding_ctx.confidence,
                metadata={
                    "detail_level": detail_level,
                    "finding_type": finding_ctx.finding_type,
                    "cwe_id": finding_ctx.cwe_id,
                },
            )

        except Exception as e:
            return StepToolResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

    def _build_finding_context(self, finding: dict[str, Any], context: dict[str, Any] | None) -> FindingContext:
        """Finding 컨텍스트 구축"""
        ctx = FindingContext(
            finding_type=finding.get("type", "unknown"),
            severity=finding.get("severity", "medium"),
            location=finding.get("location", finding.get("file", "")),
            line_number=finding.get("line", 0),
            code_snippet=finding.get("code", finding.get("snippet", "")),
            source=finding.get("source"),
            sink=finding.get("sink"),
            taint_path=finding.get("path", []),
            cwe_id=finding.get("cwe_id"),
            rule_id=finding.get("rule_id"),
            confidence=finding.get("confidence", 0.7),
        )

        # 추가 컨텍스트 병합
        if context:
            if "fix_suggestions" in context:
                ctx.fix_suggestions = context["fix_suggestions"]
            if "similar_fixes" in context:
                ctx.similar_fixes = context["similar_fixes"]

        return ctx

    def _generate_explanation(self, ctx: FindingContext, detail_level: str) -> dict[str, str]:
        """설명 생성"""
        # CWE별 설명 템플릿
        cwe_explanations = {
            "CWE-89": {
                "title": "SQL Injection",
                "brief": "User input is used directly in SQL query without sanitization.",
                "standard": (
                    "SQL Injection vulnerability detected. User-controlled input flows "
                    "into a SQL query without proper sanitization or parameterization. "
                    "An attacker could manipulate the query to access or modify data."
                ),
                "detailed": (
                    "SQL Injection (CWE-89) is a code injection technique that exploits "
                    "security vulnerabilities in an application's database layer. This occurs "
                    "when user input is incorrectly filtered or not strongly typed and "
                    "unexpectedly executed as part of a SQL command.\n\n"
                    "Attack vectors include: authentication bypass, data exfiltration, "
                    "data modification, and in some cases, command execution."
                ),
                "expert": (
                    "SQL Injection vulnerability identified through taint analysis. "
                    "The data flow analysis shows untrusted input propagating to a SQL "
                    "execution sink without passing through a sanitizer or parameterization.\n\n"
                    "Technical details:\n"
                    "- Taint source: User-controlled input\n"
                    "- Taint sink: SQL execution function\n"
                    "- Missing: Parameterized queries, input validation, or escaping\n"
                    "- CVSS considerations: Network vector, low complexity, high impact"
                ),
            },
            "CWE-78": {
                "title": "OS Command Injection",
                "brief": "User input is used in shell command execution.",
                "standard": (
                    "OS Command Injection vulnerability detected. User-controlled input "
                    "is passed to a shell command without proper sanitization, allowing "
                    "an attacker to execute arbitrary system commands."
                ),
                "detailed": (
                    "OS Command Injection (CWE-78) allows attackers to execute arbitrary "
                    "commands on the host operating system. This vulnerability exists when "
                    "an application passes unsafe user-supplied data to a system shell.\n\n"
                    "Impact: Full system compromise, data theft, service disruption."
                ),
                "expert": (
                    "Command injection via unsanitized input to shell execution sink. "
                    "Taint propagation confirmed from user input to subprocess/os.system call.\n\n"
                    "Attack surface analysis:\n"
                    "- Shell metacharacters: ; | & $ ` \\ \" '\n"
                    "- Bypass techniques: newline injection, null byte, encoding\n"
                    "- Mitigation: Avoid shell=True, use allowlists, input validation"
                ),
            },
            "CWE-79": {
                "title": "Cross-Site Scripting (XSS)",
                "brief": "User input is rendered in HTML without escaping.",
                "standard": (
                    "XSS vulnerability detected. User-controlled input is reflected in "
                    "the HTML response without proper encoding, allowing script injection."
                ),
                "detailed": (
                    "Cross-Site Scripting (CWE-79) enables attackers to inject client-side "
                    "scripts into web pages viewed by other users. XSS can be used to bypass "
                    "access controls, steal session cookies, or perform actions as the victim."
                ),
                "expert": (
                    "XSS through unescaped output rendering. Taint flow shows user input "
                    "reaching HTML/template output without passing through escape/encode.\n\n"
                    "Classification: Reflected/Stored/DOM-based\n"
                    "Context-aware escaping required based on output context."
                ),
            },
        }

        # CWE ID로 설명 선택
        cwe_id = ctx.cwe_id or self._infer_cwe_from_type(ctx.finding_type)
        template = cwe_explanations.get(cwe_id, self._get_generic_template(ctx))

        return {
            "title": template.get("title", ctx.finding_type),
            "summary": template.get("brief", "Security issue detected."),
            "description": template.get(detail_level, template.get("standard", "")),
            "source_info": f"Source: {ctx.source}" if ctx.source else "",
            "sink_info": f"Sink: {ctx.sink}" if ctx.sink else "",
            "path_info": " → ".join(ctx.taint_path) if ctx.taint_path else "",
        }

    def _infer_cwe_from_type(self, finding_type: str) -> str | None:
        """Finding 타입에서 CWE 추론"""
        type_to_cwe = {
            "sql_injection": "CWE-89",
            "sqli": "CWE-89",
            "command_injection": "CWE-78",
            "os_command": "CWE-78",
            "xss": "CWE-79",
            "cross_site_scripting": "CWE-79",
            "path_traversal": "CWE-22",
            "ssrf": "CWE-918",
            "xxe": "CWE-611",
            "deserialization": "CWE-502",
        }
        return type_to_cwe.get(finding_type.lower())

    def _get_generic_template(self, ctx: FindingContext) -> dict[str, str]:
        """일반 템플릿 생성"""
        return {
            "title": ctx.finding_type.replace("_", " ").title(),
            "brief": f"Security issue: {ctx.finding_type}",
            "standard": f"A {ctx.finding_type} issue was detected at {ctx.location}:{ctx.line_number}.",
            "detailed": (
                f"Security analysis detected a {ctx.finding_type} vulnerability. "
                f"Location: {ctx.location} at line {ctx.line_number}. "
                f"Severity: {ctx.severity}. Confidence: {ctx.confidence:.0%}."
            ),
            "expert": (
                f"Taint analysis identified {ctx.finding_type} with confidence {ctx.confidence:.0%}. "
                f"Review the data flow path for potential false positive determination."
            ),
        }

    def _generate_fix_suggestions(self, ctx: FindingContext) -> list[dict[str, Any]]:
        """수정 제안 생성"""
        cwe_fixes = {
            "CWE-89": [
                {
                    "title": "Use Parameterized Queries",
                    "priority": 1,
                    "description": "Replace string concatenation with parameterized queries",
                    "example": 'cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))',
                    "effort": "low",
                },
                {
                    "title": "Use ORM",
                    "priority": 2,
                    "description": "Use an ORM like SQLAlchemy that handles parameterization",
                    "example": "User.query.filter_by(id=user_id).first()",
                    "effort": "medium",
                },
            ],
            "CWE-78": [
                {
                    "title": "Avoid Shell Execution",
                    "priority": 1,
                    "description": "Use subprocess with shell=False and list arguments",
                    "example": 'subprocess.run(["ls", "-la", path], shell=False)',
                    "effort": "low",
                },
                {
                    "title": "Input Validation",
                    "priority": 2,
                    "description": "Validate input against an allowlist of permitted values",
                    "example": "if filename in ALLOWED_FILES: ...",
                    "effort": "medium",
                },
            ],
            "CWE-79": [
                {
                    "title": "HTML Escape Output",
                    "priority": 1,
                    "description": "Use template auto-escaping or html.escape()",
                    "example": "{{ user_input | e }}  # Jinja2 auto-escape",
                    "effort": "low",
                },
                {
                    "title": "Content Security Policy",
                    "priority": 2,
                    "description": "Implement CSP headers as defense-in-depth",
                    "example": "Content-Security-Policy: default-src 'self'",
                    "effort": "medium",
                },
            ],
        }

        cwe_id = ctx.cwe_id or self._infer_cwe_from_type(ctx.finding_type)
        return cwe_fixes.get(cwe_id, [{"title": "Review and sanitize input", "priority": 1}])

    def _collect_references(self, ctx: FindingContext) -> list[dict[str, str]]:
        """참조 문서 수집"""
        references = []

        if ctx.cwe_id:
            cwe_num = ctx.cwe_id.replace("CWE-", "")
            references.append(
                {
                    "title": f"CWE-{cwe_num} Definition",
                    "url": f"https://cwe.mitre.org/data/definitions/{cwe_num}.html",
                    "type": "cwe",
                }
            )

        # OWASP 참조
        owasp_map = {
            "CWE-89": "https://owasp.org/www-community/attacks/SQL_Injection",
            "CWE-78": "https://owasp.org/www-community/attacks/Command_Injection",
            "CWE-79": "https://owasp.org/www-community/attacks/xss/",
        }
        cwe_id = ctx.cwe_id or self._infer_cwe_from_type(ctx.finding_type)
        if cwe_id and cwe_id in owasp_map:
            references.append(
                {
                    "title": "OWASP Reference",
                    "url": owasp_map[cwe_id],
                    "type": "owasp",
                }
            )

        return references

    def _collect_evidence(self, ctx: FindingContext) -> list[dict[str, Any]]:
        """증거 수집"""
        evidence = []

        # 코드 스니펫
        if ctx.code_snippet:
            evidence.append(
                {
                    "type": "code",
                    "location": f"{ctx.location}:{ctx.line_number}",
                    "content": ctx.code_snippet,
                }
            )

        # Taint 경로
        if ctx.taint_path:
            evidence.append(
                {
                    "type": "taint_path",
                    "path": ctx.taint_path,
                    "source": ctx.source,
                    "sink": ctx.sink,
                }
            )

        return evidence
