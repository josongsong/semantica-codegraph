"""
Test Enhanced Error Messages

Verifies TaintTyper-style error messages with:
- Detailed explanations
- Fix suggestions
- Safe code examples
- References
"""

import pytest

from codegraph_engine.code_foundation.infrastructure.analyzers.deep_security_analyzer import (
    SecurityIssue,
    Severity,
)
from codegraph_engine.code_foundation.infrastructure.analyzers.security_messages import (
    SECURITY_MESSAGES,
    get_enhanced_message,
)


class TestEnhancedErrorMessages:
    """Test enhanced error message functionality"""

    def test_security_issue_has_enhanced_fields(self):
        """Test SecurityIssue has all enhanced fields"""
        issue = SecurityIssue(
            pattern="cursor.execute(query)",
            issue_type="sql_injection",
            severity=Severity.CRITICAL,
            location="line 10",
            message="SQL Injection detected",
            explanation="SQL Injection allows attackers...",
            fix_suggestion="Use parameterized queries",
            safe_examples=["cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"],
            references=["CWE-89"],
        )

        assert issue.explanation is not None
        assert issue.fix_suggestion is not None
        assert len(issue.safe_examples) > 0
        assert len(issue.references) > 0

    def test_format_detailed_message(self):
        """Test detailed message formatting"""
        issue = SecurityIssue(
            pattern="eval(user_input)",
            issue_type="code_injection",
            severity=Severity.CRITICAL,
            location="line 42",
            message="Code Injection",
            explanation="eval() allows arbitrary code execution",
            fix_suggestion="Use ast.literal_eval() instead",
            safe_examples=["ast.literal_eval(user_input)"],
            references=["CWE-94"],
        )

        detailed = issue.format_detailed()

        # Should contain all components
        assert "SECURITY ISSUE:" in detailed
        assert "CODE_INJECTION" in detailed
        assert "CRITICAL" in detailed
        assert "line 42" in detailed
        assert "eval(user_input)" in detailed
        assert "eval() allows arbitrary code execution" in detailed
        assert "ast.literal_eval()" in detailed
        assert "CWE-94" in detailed

    def test_get_enhanced_message_sql_injection(self):
        """Test SQL injection enhanced message"""
        msg = get_enhanced_message("sql_injection")

        assert "explanation" in msg
        assert "fix" in msg
        assert "examples" in msg
        assert "references" in msg

        # Check content
        assert "SQL Injection" in msg["explanation"]
        assert "parameterized" in msg["fix"].lower()
        assert len(msg["examples"]) > 0
        assert any("CWE" in ref for ref in msg["references"])

    def test_get_enhanced_message_command_injection(self):
        """Test command injection enhanced message"""
        msg = get_enhanced_message("command_injection")

        assert "shell" in msg["explanation"].lower()
        assert "subprocess" in msg["fix"].lower()
        assert len(msg["examples"]) > 0

    def test_get_enhanced_message_code_injection(self):
        """Test code injection enhanced message"""
        msg = get_enhanced_message("code_injection")

        assert "eval" in msg["explanation"].lower()
        assert "ast.literal_eval" in msg["fix"] or "json.loads" in msg["fix"]
        assert len(msg["examples"]) > 0

    def test_get_enhanced_message_weak_crypto(self):
        """Test weak crypto enhanced message"""
        msg = get_enhanced_message("weak_hash")

        assert "MD5" in msg["explanation"] or "SHA1" in msg["explanation"]
        assert "bcrypt" in msg["fix"] or "SHA-256" in msg["fix"]
        assert len(msg["examples"]) > 0

    def test_get_enhanced_message_unknown_type(self):
        """Test fallback for unknown issue type"""
        msg = get_enhanced_message("unknown_vulnerability_type")

        # Should return generic message
        assert "explanation" in msg
        assert "fix" in msg
        assert msg["explanation"] is not None

    def test_all_message_types_have_required_fields(self):
        """Test all message types have required fields"""
        for issue_type, msg in SECURITY_MESSAGES.items():
            assert "explanation" in msg, f"{issue_type} missing explanation"
            assert "fix" in msg, f"{issue_type} missing fix"
            assert "examples" in msg, f"{issue_type} missing examples"
            assert "references" in msg, f"{issue_type} missing references"

            # All should have content
            assert msg["explanation"], f"{issue_type} has empty explanation"
            assert msg["fix"], f"{issue_type} has empty fix"
            assert len(msg["examples"]) > 0, f"{issue_type} has no examples"
            assert len(msg["references"]) > 0, f"{issue_type} has no references"

    def test_message_quality_sql_injection(self):
        """Test SQL injection message quality"""
        msg = get_enhanced_message("sql_injection")

        # Should explain the risk
        assert "inject" in msg["explanation"].lower()
        assert "data" in msg["explanation"].lower()

        # Should provide specific fix
        assert "?" in msg["examples"][0] or "parameterized" in msg["fix"].lower()

        # Should reference standards
        assert any("CWE" in ref or "OWASP" in ref for ref in msg["references"])

    def test_message_formatting_with_taint_path(self):
        """Test message formatting with taint path"""
        from codegraph_engine.code_foundation.infrastructure.analyzers.interprocedural_taint import (
            TaintPath,
        )

        taint_path = TaintPath(
            source="request.GET['id']",
            sink="cursor.execute(query)",
            path=["process_input", "build_query"],
            confidence=0.9,
        )

        issue = SecurityIssue(
            pattern="request.GET -> execute",
            issue_type="sql_injection",
            severity=Severity.CRITICAL,
            location="line 50",
            message="SQL Injection via taint flow",
            taint_path=taint_path,
            explanation="Tainted data flows to SQL query",
            fix_suggestion="Use parameterized queries",
        )

        detailed = issue.format_detailed()

        # Should include taint flow
        assert "Taint Flow:" in detailed
        assert "request.GET" in detailed
        assert "cursor.execute" in detailed
        assert "process_input" in detailed


class TestMessageCoverage:
    """Test message coverage for all vulnerability types"""

    @pytest.mark.parametrize(
        "issue_type",
        [
            "sql_injection",
            "command_injection",
            "code_injection",
            "path_traversal",
            "ssrf",
            "xss",
            "weak_hash",
            "weak_key",
            "insecure_cookie",
            "hardcoded_secret",
            "taint_flow",
        ],
    )
    def test_has_message_for_type(self, issue_type):
        """Test each vulnerability type has a message"""
        msg = get_enhanced_message(issue_type)

        assert msg is not None
        assert msg["explanation"]
        assert msg["fix"]
        assert len(msg["examples"]) > 0
        assert len(msg["references"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
