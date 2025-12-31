"""
Security Spec Tests

SOTA-Level: Base + Edge + Extreme + CWE Patterns
"""

import pytest

from codegraph_runtime.codegen_loop.domain.specs.security_spec import (
    CWECategory,
    DataflowPath,
    Sanitizer,
    SecuritySpec,
    SecurityViolation,
    TaintSink,
    TaintSource,
)


class TestTaintSource:
    """TaintSource 테스트"""

    def test_valid_taint_source(self):
        """Base: 유효한 TaintSource"""
        source = TaintSource(
            cwe=CWECategory.XSS,
            source_patterns={"request.args", "request.form"},
        )

        assert source.cwe == CWECategory.XSS
        assert "request.args" in source.source_patterns
        assert len(source.source_patterns) == 2

    def test_empty_patterns_raises(self):
        """Edge: 빈 패턴은 에러"""
        with pytest.raises(ValueError, match="source_patterns cannot be empty"):
            TaintSource(cwe=CWECategory.XSS, source_patterns=set())


class TestTaintSink:
    """TaintSink 테스트"""

    def test_valid_taint_sink(self):
        """Base: 유효한 TaintSink"""
        sink = TaintSink(
            cwe=CWECategory.SQL_INJECTION,
            sink_patterns={"execute", "cursor.execute"},
        )

        assert sink.cwe == CWECategory.SQL_INJECTION
        assert "execute" in sink.sink_patterns

    def test_empty_patterns_raises(self):
        """Edge: 빈 패턴은 에러"""
        with pytest.raises(ValueError, match="sink_patterns cannot be empty"):
            TaintSink(cwe=CWECategory.SQL_INJECTION, sink_patterns=set())


class TestSanitizer:
    """Sanitizer 테스트"""

    def test_valid_sanitizer(self):
        """Base: 유효한 Sanitizer"""
        sanitizer = Sanitizer(
            cwe=CWECategory.XSS,
            sanitizer_patterns={"escape", "bleach.clean"},
        )

        assert sanitizer.cwe == CWECategory.XSS
        assert "escape" in sanitizer.sanitizer_patterns

    def test_empty_patterns_raises(self):
        """Edge: 빈 패턴은 에러"""
        with pytest.raises(ValueError, match="sanitizer_patterns cannot be empty"):
            Sanitizer(cwe=CWECategory.XSS, sanitizer_patterns=set())


class TestDataflowPath:
    """DataflowPath 테스트"""

    def test_vulnerable_path_no_sanitizer(self):
        """Base: Sanitizer 없는 취약한 경로"""
        path = DataflowPath(
            source="request.args",
            sink="execute",
            path_nodes=["request.args", "query", "execute"],
            has_sanitizer=False,
        )

        assert path.is_vulnerable
        assert path.path_length == 3
        assert len(path.sanitizers_used) == 0

    def test_safe_path_with_sanitizer(self):
        """Base: Sanitizer 있는 안전한 경로"""
        path = DataflowPath(
            source="request.args",
            sink="execute",
            path_nodes=["request.args", "escape", "execute"],
            has_sanitizer=True,
            sanitizers_used=["escape"],
        )

        assert not path.is_vulnerable
        assert len(path.sanitizers_used) == 1

    def test_direct_path(self):
        """Edge: 직접 연결 (길이 2)"""
        path = DataflowPath(
            source="request.args",
            sink="execute",
            path_nodes=["request.args", "execute"],
            has_sanitizer=False,
        )

        assert path.path_length == 2
        assert path.is_vulnerable

    def test_long_path(self):
        """Extreme: 매우 긴 경로 (15+ nodes)"""
        nodes = [f"node{i}" for i in range(20)]
        path = DataflowPath(
            source="source",
            sink="sink",
            path_nodes=nodes,
            has_sanitizer=False,
        )

        assert path.path_length == 20


class TestSecurityViolation:
    """SecurityViolation 테스트"""

    def test_valid_violation(self):
        """Base: 유효한 위반"""
        path = DataflowPath("src", "sink", ["src", "sink"], False)
        violation = SecurityViolation(
            cwe=CWECategory.XSS,
            path=path,
            severity="critical",
            description="XSS vulnerability",
        )

        assert violation.cwe == CWECategory.XSS
        assert violation.severity == "critical"
        assert violation.path == path

    def test_invalid_severity_raises(self):
        """Edge: 잘못된 severity는 에러"""
        path = DataflowPath("src", "sink", [], False)

        with pytest.raises(ValueError, match="severity must be one of"):
            SecurityViolation(
                cwe=CWECategory.XSS,
                path=path,
                severity="invalid",
                description="test",
            )

    def test_valid_severities(self):
        """Base: 유효한 severity 값들"""
        path = DataflowPath("src", "sink", [], False)

        for severity in ["critical", "high", "medium", "low"]:
            violation = SecurityViolation(
                cwe=CWECategory.XSS,
                path=path,
                severity=severity,
                description="test",
            )
            assert violation.severity == severity


