"""
UnifiedShadowFS Adapter

Hexagonal Architecture: UnifiedShadowFS → Application Ports

Implements:
    - ShadowFSPort (File operations)
    - TransactionPort (IR operations)

Architecture: Infrastructure Layer (Adapter)
"""

from pathlib import Path
from typing import Any

from codegraph_runtime.codegen_loop.application.shadowfs.shadowfs_port import ShadowFSPort
from codegraph_runtime.codegen_loop.application.shadowfs.transaction_port import TransactionPort
from codegraph_runtime.codegen_loop.domain.shadowfs.models import FilePatch
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.ir_transaction_manager import IRConfig
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.unified_shadowfs import UnifiedShadowFS


class UnifiedShadowFSAdapter(ShadowFSPort, TransactionPort):
    """
    Unified Adapter (ShadowFSPort + TransactionPort)

    Wraps UnifiedShadowFS to provide both file and IR operations.

    Design:
        - Single adapter implements both ports
        - Delegates to UnifiedShadowFS
        - Stateless (UnifiedShadowFS manages state)

    Examples:
        >>> adapter = UnifiedShadowFSAdapter(Path("/project"), ir_builder)
        >>> txn_id = await adapter.begin_transaction()
        >>> adapter.write_file("main.py", "def func(): pass")
        >>> await adapter.write_file_with_ir("main.py", "def func(): pass", txn_id)
        >>> await adapter.commit_transaction(txn_id)
    """

    def __init__(self, workspace_root: Path, ir_builder: Any, ir_config: IRConfig | None = None):
        """
        Initialize adapter

        Args:
            workspace_root: Project root
            ir_builder: LayeredIRBuilder (or mock)
            ir_config: Optional IR config
        """
        self._unified_shadowfs = UnifiedShadowFS(workspace_root, ir_builder, ir_config)

    # ========== ShadowFSPort Implementation ==========

    def read_file(self, path: str) -> str:
        """Read file (from overlay or disk)"""
        return self._unified_shadowfs.read_file(path)

    def write_file(self, path: str, content: str) -> None:
        """Write file (memory only, no IR parsing)"""
        # For non-transactional writes, we need to handle it
        # This is for compatibility with existing code
        self._unified_shadowfs.shadowfs_core.write_file(path, content)

    def delete_file(self, path: str) -> None:
        """Delete file (tombstone, memory only)"""
        self._unified_shadowfs.shadowfs_core.delete_file(path)

    def list_files(self, prefix: str | None = None, suffix: str | None = None) -> list[str]:
        """List visible files"""
        return self._unified_shadowfs.shadowfs_core.list_files(prefix, suffix)

    def get_modified_files(self) -> list[str]:
        """Get modified file paths"""
        return self._unified_shadowfs.get_modified_files()

    def is_modified(self, path: str) -> bool:
        """Check if file is modified"""
        return path in self._unified_shadowfs.shadowfs_core.overlay

    def get_diff(self) -> list[FilePatch]:
        """Get unified diff"""
        return self._unified_shadowfs.get_diff()

    def rollback(self) -> None:
        """Rollback all changes (non-transactional)"""
        self._unified_shadowfs.rollback_all()

    def prepare_for_external_tool(self) -> Path:
        """Materialize to temp directory"""
        return self._unified_shadowfs.prepare_for_external_tool()

    def cleanup_temp(self, temp_dir: Path) -> None:
        """Cleanup temp directory"""
        self._unified_shadowfs.cleanup_temp(temp_dir)

    def file_exists(self, path: str) -> bool:
        """Check if file exists"""
        try:
            self.read_file(path)
            return True
        except FileNotFoundError:
            return False

    def get_file_size(self, path: str) -> int:
        """Get file size"""
        content = self.read_file(path)
        return len(content)

    def exists(self, path: str) -> bool:
        """Check if file exists (alias for file_exists)"""
        return self.file_exists(path)

    def get_deleted_files(self) -> list[str]:
        """Get deleted file paths"""
        return list(self._unified_shadowfs.shadowfs_core.deleted)

    # ========== TransactionPort Implementation ==========

    async def begin_transaction(self, txn_id: str | None = None) -> str:
        """Begin transaction"""
        return await self._unified_shadowfs.begin_transaction(txn_id)

    async def commit_transaction(self, txn_id: str) -> None:
        """Commit transaction"""
        await self._unified_shadowfs.commit_transaction(txn_id)

    async def rollback_transaction(self, txn_id: str) -> None:
        """Rollback transaction"""
        await self._unified_shadowfs.rollback_transaction(txn_id)

    async def get_or_parse_ir(self, file_path: str, file_content: str, txn_id: str) -> Any | None:
        """Get or parse IR"""
        return await self._unified_shadowfs.get_ir(file_path, txn_id)

    def get_symbol_table(self, txn_id: str) -> dict[str, str]:
        """Get symbol table"""
        return self._unified_shadowfs.get_symbol_table(txn_id)

    def get_transaction_status(self, txn_id: str) -> dict[str, Any] | None:
        """Get transaction status"""
        return self._unified_shadowfs.get_transaction_status(txn_id)

    def get_active_transaction_ids(self) -> list[str]:
        """Get active transaction IDs"""
        return self._unified_shadowfs.get_active_transaction_ids()

    def has_transaction(self, txn_id: str) -> bool:
        """Check if transaction exists"""
        return txn_id in self._unified_shadowfs._transactions

    def get_transaction_age(self, txn_id: str) -> float:
        """Get transaction age in seconds (stub: returns 0.0)"""
        # UnifiedShadowFS doesn't track transaction creation time
        # This is a stub implementation
        if not self.has_transaction(txn_id):
            raise ValueError(f"Transaction {txn_id} not found")
        return 0.0

    # ========== Query Operations (Stub) ==========

    async def find_callers(self, target_fqn: str, txn_id: str) -> list[str]:
        """
        Find callers of target symbol (STUB)

        Args:
            target_fqn: Target fully qualified name
            txn_id: Transaction ID

        Returns:
            List of caller FQNs (empty for stub)

        Note:
            This requires full IR graph analysis (code_foundation).
            Stub implementation returns empty list.
        """
        # Stub: requires code_foundation integration
        return []

    # ========== Combined Operations (Convenience) ==========

    async def write_file_with_ir(self, path: str, content: str, txn_id: str) -> None:
        """
        Write file and parse IR (transactional)

        Args:
            path: File path
            content: File content
            txn_id: Transaction ID

        Examples:
            >>> await adapter.write_file_with_ir("main.py", code, txn_id)
        """
        await self._unified_shadowfs.write_file(path, content, txn_id)

    async def delete_file_transactional(self, path: str, txn_id: str) -> None:
        """
        Delete file (transactional)

        Args:
            path: File path
            txn_id: Transaction ID
        """
        await self._unified_shadowfs.delete_file(path, txn_id)

    async def find_symbol(self, symbol_name: str, txn_id: str) -> str | None:
        """
        Find symbol by name

        Args:
            symbol_name: Symbol name
            txn_id: Transaction ID

        Returns:
            File path or None
        """
        return await self._unified_shadowfs.find_symbol(symbol_name, txn_id)
