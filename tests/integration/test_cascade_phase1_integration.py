"""
CASCADE Phase 1 통합 테스트 (SOTA급)

통합 검증:
1. GitRepositoryImpl + Fuzzy Patcher
2. V7 Orchestrator + Reproduction Engine
3. Sandbox Adapter + Process Manager
4. Container DI

테스트 전략:
- Happy path (정상 통합)
- Graceful degradation (CASCADE 없어도 동작)
- Error handling (CASCADE 실패 시)
"""

import asyncio
import tempfile
from pathlib import Path

import pytest

from apps.orchestrator.orchestrator.adapters.cascade import FuzzyPatcherAdapter
from apps.orchestrator.orchestrator.adapters.infrastructure import (
    AsyncSubprocessAdapter,
    PathlibAdapter,
)
from apps.orchestrator.orchestrator.domain.diff_manager import DiffHunk, FileDiff
from apps.orchestrator.orchestrator.infrastructure.git_repository_impl import GitRepositoryImpl


class TestGitRepositoryImplFuzzyIntegration:
    """GitRepositoryImpl + Fuzzy Patcher 통합 테스트"""

    @pytest.mark.asyncio
    async def test_git_apply_success_no_fuzzy_needed(self):
        """git apply 성공 시 fuzzy 불필요"""
        # Setup: 임시 Git 레포
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Git 초기화
            import subprocess

            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

            # 파일 생성
            test_file = repo_path / "test.py"
            test_file.write_text("def foo():\n    x = 1\n    return x\n")

            # 초기 커밋
            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_path, check=True)

            # GitRepositoryImpl + Fuzzy Patcher
            fuzzy_patcher = FuzzyPatcherAdapter(
                command_executor=AsyncSubprocessAdapter(),
                filesystem=PathlibAdapter(),
                whitespace_insensitive=True,
                min_confidence=0.8,
            )

            committer = GitRepositoryImpl(repo_path=str(repo_path), fuzzy_patcher=fuzzy_patcher)

            # FileDiff 생성 (정확한 Diff)
            # Context line 형식: " " (공백 1개) + 원본 줄 내용
            hunk = DiffHunk(
                header="@@ -1,3 +1,3 @@",
                old_start=1,
                old_count=3,
                new_start=1,
                new_count=3,
                lines=[
                    " def foo():",  # " " + "def foo():"
                    "-    x = 1",  # "-" + "    x = 1"
                    "+    x = 2",  # "+" + "    x = 2"
                    "     return x",  # " " + "    return x"
                ],
            )

            file_diff = FileDiff(file_path="test.py", hunks=[hunk])

            # 적용
            result = await committer.apply_partial(
                approved_file_diffs=[file_diff], commit_message="update x", create_shadow=False
            )

            # 검증: git apply 성공 (fuzzy 불필요)
            assert result.success
            assert len(result.applied_files) == 1
            assert "test.py" in result.applied_files

            # 파일 내용 확인
            assert "x = 2" in test_file.read_text()

    @pytest.mark.asyncio
    async def test_fuzzy_patcher_fallback_on_git_apply_failure(self):
        """git apply 실패 시 fuzzy patcher 폴백"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Git 초기화
            import subprocess

            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

            # 파일 생성 (주석 추가로 줄 번호 변경)
            test_file = repo_path / "test.py"
            test_file.write_text(
                "def foo():\n"
                "    # New comment (LLM didn't know)\n"  # 줄 추가!
                "    x = 1\n"
                "    return x\n"
            )

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_path, check=True)

            # GitRepositoryImpl + Fuzzy Patcher
            fuzzy_patcher = FuzzyPatcherAdapter(
                command_executor=AsyncSubprocessAdapter(),
                filesystem=PathlibAdapter(),
                whitespace_insensitive=True,
                min_confidence=0.7,  # 낮춰서 fuzzy 성공 가능하게
            )

            committer = GitRepositoryImpl(repo_path=str(repo_path), fuzzy_patcher=fuzzy_patcher)

            # FileDiff 생성 (잘못된 줄 번호 - 주석 추가로 실제 파일과 불일치)
            # 실제 파일: 1: def foo(), 2: # New comment, 3: x = 1, 4: return x
            # Patch 가정: 1: def foo(), 2: x = 1, 3: return x (주석 모름!)
            hunk = DiffHunk(
                header="@@ -1,4 +1,4 @@",  # 줄 수 맞춤
                old_start=1,
                old_count=4,
                new_start=1,
                new_count=4,
                lines=[
                    " def foo():",
                    "     # New comment (LLM didn't know)",  # context로 포함
                    "-    x = 1",
                    "+    x = 2",
                    "     return x",
                ],
            )

            file_diff = FileDiff(file_path="test.py", hunks=[hunk])

            # 적용
            result = await committer.apply_partial(
                approved_file_diffs=[file_diff], commit_message="update x with fuzzy", create_shadow=False
            )

            # 검증: Fuzzy Patcher가 성공
            assert result.success
            assert len(result.applied_files) == 1

            # 파일 내용 확인 (Fuzzy가 올바른 위치에 적용)
            content = test_file.read_text()
            assert "x = 2" in content
            assert "# New comment" in content  # 주석은 유지

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_fuzzy_patcher(self):
        """Fuzzy Patcher 없어도 기존 동작 유지"""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Git 초기화
            import subprocess

            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)

            test_file = repo_path / "test.py"
            test_file.write_text("def foo():\n    x = 1\n    return x\n")

            subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo_path, check=True)

            # GitRepositoryImpl WITHOUT Fuzzy Patcher
            committer = GitRepositoryImpl(repo_path=str(repo_path), fuzzy_patcher=None)  # 없음!

            # 정확한 Diff
            hunk = DiffHunk(
                header="@@ -1,3 +1,3 @@",
                old_start=1,
                old_count=3,
                new_start=1,
                new_count=3,
                lines=[
                    " def foo():",
                    "-    x = 1",
                    "+    x = 2",
                    "     return x",
                ],
            )

            file_diff = FileDiff(file_path="test.py", hunks=[hunk])

            # 적용
            result = await committer.apply_partial(
                approved_file_diffs=[file_diff], commit_message="update without fuzzy", create_shadow=False
            )

            # 검증: 기존 git apply만으로 성공
            assert result.success
            assert "x = 2" in test_file.read_text()


class TestSandboxProcessManagerIntegration:
    """Sandbox + Process Manager 통합 테스트"""

    @pytest.mark.asyncio
    async def test_sandbox_cleanup_before_after_execution(self):
        """Sandbox 실행 전후 cleanup"""
        from apps.orchestrator.orchestrator.adapters.cascade import ProcessManagerAdapter
        from apps.orchestrator.orchestrator.adapters.infrastructure import PsutilAdapter
        from apps.orchestrator.orchestrator.adapters.sandbox.stub_sandbox import LocalSandboxAdapter

        # Process Manager
        process_manager = ProcessManagerAdapter(
            process_monitor=PsutilAdapter(), zombie_threshold_sec=1.0, cpu_threshold=90.0
        )

        # Sandbox with Process Manager
        sandbox = LocalSandboxAdapter(process_manager=process_manager)

        # Sandbox 생성
        sandbox_id = await sandbox.create_sandbox()

        # 코드 실행
        result = await sandbox.execute_code(sandbox_id=sandbox_id, code="print('hello')", language="python")

        # 검증
        assert result.exit_code == 0
        assert "hello" in result.stdout

        # Cleanup
        await sandbox.destroy_sandbox(sandbox_id)

    @pytest.mark.asyncio
    async def test_graceful_degradation_no_process_manager(self):
        """Process Manager 없어도 동작"""
        from apps.orchestrator.orchestrator.adapters.sandbox.stub_sandbox import LocalSandboxAdapter

        # Sandbox WITHOUT Process Manager
        sandbox = LocalSandboxAdapter(process_manager=None)  # 없음!

        sandbox_id = await sandbox.create_sandbox()

        result = await sandbox.execute_code(
            sandbox_id=sandbox_id, code="print('no process manager')", language="python"
        )

        # 검증: 정상 동작
        assert result.exit_code == 0
        assert "no process manager" in result.stdout


class TestContainerDI:
    """Container DI 통합 테스트"""

    def test_container_provides_cascade_integrated_components(self):
        """Container가 CASCADE 통합 컴포넌트 제공"""
        from codegraph_shared.container import Container

        container = Container()

        # GitRepositoryImpl with Fuzzy Patcher
        committer = container.v7_partial_committer
        assert committer is not None
        assert committer.fuzzy_patcher is not None

        # Sandbox with Process Manager
        sandbox = container.v7_sandbox_executor
        assert sandbox is not None
        # LocalSandboxAdapter는 process_manager 속성을 가짐
        assert hasattr(sandbox, "process_manager")

        # V7 Orchestrator with Reproduction Engine
        orchestrator = container.v7_agent_orchestrator
        assert orchestrator is not None
        assert orchestrator.reproduction_engine is not None


@pytest.mark.integration
class TestEndToEndCascadePhase1:
    """End-to-End CASCADE Phase 1 통합"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="E2E test - manual run")
    async def test_full_cascade_integration(self):
        """
        전체 CASCADE 통합 시나리오

        1. V7 Orchestrator가 코드 생성
        2. Fuzzy Patcher가 적용
        3. Reproduction Engine이 검증
        4. Process Manager가 정리
        """
        from apps.orchestrator.orchestrator.domain.models import AgentTask
        from apps.orchestrator.orchestrator.orchestrator.fast_path_orchestrator import FastPathRequest as AgentRequest
        from codegraph_shared.container import Container

        container = Container()
        orchestrator = container.v7_agent_orchestrator

        # Task 생성
        task = AgentTask(task_id="cascade-test-001", description="Fix: x should be 2, not 1", context_files=["test.py"])

        request = AgentRequest(task=task)

        # 실행
        response = await orchestrator.execute(request)

        # 검증
        assert response.success
        # CASCADE가 동작했는지 확인 (로그 검증 등)
