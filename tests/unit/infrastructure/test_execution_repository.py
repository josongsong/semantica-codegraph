"""
ExecutionRepository 테스트

Test Coverage:
- Base: CRUD 기본 동작
- Edge: 상태 변환, 중복 저장
- Corner: 빈 결과, None 값
- Extreme: 대량 findings
"""

import os
import tempfile

import pytest

from codegraph_engine.shared_kernel.contracts import (
    AgentMetadata,
    Execution,
    Finding,
    VerificationSnapshot,
)
from codegraph_engine.shared_kernel.infrastructure.execution_repository import (
    InMemoryExecutionRepository,
    SQLiteExecutionRepository,
)


@pytest.fixture
def sqlite_repo():
    """SQLite 임시 DB."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    repo = SQLiteExecutionRepository(db_path)
    yield repo

    os.unlink(db_path)


@pytest.fixture
def memory_repo():
    """In-Memory 저장소."""
    return InMemoryExecutionRepository()


@pytest.fixture
def sample_execution():
    """샘플 Execution."""
    return Execution(
        execution_id="exec_test",
        workspace_id="ws_test",
        spec_type="taint_analysis",
        state="completed",
        trace_id="trace_1",
        verification_snapshot=VerificationSnapshot(
            engine_version="2.4.1",
            ruleset_hash="sha256:abc",
            policies_hash="sha256:def",
            index_snapshot_id="idx_1",
            repo_revision="commit_sha",
        ),
    )


@pytest.fixture
def sample_findings():
    """샘플 Findings."""
    return [
        Finding(
            finding_id="F001",
            type="sql_injection",
            severity="high",
            message="SQL Injection found",
            file_path="db.py",
            line=42,
        ),
        Finding(
            finding_id="F002",
            type="xss",
            severity="medium",
            message="XSS found",
            file_path="web.py",
            line=100,
        ),
    ]


class TestSQLiteExecutionRepository:
    """SQLite Repository 테스트."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, sqlite_repo, sample_execution):
        """Base: 저장 및 조회."""
        await sqlite_repo.save(sample_execution)
        result = await sqlite_repo.get("exec_test")

        assert result is not None
        assert result.execution_id == "exec_test"
        assert result.workspace_id == "ws_test"
        assert result.state == "completed"

    @pytest.mark.asyncio
    async def test_get_with_verification_snapshot(self, sqlite_repo, sample_execution):
        """Edge: VerificationSnapshot 복원."""
        await sqlite_repo.save(sample_execution)
        result = await sqlite_repo.get("exec_test")

        assert result.verification_snapshot is not None
        assert result.verification_snapshot.engine_version == "2.4.1"
        assert result.verification_snapshot.ruleset_hash == "sha256:abc"

    @pytest.mark.asyncio
    async def test_save_findings(self, sqlite_repo, sample_execution, sample_findings):
        """Base: Findings 저장."""
        await sqlite_repo.save(sample_execution)
        await sqlite_repo.save_findings("exec_test", sample_findings)

        findings = await sqlite_repo.get_findings("exec_test")
        assert len(findings) == 2
        assert findings[0]["finding_id"] == "F001"
        assert findings[1]["finding_id"] == "F002"

    @pytest.mark.asyncio
    async def test_get_findings_empty(self, sqlite_repo):
        """Corner: 빈 findings."""
        findings = await sqlite_repo.get_findings("nonexistent")
        assert findings == []

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, sqlite_repo):
        """Corner: 존재하지 않는 execution."""
        result = await sqlite_repo.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_workspace(self, sqlite_repo):
        """Base: Workspace별 목록."""
        for i in range(5):
            exec = Execution(
                execution_id=f"exec_{i}",
                workspace_id="ws_list",
                spec_type="test",
                state="completed",
                trace_id=f"trace_{i}",
            )
            await sqlite_repo.save(exec)

        results = await sqlite_repo.list_by_workspace("ws_list")
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_list_by_workspace_limit(self, sqlite_repo):
        """Edge: Limit 적용."""
        for i in range(10):
            exec = Execution(
                execution_id=f"exec_{i}",
                workspace_id="ws_limit",
                spec_type="test",
                state="completed",
                trace_id=f"trace_{i}",
            )
            await sqlite_repo.save(exec)

        results = await sqlite_repo.list_by_workspace("ws_limit", limit=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_list_by_workspace_empty(self, sqlite_repo):
        """Corner: 빈 workspace."""
        results = await sqlite_repo.list_by_workspace("ws_empty")
        assert results == []

    @pytest.mark.asyncio
    async def test_update_execution(self, sqlite_repo, sample_execution):
        """Edge: 중복 저장 (업데이트)."""
        await sqlite_repo.save(sample_execution)

        # 상태 변경
        updated = Execution(
            execution_id="exec_test",
            workspace_id="ws_test",
            spec_type="taint_analysis",
            state="failed",
            trace_id="trace_1",
            error="Analysis failed",
        )
        await sqlite_repo.save(updated)

        result = await sqlite_repo.get("exec_test")
        assert result.state == "failed"
        assert result.error == "Analysis failed"

    @pytest.mark.asyncio
    async def test_execution_with_agent_metadata(self, sqlite_repo):
        """Edge: AgentMetadata 포함."""
        exec = Execution(
            execution_id="exec_agent",
            workspace_id="ws_agent",
            spec_type="agent_fix",
            state="completed",
            trace_id="trace_agent",
            agent_metadata=AgentMetadata(
                agent_model_id="gpt-4o",
                agent_version="v1",
            ),
        )
        await sqlite_repo.save(exec)

        result = await sqlite_repo.get("exec_agent")
        assert result.agent_metadata is not None
        assert result.agent_metadata.agent_model_id == "gpt-4o"

    @pytest.mark.asyncio
    async def test_large_findings(self, sqlite_repo, sample_execution):
        """Extreme: 대량 findings."""
        await sqlite_repo.save(sample_execution)

        large_findings = [
            Finding(
                finding_id=f"F{i:04d}",
                type="test",
                severity="low",
                message=f"Finding {i}",
                file_path=f"file_{i}.py",
                line=i,
            )
            for i in range(100)
        ]
        await sqlite_repo.save_findings("exec_test", large_findings)

        findings = await sqlite_repo.get_findings("exec_test")
        assert len(findings) == 100

    # ========================================================================
    # RFC-SEM-022 SOTA: 추가 메서드 테스트
    # ========================================================================

    @pytest.mark.asyncio
    async def test_update_state(self, sqlite_repo, sample_execution):
        """RFC-SEM-022: 상태 업데이트."""
        await sqlite_repo.save(sample_execution)

        await sqlite_repo.update_state(
            execution_id="exec_test",
            state="failed",
            error="Test error",
        )

        result = await sqlite_repo.get("exec_test")
        assert result.state == "failed"
        assert result.error == "Test error"
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_state_with_result(self, sqlite_repo, sample_execution):
        """RFC-SEM-022: 결과와 함께 상태 업데이트."""
        await sqlite_repo.save(sample_execution)

        await sqlite_repo.update_state(
            execution_id="exec_test",
            state="completed",
            result={"claims_count": 5, "execution_time_ms": 123.4},
        )

        result = await sqlite_repo.get("exec_test")
        assert result.state == "completed"
        assert result.result["claims_count"] == 5

    @pytest.mark.asyncio
    async def test_save_finding_single(self, sqlite_repo, sample_execution):
        """RFC-SEM-022: 단일 Finding 저장."""
        await sqlite_repo.save(sample_execution)

        finding = Finding(
            finding_id="F_single",
            type="sql_injection",
            severity="high",
            message="Single finding",
            file_path="test.py",
            line=10,
        )
        await sqlite_repo.save_finding("exec_test", finding)

        findings = await sqlite_repo.get_findings("exec_test")
        assert len(findings) == 1
        assert findings[0]["finding_id"] == "F_single"

    @pytest.mark.asyncio
    async def test_compare_findings_identical(self, sqlite_repo):
        """RFC-SEM-022: Regression Proof - 동일한 findings."""
        # Baseline execution
        baseline = Execution(
            execution_id="exec_baseline",
            workspace_id="ws_test",
            spec_type="test",
            state="completed",
            trace_id="trace_1",
        )
        await sqlite_repo.save(baseline)
        await sqlite_repo.save_findings(
            "exec_baseline",
            [
                Finding(
                    finding_id="F1", type="sql_injection", severity="high", message="SQL", file_path="db.py", line=10
                ),
            ],
        )

        # Current execution (same findings)
        current = Execution(
            execution_id="exec_current",
            workspace_id="ws_test",
            spec_type="test",
            state="completed",
            trace_id="trace_2",
        )
        await sqlite_repo.save(current)
        await sqlite_repo.save_findings(
            "exec_current",
            [
                Finding(
                    finding_id="F1_new",
                    type="sql_injection",
                    severity="high",
                    message="SQL",
                    file_path="db.py",
                    line=10,
                ),
            ],
        )

        comparison = await sqlite_repo.compare_findings("exec_baseline", "exec_current")

        assert comparison["passed"] is True
        assert len(comparison["new_findings"]) == 0
        assert len(comparison["removed_findings"]) == 0
        assert comparison["unchanged_count"] == 1

    @pytest.mark.asyncio
    async def test_compare_findings_regression(self, sqlite_repo):
        """RFC-SEM-022: Regression Proof - 새로운 finding 발생."""
        # Baseline - no findings
        baseline = Execution(
            execution_id="exec_base_reg",
            workspace_id="ws_test",
            spec_type="test",
            state="completed",
            trace_id="trace_1",
        )
        await sqlite_repo.save(baseline)
        # Empty baseline

        # Current (with new finding = regression)
        current = Execution(
            execution_id="exec_curr_reg",
            workspace_id="ws_test",
            spec_type="test",
            state="completed",
            trace_id="trace_2",
        )
        await sqlite_repo.save(current)
        await sqlite_repo.save_findings(
            "exec_curr_reg",
            [
                Finding(finding_id="F1", type="xss", severity="medium", message="XSS", file_path="web.py", line=20),
            ],
        )

        comparison = await sqlite_repo.compare_findings("exec_base_reg", "exec_curr_reg")

        assert comparison["passed"] is False
        assert len(comparison["new_findings"]) == 1
        assert comparison["new_findings"][0]["type"] == "xss"

    @pytest.mark.asyncio
    async def test_compare_findings_fixed(self, sqlite_repo):
        """RFC-SEM-022: Regression Proof - finding 해결됨."""
        # Baseline (with finding)
        baseline = Execution(
            execution_id="exec_base_fix",
            workspace_id="ws_test",
            spec_type="test",
            state="completed",
            trace_id="trace_1",
        )
        await sqlite_repo.save(baseline)
        await sqlite_repo.save_findings(
            "exec_base_fix",
            [
                Finding(
                    finding_id="F1", type="sql_injection", severity="high", message="SQL", file_path="db.py", line=10
                ),
            ],
        )

        # Current (finding resolved)
        current = Execution(
            execution_id="exec_curr_fix",
            workspace_id="ws_test",
            spec_type="test",
            state="completed",
            trace_id="trace_2",
        )
        await sqlite_repo.save(current)
        # No findings

        comparison = await sqlite_repo.compare_findings("exec_base_fix", "exec_curr_fix")

        assert comparison["passed"] is True  # No new findings
        assert len(comparison["removed_findings"]) == 1
        assert comparison["removed_findings"][0]["type"] == "sql_injection"


class TestInMemoryExecutionRepository:
    """In-Memory Repository 테스트."""

    @pytest.mark.asyncio
    async def test_save_and_get(self, memory_repo, sample_execution):
        """Base: 저장 및 조회."""
        await memory_repo.save(sample_execution)
        result = await memory_repo.get("exec_test")

        assert result is not None
        assert result.execution_id == "exec_test"

    @pytest.mark.asyncio
    async def test_get_findings(self, memory_repo, sample_execution, sample_findings):
        """Base: Findings 조회."""
        await memory_repo.save(sample_execution)
        await memory_repo.save_findings("exec_test", sample_findings)

        findings = await memory_repo.get_findings("exec_test")
        assert len(findings) == 2

    @pytest.mark.asyncio
    async def test_list_by_workspace(self, memory_repo):
        """Base: Workspace별 목록."""
        for i in range(3):
            exec = Execution(
                execution_id=f"exec_{i}",
                workspace_id="ws_mem",
                spec_type="test",
                state="completed",
                trace_id=f"trace_{i}",
            )
            await memory_repo.save(exec)

        results = await memory_repo.list_by_workspace("ws_mem")
        assert len(results) == 3
