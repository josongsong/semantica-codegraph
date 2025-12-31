"""Integration tests for security pattern-based plugins.

Tests pattern loading and plugin usage with YAML-defined rules.
"""

import pytest

from codegraph_analysis.security import CryptoPlugin
from codegraph_analysis.security.patterns import load_all_patterns, load_pattern


def test_load_crypto_patterns():
    """Test loading crypto patterns from YAML."""
    patterns = load_pattern("crypto")

    assert "patterns" in patterns
    assert "weak_hash" in patterns["patterns"]
    assert "weak_cipher" in patterns["patterns"]

    # Check weak_hash pattern
    weak_hash = patterns["patterns"]["weak_hash"]
    assert weak_hash["severity"] == "HIGH"
    assert weak_hash["cwe"] == "CWE-327"
    assert "hashlib.md5" in weak_hash["functions"]
    assert "hashlib.sha1" in weak_hash["functions"]


def test_load_auth_patterns():
    """Test loading auth patterns from YAML."""
    patterns = load_pattern("auth")

    assert "patterns" in patterns
    assert "missing_authentication" in patterns["patterns"]
    assert "hardcoded_credentials" in patterns["patterns"]

    # Check missing_authentication pattern
    missing_auth = patterns["patterns"]["missing_authentication"]
    assert missing_auth["severity"] == "HIGH"
    assert missing_auth["cwe"] == "CWE-306"


def test_load_injection_patterns():
    """Test loading injection patterns from YAML."""
    patterns = load_pattern("injection")

    assert "patterns" in patterns
    assert "sql_injection" in patterns["patterns"]
    assert "command_injection" in patterns["patterns"]
    assert "xss" in patterns["patterns"]

    # Check SQL injection pattern
    sql_injection = patterns["patterns"]["sql_injection"]
    assert sql_injection["severity"] == "CRITICAL"
    assert sql_injection["cwe"] == "CWE-89"
    assert "cursor.execute" in sql_injection["sinks"]


def test_load_all_patterns():
    """Test loading all patterns at once."""
    all_patterns = load_all_patterns()

    assert "crypto" in all_patterns
    assert "auth" in all_patterns
    assert "injection" in all_patterns

    # Verify structure
    assert "patterns" in all_patterns["crypto"]
    assert "patterns" in all_patterns["auth"]
    assert "patterns" in all_patterns["injection"]


def test_crypto_plugin_initialization():
    """Test CryptoPlugin initializes with patterns."""
    plugin = CryptoPlugin()

    assert plugin.name() == "crypto"
    assert plugin.version() == "1.0.0"
    assert plugin.patterns is not None
    assert "weak_hash" in plugin.patterns


def test_crypto_plugin_detects_md5():
    """Test CryptoPlugin detects MD5 usage."""
    plugin = CryptoPlugin()

    # Mock IR with MD5 call
    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "hashlib.md5",
                    "location": {"file": "test.py", "line": 10, "column": 5},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 1
    assert findings[0]["severity"] == "HIGH"
    assert findings[0]["category"] == "weak-crypto"
    assert findings[0]["cwe"] == "CWE-327"
    assert "md5" in findings[0]["message"].lower()
    assert "SHA-256" in findings[0]["remediation"]


def test_crypto_plugin_detects_sha1():
    """Test CryptoPlugin detects SHA1 usage."""
    plugin = CryptoPlugin()

    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "hashlib.sha1",
                    "location": {"file": "legacy.py", "line": 42},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 1
    assert findings[0]["severity"] == "HIGH"
    assert "sha1" in findings[0]["message"].lower()


def test_crypto_plugin_detects_weak_cipher():
    """Test CryptoPlugin detects weak cipher (DES)."""
    plugin = CryptoPlugin()

    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "DES.new",
                    "location": {"file": "crypto.py", "line": 20},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 1
    assert findings[0]["severity"] == "HIGH"
    assert "DES" in findings[0]["message"]
    assert "AES-256" in findings[0]["remediation"]


def test_crypto_plugin_detects_weak_random():
    """Test CryptoPlugin detects weak random generator."""
    plugin = CryptoPlugin()

    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "random.random",
                    "location": {"file": "game.py", "line": 15},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 1
    assert findings[0]["severity"] == "MEDIUM"
    assert findings[0]["cwe"] == "CWE-338"
    assert "random" in findings[0]["message"].lower()


def test_crypto_plugin_detects_hardcoded_key():
    """Test CryptoPlugin detects hardcoded key."""
    plugin = CryptoPlugin()

    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Assign",
                    "target": "secret_key",
                    "location": {"file": "config.py", "line": 5},
                }
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 1
    assert findings[0]["severity"] == "CRITICAL"
    assert findings[0]["cwe"] == "CWE-798"
    assert "key" in findings[0]["message"].lower()


def test_crypto_plugin_multiple_issues():
    """Test CryptoPlugin detects multiple issues in one document."""
    plugin = CryptoPlugin()

    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "hashlib.md5",
                    "location": {"file": "app.py", "line": 10},
                },
                {
                    "kind": "Call",
                    "name": "random.randint",
                    "location": {"file": "app.py", "line": 15},
                },
                {
                    "kind": "Assign",
                    "target": "api_key",
                    "location": {"file": "app.py", "line": 20},
                },
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 3
    severities = [f["severity"] for f in findings]
    assert "HIGH" in severities
    assert "MEDIUM" in severities
    assert "CRITICAL" in severities


def test_crypto_plugin_no_issues():
    """Test CryptoPlugin returns empty list when no issues found."""
    plugin = CryptoPlugin()

    # IR with safe crypto
    ir_documents = [
        {
            "nodes": [
                {
                    "kind": "Call",
                    "name": "hashlib.sha256",  # Safe
                    "location": {"file": "secure.py", "line": 10},
                },
                {
                    "kind": "Call",
                    "name": "secrets.token_bytes",  # Safe
                    "location": {"file": "secure.py", "line": 15},
                },
            ]
        }
    ]

    findings = plugin.analyze(ir_documents)

    assert len(findings) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
