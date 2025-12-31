"""Replay & Audit Domain Models"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RequestAuditLog:
    """
    RFC 요청 감사 로그 (Replay용).

    모든 RFC 요청은 재현 가능해야 함 (Deterministic Replay).
    """

    request_id: str

    # Input
    input_spec: dict[str, Any]
    resolved_spec: dict[str, Any]

    # Engine State (Snapshot at execution time)
    engine_versions: dict[str, str] = field(default_factory=dict)  # {"sccp": "1.2.0", "taint": "3.0.1"}
    index_digests: dict[str, str] = field(default_factory=dict)  # {"chunk_index": "sha256:abc123"}

    # LLM Decisions (Bias Trace)
    llm_decisions: list[dict[str, Any]] = field(default_factory=list)

    # Tool Trace
    tool_trace: list[dict[str, Any]] = field(default_factory=list)

    # Output
    outputs: dict[str, Any] = field(default_factory=dict)

    # Metadata
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0

    # User context
    user_id: str | None = None
    session_id: str | None = None


@dataclass
class ReplayEntry:
    """Replay 실행 엔트리"""

    replay_id: str
    original_request_id: str
    replay_timestamp: datetime = field(default_factory=datetime.now)
    status: str = "pending"  # pending, running, completed, failed
    diff: dict[str, Any] | None = None  # 원본 vs 재실행 차이
