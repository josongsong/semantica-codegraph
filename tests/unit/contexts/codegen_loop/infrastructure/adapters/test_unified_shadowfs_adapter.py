"""
UnifiedShadowFSAdapter Tests

Hexagonal Architecture 검증: Adapter가 Port 인터페이스 준수

Test Coverage:
    - ShadowFSPort 인터페이스 구현 확인
    - TransactionPort 인터페이스 구현 확인
    - 실제 동작 검증 (Base/Edge cases)
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from codegraph_runtime.codegen_loop.application.shadowfs.shadowfs_port import ShadowFSPort
from codegraph_runtime.codegen_loop.application.shadowfs.transaction_port import TransactionPort
from codegraph_runtime.codegen_loop.infrastructure.adapters.unified_shadowfs_adapter import UnifiedShadowFSAdapter


@pytest.fixture
def temp_workspace(tmp_path):
    """Temp workspace"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "existing.py").write_text("# existing\n")
    return workspace


@pytest.fixture
def adapter(temp_workspace):
    """Adapter instance"""
    mock_builder = MagicMock()
    mock_builder.parse_file = None  # Force stub

    return UnifiedShadowFSAdapter(temp_workspace, mock_builder)


# ========== Interface Conformance ==========


class TestInterfaceConformance:
    """인터페이스 준수 검증"""

    def test_implements_shadowfs_port(self, adapter):
        """Adapter는 ShadowFSPort 구현"""
        assert isinstance(adapter, ShadowFSPort)

    def test_implements_transaction_port(self, adapter):
        """Adapter는 TransactionPort 구현"""
        assert isinstance(adapter, TransactionPort)

    def test_has_all_shadowfs_port_methods(self, adapter):
        """ShadowFSPort의 모든 메서드 구현"""
        required_methods = [
            "read_file",
            "write_file",
            "delete_file",
            "list_files",
            "get_modified_files",
            "is_modified",
            "get_diff",
            "rollback",
            "prepare_for_external_tool",
            "cleanup_temp",
            "file_exists",
            "get_file_size",
        ]

        for method in required_methods:
            assert hasattr(adapter, method)
            assert callable(getattr(adapter, method))

    def test_has_all_transaction_port_methods(self, adapter):
        """TransactionPort의 모든 메서드 구현"""
        required_methods = [
            "begin_transaction",
            "commit_transaction",
            "rollback_transaction",
            "get_or_parse_ir",
            "get_symbol_table",
            "get_transaction_status",
            "get_active_transaction_ids",
        ]

        for method in required_methods:
            assert hasattr(adapter, method)
            assert callable(getattr(adapter, method))


# ========== File Operations ==========


class TestFileOperations:
    """File 연산 검증"""

    def test_read_existing_file(self, adapter):
        """BASE: 기존 파일 읽기"""
        content = adapter.read_file("existing.py")
        assert content == "# existing\n"

    def test_write_and_read_file(self, adapter):
        """BASE: 파일 쓰기 + 읽기"""
        adapter.write_file("new.py", "# new content")

        content = adapter.read_file("new.py")
        assert content == "# new content"

    def test_delete_file(self, adapter):
        """BASE: 파일 삭제"""
        adapter.write_file("temp.py", "# temp")
        adapter.delete_file("temp.py")

        with pytest.raises(FileNotFoundError):
            adapter.read_file("temp.py")

    def test_list_files(self, adapter):
        """BASE: 파일 리스트"""
        adapter.write_file("a.py", "# a")
        adapter.write_file("b.py", "# b")

        files = adapter.list_files(suffix=".py")
        assert "a.py" in files
        assert "b.py" in files

    def test_get_modified_files(self, adapter):
        """BASE: 수정 파일 조회"""
        adapter.write_file("modified.py", "# modified")

        modified = adapter.get_modified_files()
        assert "modified.py" in modified

    def test_is_modified(self, adapter):
        """BASE: 수정 여부 확인"""
        adapter.write_file("test.py", "# test")

        assert adapter.is_modified("test.py")
        assert not adapter.is_modified("existing.py")

    def test_file_exists(self, adapter):
        """BASE: 파일 존재 확인"""
        assert adapter.file_exists("existing.py")
        assert not adapter.file_exists("nonexistent.py")

    def test_get_file_size(self, adapter):
        """BASE: 파일 크기 조회"""
        adapter.write_file("sized.py", "12345")

        size = adapter.get_file_size("sized.py")
        assert size == 5