class TestSecuritySpec:
    """SecuritySpec 테스트 (CWE Patterns)"""

    def test_default_sources_loaded(self):
        """Base: 기본 Sources 로드"""
        spec = SecuritySpec()

        assert CWECategory.XSS in spec.sources
        assert CWECategory.SQL_INJECTION in spec.sources
        assert CWECategory.OS_COMMAND in spec.sources

        xss_source = spec.sources[CWECategory.XSS]
        assert "request.args" in xss_source.source_patterns
        assert "request.form" in xss_source.source_patterns

    def test_default_sinks_loaded(self):
        """Base: 기본 Sinks 로드"""
        spec = SecuritySpec()

        assert CWECategory.XSS in spec.sinks

        xss_sink = spec.sinks[CWECategory.XSS]
        assert "render_template_string" in xss_sink.sink_patterns

    def test_default_sanitizers_loaded(self):
        """Base: 기본 Sanitizers 로드"""
        spec = SecuritySpec()

        assert CWECategory.XSS in spec.sanitizers

        xss_sanitizer = spec.sanitizers[CWECategory.XSS]
        assert "escape" in xss_sanitizer.sanitizer_patterns

    def test_validate_path_xss_vulnerable(self):
        """Base: XSS 취약점 감지"""
        spec = SecuritySpec()

        path = DataflowPath(
            source="request.args['input']",
            sink="render_template_string(x)",
            path_nodes=["request.args", "x", "render_template_string"],
            has_sanitizer=False,
        )

        violation = spec.validate_path(path, CWECategory.XSS)

        assert violation is not None
        assert violation.cwe == CWECategory.XSS
        assert violation.severity in ["critical", "high"]
        assert "XSS" in violation.description or "CWE-79" in violation.description

    def test_validate_path_xss_safe(self):
        """Base: XSS 안전 (sanitizer 있음)"""
        spec = SecuritySpec()

        path = DataflowPath(
            source="request.args['input']",
            sink="render_template_string(x)",
            path_nodes=["request.args", "escape", "render_template_string"],
            has_sanitizer=True,
            sanitizers_used=["escape"],
        )

        violation = spec.validate_path(path, CWECategory.XSS)

        assert violation is None  # 안전

    def test_validate_path_sql_injection_vulnerable(self):
        """Base: SQL Injection 취약점 감지"""
        spec = SecuritySpec()

        path = DataflowPath(
            source="request.args['id']",
            sink="cursor.execute(query)",
            path_nodes=["request.args", "query", "cursor.execute"],
            has_sanitizer=False,
        )

        violation = spec.validate_path(path, CWECategory.SQL_INJECTION)

        assert violation is not None
        assert violation.cwe == CWECategory.SQL_INJECTION
        assert violation.severity == "critical"

    def test_validate_path_sql_injection_safe(self):
        """Base: SQL Injection 안전 (parameterize)"""
        spec = SecuritySpec()

        path = DataflowPath(
            source="request.args['id']",
            sink="cursor.execute(query)",
            path_nodes=["request.args", "parameterize", "cursor.execute"],
            has_sanitizer=True,
            sanitizers_used=["parameterize"],
        )

        violation = spec.validate_path(path, CWECategory.SQL_INJECTION)

        assert violation is None

    def test_validate_path_os_command_vulnerable(self):
        """Base: OS Command Injection 감지"""
        spec = SecuritySpec()

        path = DataflowPath(
            source="os.environ['PATH']",
            sink="os.system(cmd)",
            path_nodes=["os.environ", "cmd", "os.system"],
            has_sanitizer=False,
        )

        violation = spec.validate_path(path, CWECategory.OS_COMMAND)

        assert violation is not None
        assert violation.severity == "critical"

    def test_validate_paths_batch(self):
        """Base: 여러 경로 일괄 검증"""
        spec = SecuritySpec()

        paths = [
            DataflowPath(
                "request.args",
                "render_template_string",
                ["request.args", "render_template_string"],
                False,
            ),
            DataflowPath(
                "request.form",
                "Markup",
                ["request.form", "Markup"],
                False,
            ),
        ]

        result = spec.validate_paths(paths, CWECategory.XSS)

        assert not result.passed
        assert len(result.violations) == 2
        assert result.paths_checked == 2
        assert result.vulnerable_paths == 2

    def test_validate_paths_all_safe(self):
        """Base: 모든 경로 안전"""
        spec = SecuritySpec()

        paths = [
            DataflowPath(
                "request.args",
                "render_template_string",
                ["request.args", "escape", "render_template_string"],
                True,
                ["escape"],
            ),
        ]

        result = spec.validate_paths(paths, CWECategory.XSS)

        assert result.passed
        assert len(result.violations) == 0

    def test_validate_all_cwes(self):
        """Integration: 모든 CWE 카테고리 검증"""
        spec = SecuritySpec()

        paths_by_cwe = {
            CWECategory.XSS: [
                DataflowPath("request.args", "render_template_string", [], False),
            ],
            CWECategory.SQL_INJECTION: [
                DataflowPath("request.form", "execute", [], False),
            ],
        }

        result = spec.validate_all_cwes(paths_by_cwe)

        assert not result.passed
        assert len(result.violations) == 2
        assert result.paths_checked == 2

    def test_add_custom_source(self):
        """Base: 커스텀 Source 추가"""
        spec = SecuritySpec()

        spec.add_custom_source(CWECategory.XSS, {"custom.input"})

        assert "custom.input" in spec.sources[CWECategory.XSS].source_patterns
        assert "request.args" in spec.sources[CWECategory.XSS].source_patterns  # 기존 유지

    def test_add_custom_sink(self):
        """Base: 커스텀 Sink 추가"""
        spec = SecuritySpec()

        spec.add_custom_sink(CWECategory.SQL_INJECTION, {"custom.execute"})

        assert "custom.execute" in spec.sinks[CWECategory.SQL_INJECTION].sink_patterns

    def test_add_custom_sanitizer(self):
        """Base: 커스텀 Sanitizer 추가"""
        spec = SecuritySpec()

        spec.add_custom_sanitizer(CWECategory.XSS, {"custom.sanitize"})

        assert "custom.sanitize" in spec.sanitizers[CWECategory.XSS].sanitizer_patterns

    def test_severity_calculation_direct_path(self):
        """Edge: 직접 연결 경로는 심각도 상승"""
        spec = SecuritySpec()

        # XSS는 기본 "high"이지만 직접 연결이면 "critical"
        path = DataflowPath(
            "request.args",
            "render_template_string",
            ["request.args", "render_template_string"],  # 길이 2
            False,
        )

        violation = spec.validate_path(path, CWECategory.XSS)

        assert violation.severity == "critical"  # 직접 연결로 인해 상승

    def test_remediation_suggestions(self):
        """Base: 수정 제안 확인"""
        spec = SecuritySpec()

        path = DataflowPath("request.args", "execute", [], False)
        violation = spec.validate_path(path, CWECategory.SQL_INJECTION)

        assert violation.remediation is not None
        assert "parameterized" in violation.remediation.lower() or "ORM" in violation.remediation

    def test_unknown_cwe_raises(self):
        """Edge: 알 수 없는 CWE는 에러"""
        spec = SecuritySpec()

        # 등록되지 않은 CWE
        path = DataflowPath("src", "sink", [], False)

        # 임의의 CWE (등록 안됨)
        # XXE는 sources에 없음
        with pytest.raises(ValueError, match="Unknown CWE"):
            spec.validate_path(path, CWECategory.XXE)


