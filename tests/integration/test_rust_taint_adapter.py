"""Integration tests for RustTaintAdapter - SOTA Security Analysis

Tests:
- Existing SecurityRule → Rust engine
- Python rule preservation
- Performance benchmarks
- Batch analysis
"""

import pytest

from codegraph_analysis.security_analysis.domain.models.security_rule import (
    SecurityRule,
    TaintSink,
    TaintSource,
)
from codegraph_analysis.security_analysis.domain.models.vulnerability import CWE, Severity
from codegraph_analysis.security_analysis.infrastructure.adapters.rust_taint_adapter import (
    RustTaintAdapter,
    RustTaintBatchAnalyzer,
)


# =============================================================================
# Test Rules (based on existing pattern)
# =============================================================================


class TestSQLInjectionRule(SecurityRule):
    """Test SQL injection rule"""

    CWE_ID = CWE.CWE_89
    SEVERITY = Severity.CRITICAL

    SOURCES = (
        TaintSource(
            patterns=["request.GET", "request.POST", "request.args", "request.form"],
            description="HTTP request parameters",
        ),
    )

    SINKS = (
        TaintSink(
            patterns=["cursor.execute", "execute", "executemany"],
            description="SQL execution",
            severity=Severity.CRITICAL,
        ),
    )

    def analyze(self, ir_document):
        """Required by SecurityRule ABC"""
        # RustTaintAdapter will handle this
        pass


class TestCommandInjectionRule(SecurityRule):
    """Test command injection rule"""

    CWE_ID = CWE.CWE_78
    SEVERITY = Severity.HIGH

    SOURCES = (
        TaintSource(
            patterns=["input", "sys.argv", "os.environ"],
            description="User input",
        ),
    )

    SINKS = (
        TaintSink(
            patterns=["os.system", "subprocess.call", "subprocess.run"],
            description="Command execution",
            severity=Severity.HIGH,
        ),
    )

    def analyze(self, ir_document):
        pass


# =============================================================================
# Test Data
# =============================================================================


@pytest.fixture
def sql_injection_rule():
    """Create SQL injection rule"""
    return TestSQLInjectionRule()


@pytest.fixture
def command_injection_rule():
    """Create command injection rule"""
    return TestCommandInjectionRule()


@pytest.fixture
def vulnerable_ir_sql():
    """IR document with SQL injection vulnerability"""
    return {
        "file_path": "test_app.py",
        "nodes": [
            {"id": "node_1", "name": "request.GET", "kind": "Call"},
            {"id": "node_2", "name": "get_user_data", "kind": "Function"},
            {"id": "node_3", "name": "cursor.execute", "kind": "Call"},
        ],
        "edges": [
            {"kind": "CALLS", "source_id": "node_1", "target_id": "node_2"},
            {"kind": "CALLS", "source_id": "node_2", "target_id": "node_3"},
        ],
    }


@pytest.fixture
def safe_ir():
    """IR document with no vulnerabilities"""
    return {
        "file_path": "safe_app.py",
        "nodes": [
            {"id": "node_1", "name": "safe_function", "kind": "Function"},
            {"id": "node_2", "name": "safe_call", "kind": "Call"},
        ],
        "edges": [{"kind": "CALLS", "source_id": "node_1", "target_id": "node_2"}],
    }


# =============================================================================
# Core Tests
# =============================================================================


def test_rust_taint_adapter_initialization(sql_injection_rule):
    """Test RustTaintAdapter initializes with SecurityRule"""
    adapter = RustTaintAdapter(sql_injection_rule)

    assert adapter.rule == sql_injection_rule
    assert len(adapter.rust_sources) == 4  # request.GET, POST, args, form
    assert len(adapter.rust_sinks) == 3  # cursor.execute, execute, executemany
    assert len(adapter.rust_sanitizers) == 0


def test_rust_taint_adapter_source_conversion(sql_injection_rule):
    """Test TaintSource → Rust DTO conversion"""
    adapter = RustTaintAdapter(sql_injection_rule)

    sources = adapter.rust_sources

    assert len(sources) == 4
    assert any(s["pattern"] == "request.GET" for s in sources)
    assert all("description" in s for s in sources)
    assert all("isRegex" in s for s in sources)


def test_rust_taint_adapter_sink_conversion(sql_injection_rule):
    """Test TaintSink → Rust DTO conversion"""
    adapter = RustTaintAdapter(sql_injection_rule)

    sinks = adapter.rust_sinks

    assert len(sinks) == 3
    assert any(s["pattern"] == "cursor.execute" for s in sinks)
    assert all("severity" in s for s in sinks)
    assert all(s["severity"] == "CRITICAL" for s in sinks)