# ========== Transaction Operations ==========


class TestTransactionOperations:
    """Transaction 연산 검증"""

    @pytest.mark.asyncio
    async def test_transaction_lifecycle(self, adapter):
        """BASE: Transaction begin → commit"""
        txn_id = await adapter.begin_transaction()

        assert txn_id is not None
        assert txn_id in adapter.get_active_transaction_ids()

        await adapter.commit_transaction(txn_id)

        assert txn_id not in adapter.get_active_transaction_ids()

    @pytest.mark.asyncio
    async def test_write_file_with_ir(self, adapter):
        """BASE: 파일 쓰기 + IR 파싱"""
        txn_id = await adapter.begin_transaction()

        await adapter.write_file_with_ir("code.py", "def func(): pass", txn_id)

        # File should be writable
        content = adapter.read_file("code.py")
        assert content == "def func(): pass"

        await adapter.commit_transaction(txn_id)

    @pytest.mark.asyncio
    async def test_get_symbol_table(self, adapter):
        """BASE: Symbol table 조회"""
        txn_id = await adapter.begin_transaction()

        await adapter.write_file_with_ir("math.py", "def add(a, b): return a + b", txn_id)

        symbols = adapter.get_symbol_table(txn_id)

        assert isinstance(symbols, dict)
        assert len(symbols) >= 1

        await adapter.commit_transaction(txn_id)

    @pytest.mark.asyncio
    async def test_find_symbol(self, adapter):
        """BASE: Symbol 찾기"""
        txn_id = await adapter.begin_transaction()

        await adapter.write_file_with_ir(
            "calculator.py",
            """
class Calculator:
    def add(self, a, b):
        return a + b
""",
            txn_id,
        )

        file_path = await adapter.find_symbol("Calculator", txn_id)

        assert file_path == "calculator.py"

        await adapter.commit_transaction(txn_id)

    @pytest.mark.asyncio
    async def test_rollback_transaction(self, adapter):
        """EDGE: Transaction rollback"""
        txn_id = await adapter.begin_transaction()

        await adapter.write_file_with_ir("temp.py", "# temp", txn_id)

        await adapter.rollback_transaction(txn_id)

        # Transaction should be gone
        assert txn_id not in adapter.get_active_transaction_ids()


# ========== Edge Cases ==========


class TestEdgeCases:
    """엣지 케이스"""

    def test_read_nonexistent_file(self, adapter):
        """EDGE: 존재하지 않는 파일 읽기"""
        with pytest.raises(FileNotFoundError):
            adapter.read_file("nonexistent.py")

    def test_get_diff(self, adapter):
        """EDGE: Diff 생성"""
        adapter.write_file("new.py", "# new")

        patches = adapter.get_diff()

        assert len(patches) >= 1
        assert any(p.path == "new.py" for p in patches)

    def test_rollback_all(self, adapter):
        """EDGE: 전체 롤백"""
        adapter.write_file("temp.py", "# temp")

        adapter.rollback()

        # Overlay should be cleared
        assert len(adapter.get_modified_files()) == 0

    def test_prepare_for_external_tool(self, adapter):
        """EDGE: External tool materialization"""
        adapter.write_file("ext.py", "# for external")

        temp_dir = adapter.prepare_for_external_tool()

        assert temp_dir.exists()
        assert (temp_dir / "ext.py").exists()

        adapter.cleanup_temp(temp_dir)
        assert not temp_dir.exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