# Extreme Cases
class TestExtremeCases:
    """극한 케이스"""

    def test_1000_paths_validation(self):
        """Extreme: 1000개 경로 검증"""
        spec = SecuritySpec()

        paths = [DataflowPath(f"source{i}", f"sink{i}", [], False) for i in range(1000)]

        # 실제 source/sink 패턴과 맞지 않아서 violations 0
        result = spec.validate_paths(paths, CWECategory.XSS)

        assert result.paths_checked == 1000

    def test_very_long_pattern_names(self):
        """Edge: 매우 긴 패턴 이름"""
        spec = SecuritySpec()

        long_pattern = "a" * 500 + ".request.args"
        spec.add_custom_source(CWECategory.XSS, {long_pattern})

        assert long_pattern in spec.sources[CWECategory.XSS].source_patterns

    def test_unicode_in_patterns(self):
        """Edge: Unicode 패턴"""
        spec = SecuritySpec()

        spec.add_custom_source(CWECategory.XSS, {"요청.인자"})

        assert "요청.인자" in spec.sources[CWECategory.XSS].source_patterns

    def test_all_cwe_categories(self):
        """Integration: 모든 CWE 카테고리 커버"""
        spec = SecuritySpec()

        # 모든 지원 CWE 확인
        supported_cwes = {
            CWECategory.XSS,
            CWECategory.SQL_INJECTION,
            CWECategory.OS_COMMAND,
            CWECategory.PATH_TRAVERSAL,
        }

        for cwe in supported_cwes:
            assert cwe in spec.sources or cwe in spec.sinks


@pytest.mark.parametrize(
    "cwe,source,sink,path_length,expected_critical",
    [
        (CWECategory.SQL_INJECTION, "request.args", "execute", 2, True),
        (CWECategory.OS_COMMAND, "os.environ", "os.system", 2, True),
        # XSS와 PATH_TRAVERSAL도 직접 경로(길이 2)면 critical로 상승
        (CWECategory.XSS, "request.form", "Markup", 2, True),
        (CWECategory.PATH_TRAVERSAL, "request.files", "open", 2, True),
        # 경로 길이가 길면 (3+) high 유지
        (CWECategory.XSS, "request.form", "Markup", 5, False),
    ],
)
def test_severity_matrix(cwe, source, sink, path_length, expected_critical):
    """Parametrize: 심각도 매트릭스"""
    spec = SecuritySpec()

    path_nodes = [f"node{i}" for i in range(path_length)]
    path = DataflowPath(source, sink, path_nodes, False)
    violation = spec.validate_path(path, cwe)

    if violation:
        is_critical = violation.severity == "critical"
        assert is_critical == expected_critical