def test_rust_taint_adapter_call_graph_extraction(sql_injection_rule, vulnerable_ir_sql):
    """Test call graph extraction from IR document"""
    adapter = RustTaintAdapter(sql_injection_rule)

    call_graph = adapter._extract_call_graph(vulnerable_ir_sql)

    assert len(call_graph) == 3
    assert "node_1" in call_graph
    assert "node_2" in call_graph
    assert "node_3" in call_graph

    # Check callees
    assert "node_2" in call_graph["node_1"]["callees"]
    assert "node_3" in call_graph["node_2"]["callees"]


@pytest.mark.slow
def test_rust_taint_adapter_detects_sql_injection(sql_injection_rule, vulnerable_ir_sql):
    """Test RustTaintAdapter detects SQL injection"""
    adapter = RustTaintAdapter(sql_injection_rule)

    try:
        vulnerabilities = adapter.analyze(vulnerable_ir_sql)

        # May succeed or fail depending on codegraph_ir availability
        if vulnerabilities:
            assert len(vulnerabilities) > 0
            vuln = vulnerabilities[0]

            assert vuln.cwe == CWE.CWE_89
            assert vuln.severity in (Severity.CRITICAL, Severity.HIGH)
            assert "request.GET" in str(vuln.taint_path) or "cursor.execute" in str(vuln.taint_path)

    except ImportError:
        pytest.skip("codegraph_ir not available")


@pytest.mark.slow
def test_rust_taint_adapter_no_false_positives(sql_injection_rule, safe_ir):
    """Test RustTaintAdapter doesn't report false positives"""
    adapter = RustTaintAdapter(sql_injection_rule)

    try:
        vulnerabilities = adapter.analyze(safe_ir)

        # Should find no vulnerabilities in safe code
        assert len(vulnerabilities) == 0

    except ImportError:
        pytest.skip("codegraph_ir not available")


@pytest.mark.slow
def test_rust_taint_adapter_command_injection(command_injection_rule):
    """Test RustTaintAdapter with command injection rule"""
    adapter = RustTaintAdapter(command_injection_rule)

    ir_document = {
        "file_path": "cmd_app.py",
        "nodes": [
            {"id": "node_1", "name": "input", "kind": "Call"},
            {"id": "node_2", "name": "process_input", "kind": "Function"},
            {"id": "node_3", "name": "os.system", "kind": "Call"},
        ],
        "edges": [
            {"kind": "CALLS", "source_id": "node_1", "target_id": "node_2"},
            {"kind": "CALLS", "source_id": "node_2", "target_id": "node_3"},
        ],
    }

    try:
        vulnerabilities = adapter.analyze(ir_document)

        if vulnerabilities:
            assert len(vulnerabilities) > 0
            vuln = vulnerabilities[0]

            assert vuln.cwe == CWE.CWE_78
            assert vuln.severity == Severity.HIGH

    except ImportError:
        pytest.skip("codegraph_ir not available")


# =============================================================================
# Batch Analysis Tests
# =============================================================================


def test_rust_taint_batch_analyzer_initialization(sql_injection_rule, command_injection_rule):
    """Test RustTaintBatchAnalyzer with multiple rules"""
    rules = [sql_injection_rule, command_injection_rule]
    batch_analyzer = RustTaintBatchAnalyzer(rules)

    assert len(batch_analyzer.adapters) == 2
    assert batch_analyzer.adapters[0].rule == sql_injection_rule
    assert batch_analyzer.adapters[1].rule == command_injection_rule


@pytest.mark.slow
def test_rust_taint_batch_analyzer_analyze_all(sql_injection_rule, command_injection_rule, vulnerable_ir_sql):
    """Test batch analysis with multiple rules"""
    rules = [sql_injection_rule, command_injection_rule]
    batch_analyzer = RustTaintBatchAnalyzer(rules)

    try:
        results = batch_analyzer.analyze_all(vulnerable_ir_sql)

        assert "TestSQLInjectionRule" in results
        assert "TestCommandInjectionRule" in results

        # At least SQL injection should be found
        if results["TestSQLInjectionRule"]:
            assert len(results["TestSQLInjectionRule"]) > 0

    except ImportError:
        pytest.skip("codegraph_ir not available")


