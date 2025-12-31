"""
RequestAuditLog Tests (RFC-027 Section 9.1)

Test coverage:
- RequestAuditLog validation
- to_replay_entry() method
- JSON serialization
- Edge cases (empty fields, large data)

Testing Strategy:
- Unit tests (model validation)
- Serialization tests
- Edge cases
"""

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from apps.orchestrator.orchestrator.domain.rfc_replay.models import RequestAuditLog

# ============================================================
# Base Case Tests
# ============================================================


def test_request_audit_log_valid():
    """Test valid RequestAuditLog (base case)"""
    log = RequestAuditLog(
        request_id="req_test123",
        input_spec={"intent": "analyze"},
        resolved_spec={"intent": "analyze", "limits": {}},
        engine_versions={"sccp": "1.0.0"},
        index_digests={"chunk": "sha256:abc"},
        timestamp=datetime(2025, 12, 16, 10, 30, 0),
        duration_ms=234.5,
    )

    assert log.request_id == "req_test123"
    assert log.duration_ms == 234.5


def test_to_replay_entry():
    """Test to_replay_entry() method"""
    log = RequestAuditLog(
        request_id="req_test",
        input_spec={"intent": "analyze"},
        resolved_spec={},
        timestamp=datetime(2025, 12, 16, 10, 30, 0),
        duration_ms=100.0,
    )

    replay_data = log.to_replay_entry()

    assert replay_data["request_id"] == "req_test"
    assert replay_data["input_spec"] == {"intent": "analyze"}
    assert replay_data["timestamp"] == "2025-12-16T10:30:00"


# ============================================================
# Validation Tests
# ============================================================


def test_invalid_request_id():
    """Test invalid request_id"""
    with pytest.raises(ValidationError):
        RequestAuditLog(
            request_id="invalid",  # Must start with req_
            input_spec={},
            resolved_spec={},
            timestamp=datetime.now(),
            duration_ms=100.0,
        )


def test_negative_duration():
    """Test negative duration_ms"""
    with pytest.raises(ValidationError):
        RequestAuditLog(
            request_id="req_test",
            input_spec={},
            resolved_spec={},
            timestamp=datetime.now(),
            duration_ms=-1.0,  # Must be >= 0
        )


# ============================================================
# Edge Cases
# ============================================================


def test_empty_optional_fields():
    """Test with empty optional fields"""
    log = RequestAuditLog(
        request_id="req_empty",
        input_spec={},
        resolved_spec={},
        engine_versions={},  # Empty OK
        index_digests={},  # Empty OK
        llm_decisions=[],  # Empty OK
        tool_trace=[],  # Empty OK
        outputs={},  # Empty OK
        timestamp=datetime.now(),
        duration_ms=0.1,
    )

    assert len(log.engine_versions) == 0
    assert len(log.llm_decisions) == 0


def test_json_serialization():
    """Test JSON serialization"""
    log = RequestAuditLog(
        request_id="req_json",
        input_spec={"test": "data"},
        resolved_spec={},
        timestamp=datetime(2025, 12, 16, 10, 30, 0),
        duration_ms=100.0,
    )

    # to_replay_entry should be JSON-serializable
    replay_data = log.to_replay_entry()
    json_str = json.dumps(replay_data)

    assert "req_json" in json_str


def test_immutable():
    """Test RequestAuditLog is frozen (immutable)"""
    log = RequestAuditLog(
        request_id="req_test",
        input_spec={},
        resolved_spec={},
        timestamp=datetime.now(),
        duration_ms=100.0,
    )

    with pytest.raises(ValidationError):
        log.duration_ms = 200.0
