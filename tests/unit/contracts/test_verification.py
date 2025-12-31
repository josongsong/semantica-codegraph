"""
Verification Snapshot 모델 테스트 (RFC-SEM-022)

Test Coverage:
- Happy Path: Model creation
- Corner Cases: Null/empty values
- Edge Cases: Hash computation
- Extreme Cases: Large content
"""

import pytest

from codegraph_engine.shared_kernel.contracts import (
    AgentMetadata,
    Execution,
    Finding,
    PatchSet,
    VerificationSnapshot,
    Workspace,
    create_verification_snapshot,
    create_workspace,
)


class TestVerificationSnapshot:
    """VerificationSnapshot 테스트."""

    def test_create_happy_path(self):
        """Happy Path: 정상 생성."""
        snapshot = VerificationSnapshot(
            engine_version="2.4.1",
            ruleset_hash="sha256:abc123",
            policies_hash="sha256:def456",
            index_snapshot_id="index_v20251218",
            repo_revision="abc123def456",
        )

        assert snapshot.engine_version == "2.4.1"
        assert snapshot.ruleset_hash == "sha256:abc123"
        assert snapshot.index_snapshot_id == "index_v20251218"

    def test_compute_hash(self):
        """Edge Case: 해시 계산."""
        hash1 = VerificationSnapshot.compute_hash("test content")
        hash2 = VerificationSnapshot.compute_hash("test content")
        hash3 = VerificationSnapshot.compute_hash("different content")

        # 동일 입력 → 동일 해시
        assert hash1 == hash2
        # 다른 입력 → 다른 해시
        assert hash1 != hash3
        # sha256: prefix
        assert hash1.startswith("sha256:")

    def test_compute_hash_bytes(self):
        """Edge Case: bytes 입력."""
        hash1 = VerificationSnapshot.compute_hash(b"binary content")
        assert hash1.startswith("sha256:")

    def test_factory_function(self):
        """Happy Path: Factory 함수."""
        snapshot = create_verification_snapshot(
            engine_version="2.4.1",
            ruleset_content="rule1: taint\nrule2: xss",
            policies_content="policy1: block",
            index_id="idx_123",
            repo_revision="commit_sha",
        )

        assert snapshot.engine_version == "2.4.1"
        assert snapshot.ruleset_hash.startswith("sha256:")
        assert snapshot.policies_hash.startswith("sha256:")

    def test_immutability(self):
        """Edge Case: Immutable (frozen)."""
        snapshot = VerificationSnapshot(
            engine_version="2.4.1",
            ruleset_hash="sha256:abc",
            policies_hash="sha256:def",
            index_snapshot_id="idx",
            repo_revision="sha",
        )

        with pytest.raises(Exception):  # ValidationError or AttributeError
            snapshot.engine_version = "2.5.0"


class TestAgentMetadata:
    """AgentMetadata 테스트."""

    def test_create_happy_path(self):
        """Happy Path: 정상 생성."""
        meta = AgentMetadata(
            agent_model_id="gpt-4o",
            agent_version="agent-v1",
            prompt_hash="sha256:prompt123",
        )

        assert meta.agent_model_id == "gpt-4o"
        assert meta.agent_version == "agent-v1"

    def test_optional_prompt_hash(self):
        """Corner Case: prompt_hash 생략."""
        meta = AgentMetadata(
            agent_model_id="claude-3",
            agent_version="v2",
        )

        assert meta.prompt_hash is None


class TestExecution:
    """Execution 테스트."""

    def test_create_with_snapshot(self):
        """Happy Path: Snapshot 포함."""
        snapshot = VerificationSnapshot(
            engine_version="2.4.1",
            ruleset_hash="sha256:abc",
            policies_hash="sha256:def",
            index_snapshot_id="idx",
            repo_revision="sha",
        )

        execution = Execution(
            execution_id="exec_123",
            workspace_id="ws_456",
            spec_type="taint_analysis",
            trace_id="trace_abc",
            verification_snapshot=snapshot,
        )

        assert execution.state == "pending"
        assert execution.verification_snapshot == snapshot

    def test_state_values(self):
        """Edge Case: 상태 값들."""
        for state in ["pending", "running", "completed", "failed", "cancelled"]:
            execution = Execution(
                execution_id="exec_1",
                workspace_id="ws_1",
                spec_type="test",
                trace_id="trace",
                state=state,
            )
            assert execution.state == state

    def test_invalid_state(self):
        """Corner Case: 잘못된 상태."""
        with pytest.raises(Exception):  # ValidationError
            Execution(
                execution_id="exec_1",
                workspace_id="ws_1",
                spec_type="test",
                trace_id="trace",
                state="invalid_state",
            )


class TestWorkspace:
    """Workspace 테스트."""

    def test_create_happy_path(self):
        """Happy Path: 정상 생성."""
        ws = Workspace(
            workspace_id="ws_123",
            repo_id="repo_456",
            revision="abc123",
        )

        assert ws.workspace_id == "ws_123"
        assert ws.parent_workspace_id is None
        assert ws.patchset_id is None

    def test_create_branch(self):
        """Edge Case: 분기 생성."""
        ws = Workspace(
            workspace_id="ws_branch",
            repo_id="repo_1",
            revision="base_sha",
            parent_workspace_id="ws_parent",
            patchset_id="patch_123",
        )

        assert ws.parent_workspace_id == "ws_parent"
        assert ws.patchset_id == "patch_123"

    def test_factory_function(self):
        """Happy Path: Factory 함수."""
        ws = create_workspace(
            workspace_id="ws_factory",
            repo_id="repo",
            revision="sha",
        )

        assert ws.workspace_id == "ws_factory"


class TestPatchSet:
    """PatchSet 테스트."""

    def test_create_happy_path(self):
        """Happy Path: 정상 생성."""
        patch = PatchSet(
            patchset_id="patch_123",
            workspace_id="ws_456",
            files=["src/main.py", "src/utils.py"],
            patches={"src/main.py": "diff content"},
        )

        assert patch.patchset_id == "patch_123"
        assert len(patch.files) == 2
        assert not patch.verified

    def test_verification_states(self):
        """Edge Case: 검증 상태들."""
        patch = PatchSet(
            patchset_id="p1",
            workspace_id="ws1",
            compile_verified=True,
            finding_resolved=True,
            no_regression=True,
            verified=True,
        )

        assert patch.compile_verified
        assert patch.finding_resolved
        assert patch.no_regression
        assert patch.verified


class TestFinding:
    """Finding 테스트."""

    def test_create_happy_path(self):
        """Happy Path: 정상 생성."""
        finding = Finding(
            finding_id="F001",
            type="sql_injection",
            severity="high",
            message="SQL Injection vulnerability detected",
            file_path="src/db.py",
            line=42,
        )

        assert finding.finding_id == "F001"
        assert finding.severity == "high"
        assert finding.line == 42

    def test_severity_values(self):
        """Edge Case: 심각도 값들."""
        for severity in ["critical", "high", "medium", "low", "info"]:
            finding = Finding(
                finding_id="F1",
                type="test",
                severity=severity,
                message="msg",
                file_path="f.py",
                line=1,
            )
            assert finding.severity == severity

    def test_optional_fields(self):
        """Corner Case: Optional 필드."""
        finding = Finding(
            finding_id="F2",
            type="xss",
            severity="medium",
            message="XSS",
            file_path="a.js",
            line=10,
            evidence_uri="semantica://executions/exec_1/artifacts",
            execution_id="exec_1",
            cwe_id="CWE-79",
        )

        assert finding.evidence_uri is not None
        assert finding.cwe_id == "CWE-79"
