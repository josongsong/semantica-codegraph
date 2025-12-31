"""CodeGen Loop 통합 테스트

Phase 4: codegen_loop 통합 검증:
- CodeGenAdapter 기본 기능
- ShadowFS 격리 실행
- 트랜잭션 롤백
- 입력 검증

테스트 범위:
- Happy Path
- Corner Cases (empty dict, None content)
- Edge Cases (ShadowFS 미설치)
- Error Cases (트랜잭션 실패)
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.orchestrator.orchestrator.adapters.codegen_adapter import CodeGenAdapter, CodeGenResult


class TestCodeGenAdapter:
    """CodeGenAdapter 테스트"""

    @pytest.fixture
    def adapter(self, tmp_path):
        """테스트용 어댑터"""
        return CodeGenAdapter(workspace_root=tmp_path)

    # ============================================================
    # 초기화 테스트
    # ============================================================

    def test_init_default_values(self):
        """기본값 초기화 테스트"""
        adapter = CodeGenAdapter()

        assert adapter.workspace_root == Path.cwd()
        assert adapter.llm_api_key is None
        assert adapter.max_iterations == 5
        assert adapter.convergence_threshold == 0.95
        assert adapter._api is None  # Lazy init

    def test_init_custom_values(self, tmp_path):
        """커스텀 값 초기화 테스트"""
        adapter = CodeGenAdapter(
            workspace_root=tmp_path,
            llm_api_key="test-key",
            max_iterations=10,
            convergence_threshold=0.99,
        )

        assert adapter.workspace_root == tmp_path
        assert adapter.llm_api_key == "test-key"
        assert adapter.max_iterations == 10
        assert adapter.convergence_threshold == 0.99

    # ============================================================
    # apply_changes_isolated 테스트
    # ============================================================

    @pytest.mark.asyncio
    async def test_apply_changes_isolated_empty_dict_raises(self, adapter):
        """Corner Case: 빈 file_changes"""
        with pytest.raises(ValueError, match="file_changes cannot be empty"):
            await adapter.apply_changes_isolated(file_changes={})

    @pytest.mark.asyncio
    async def test_apply_changes_isolated_empty_path_raises(self, adapter):
        """Corner Case: 빈 file_path"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await adapter.apply_changes_isolated(file_changes={"": "content"})

    @pytest.mark.asyncio
    async def test_apply_changes_isolated_whitespace_path_raises(self, adapter):
        """Corner Case: 공백만 있는 file_path"""
        with pytest.raises(ValueError, match="file_path cannot be empty"):
            await adapter.apply_changes_isolated(file_changes={"   ": "content"})

    @pytest.mark.asyncio
    async def test_apply_changes_isolated_none_content_raises(self, adapter):
        """Corner Case: None content"""
        with pytest.raises(ValueError, match="content for test.py cannot be None"):
            await adapter.apply_changes_isolated(file_changes={"test.py": None})

    @pytest.mark.asyncio
    async def test_apply_changes_isolated_shadowfs_not_available(self, adapter):
        """Edge Case: ShadowFS 미설치"""
        with patch.object(adapter, "_get_shadowfs", side_effect=ImportError("No module")):
            with pytest.raises(RuntimeError, match="ShadowFS not available"):
                await adapter.apply_changes_isolated(file_changes={"test.py": "content"})

    @pytest.mark.asyncio
    async def test_apply_changes_isolated_success(self, tmp_path, adapter):
        """Happy Path: 격리된 파일 변경 성공"""
        # 작업 디렉토리에 테스트 파일 생성
        test_file = tmp_path / "test.py"
        test_file.write_text("# original")

        file_changes = {"test.py": "# modified"}

        # ShadowFS Mock (Lazy singleton 패턴)
        mock_shadowfs = AsyncMock()
        mock_shadowfs.begin_transaction = AsyncMock(return_value="txn-001")
        mock_shadowfs.write_file = AsyncMock()
        mock_shadowfs.shadowfs_core = MagicMock()
        mock_shadowfs.shadowfs_core.get_diff = MagicMock(return_value=[{"path": "test.py"}])
        mock_shadowfs.commit_transaction = AsyncMock()

        # Inject mock via lazy singleton
        adapter._shadowfs = mock_shadowfs

        result = await adapter.apply_changes_isolated(
            file_changes=file_changes,
        )

        assert result.success is True
        assert result.file_changes == file_changes
        assert result.iterations == 1  # 1개 patch

    @pytest.mark.asyncio
    async def test_apply_changes_isolated_rollback_on_error(self, adapter):
        """Error Case: 에러 시 롤백 후 예외 발생"""
        mock_shadowfs = AsyncMock()
        mock_shadowfs.begin_transaction = AsyncMock(return_value="txn-001")
        mock_shadowfs.write_file = AsyncMock(side_effect=Exception("Write failed"))
        mock_shadowfs.rollback_transaction = AsyncMock()

        # Inject mock via lazy singleton
        adapter._shadowfs = mock_shadowfs

        with pytest.raises(RuntimeError, match="Failed to apply changes"):
            await adapter.apply_changes_isolated(
                file_changes={"test.py": "content"},
            )

        # 롤백 호출 확인
        mock_shadowfs.rollback_transaction.assert_called_once_with("txn-001")

    # ============================================================
    # execute_with_shadowfs 테스트
    # ============================================================

    @pytest.mark.asyncio
    async def test_execute_with_shadowfs_api_not_available(self, adapter):
        """Edge Case: CodeGenLoopAPI 미설치"""
        with patch.object(adapter, "_get_api", side_effect=ImportError("No module")):
            result = await adapter.execute_with_shadowfs(
                task_id="test-001",
                task_description="Fix bug",
            )

        assert result.success is False
        assert "not available" in result.error

    @pytest.mark.asyncio
    async def test_execute_with_shadowfs_success(self, adapter):
        """Happy Path: 성공적인 8-Step Pipeline 실행"""
        # Mock API
        mock_api = MagicMock()
        mock_loop_state = MagicMock()
        mock_loop_state.iteration = 3
        mock_loop_state.convergence_score = 0.98
        mock_loop_state.patches = []

        # LoopStatus.CONVERGED 시뮬레이션
        with patch("src.contexts.codegen_loop.domain.models.LoopStatus") as mock_status:
            mock_status.CONVERGED = "converged"
            mock_loop_state.status = "converged"
            mock_api.run = AsyncMock(return_value=mock_loop_state)

            adapter._api = mock_api

            result = await adapter.execute_with_shadowfs(
                task_id="test-001",
                task_description="Fix bug",
            )

        assert result.task_id == "test-001"
        assert result.iterations == 3
        assert result.final_score == 0.98

    @pytest.mark.asyncio
    async def test_execute_with_shadowfs_exception_handling(self, adapter):
        """Error Case: 실행 중 예외"""
        mock_api = MagicMock()
        mock_api.run = AsyncMock(side_effect=Exception("Pipeline failed"))
        adapter._api = mock_api

        result = await adapter.execute_with_shadowfs(
            task_id="test-001",
            task_description="Fix bug",
        )

        assert result.success is False
        assert "Pipeline failed" in result.error

    # ============================================================
    # _extract_file_changes 테스트
    # ============================================================

    def test_extract_file_changes_with_patches(self, adapter):
        """Happy Path: 패치 추출"""
        mock_loop_state = MagicMock()
        mock_loop_state.patches = [
            MagicMock(file_path="a.py", new_content="# a"),
            MagicMock(file_path="b.py", new_content="# b"),
        ]

        result = adapter._extract_file_changes(mock_loop_state)

        assert result == {"a.py": "# a", "b.py": "# b"}

    def test_extract_file_changes_empty_patches(self, adapter):
        """Edge Case: 빈 패치 리스트"""
        mock_loop_state = MagicMock()
        mock_loop_state.patches = []

        result = adapter._extract_file_changes(mock_loop_state)

        assert result is None

    def test_extract_file_changes_none_state(self, adapter):
        """Edge Case: None 상태"""
        result = adapter._extract_file_changes(None)

        assert result is None

    def test_extract_file_changes_no_patches_attr(self, adapter):
        """Edge Case: patches 속성 없음"""
        mock_loop_state = MagicMock(spec=[])  # patches 속성 없음

        result = adapter._extract_file_changes(mock_loop_state)

        assert result is None