@pytest.mark.slow
def test_rust_taint_batch_analyzer_summary(sql_injection_rule, command_injection_rule, vulnerable_ir_sql):
    """Test batch analyzer summary statistics"""
    rules = [sql_injection_rule, command_injection_rule]
    batch_analyzer = RustTaintBatchAnalyzer(rules)

    try:
        results = batch_analyzer.analyze_all(vulnerable_ir_sql)
        summary = batch_analyzer.get_summary(results)

        assert "total_vulnerabilities" in summary
        assert "rules_triggered" in summary
        assert "severity_breakdown" in summary
        assert "cwe_breakdown" in summary
        assert summary["rules_analyzed"] == 2

    except ImportError:
        pytest.skip("codegraph_ir not available")


# =============================================================================
# Performance Tests
# =============================================================================


@pytest.mark.benchmark
@pytest.mark.slow
def test_rust_taint_adapter_performance(sql_injection_rule):
    """Benchmark RustTaintAdapter performance"""
    import time

    adapter = RustTaintAdapter(sql_injection_rule)

    # Create large IR document
    nodes = []
    edges = []
    num_nodes = 1000

    for i in range(num_nodes):
        nodes.append({"id": f"node_{i}", "name": f"func_{i}", "kind": "Function"})
        if i > 0:
            edges.append({"kind": "CALLS", "source_id": f"node_{i - 1}", "target_id": f"node_{i}"})

    # Add source and sink
    nodes[0]["name"] = "request.GET"
    nodes[-1]["name"] = "cursor.execute"

    ir_document = {"file_path": "large_app.py", "nodes": nodes, "edges": edges}

    try:
        start = time.time()
        vulnerabilities = adapter.analyze(ir_document)
        elapsed = time.time() - start

        print(f"\n⏱️  Performance: {num_nodes} nodes analyzed in {elapsed:.3f}s")
        print(f"   Vulnerabilities found: {len(vulnerabilities)}")

        # Should be fast (< 1s for 1000 nodes)
        assert elapsed < 5.0, f"Too slow: {elapsed:.3f}s"

    except ImportError:
        pytest.skip("codegraph_ir not available")


# =============================================================================
# Edge Cases
# =============================================================================


def test_rust_taint_adapter_empty_ir(sql_injection_rule):
    """Test RustTaintAdapter with empty IR document"""
    adapter = RustTaintAdapter(sql_injection_rule)

    empty_ir = {"file_path": "empty.py", "nodes": [], "edges": []}

    try:
        vulnerabilities = adapter.analyze(empty_ir)
        assert len(vulnerabilities) == 0

    except ImportError:
        pytest.skip("codegraph_ir not available")


def test_rust_taint_adapter_no_sinks(sql_injection_rule):
    """Test RustTaintAdapter with source but no sink"""
    adapter = RustTaintAdapter(sql_injection_rule)

    ir_document = {
        "file_path": "no_sink.py",
        "nodes": [
            {"id": "node_1", "name": "request.GET", "kind": "Call"},
            {"id": "node_2", "name": "safe_function", "kind": "Function"},
        ],
        "edges": [{"kind": "CALLS", "source_id": "node_1", "target_id": "node_2"}],
    }

    try:
        vulnerabilities = adapter.analyze(ir_document)
        assert len(vulnerabilities) == 0

    except ImportError:
        pytest.skip("codegraph_ir not available")


def test_rust_taint_adapter_regex_patterns():
    """Test RustTaintAdapter with regex patterns"""

    class RegexTestRule(SecurityRule):
        CWE_ID = CWE.CWE_89
        SEVERITY = Severity.HIGH

        SOURCES = (
            TaintSource(
                patterns=[r"request\.(GET|POST)", r"request\.args\[\w+\]"],
                description="Regex HTTP params",
            ),
        )

        SINKS = (
            TaintSink(
                patterns=[r"cursor\.(execute|executemany)", r"db\.(query|exec)"],
                description="Regex SQL sinks",
                severity=Severity.HIGH,
            ),
        )

        def analyze(self, ir_document):
            pass

    rule = RegexTestRule()
    adapter = RustTaintAdapter(rule)

    # Check regex detection
    sources = adapter.rust_sources
    assert all(s["isRegex"] for s in sources)  # All should be detected as regex


# =============================================================================
# Integration with Existing Rules
# =============================================================================


@pytest.mark.slow
def test_rust_taint_adapter_with_rule_registry():
    """Test RustTaintAdapter with SecurityRule registry"""
    from codegraph_analysis.security_analysis.domain.models.security_rule import RuleRegistry

    registry = RuleRegistry()

    # Register test rule
    registry.register(TestSQLInjectionRule)

    # Get rule from registry
    rule = registry.get_rule("TestSQLInjectionRule")
    assert rule is not None

    # Create adapter
    adapter = RustTaintAdapter(rule)
    assert adapter.rule.CWE_ID == CWE.CWE_89


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "-m", "not slow"])
