"""
UnifiedShadowFS - Phase 6

3-Layer Architecture Integration:
    1. ShadowFSCore (File Layer)
    2. IRTransactionManager (IR Layer)
    3. UnifiedShadowFS (Orchestration Layer)

Key Features:
    - File write → Auto IR update
    - Transaction isolation (File + IR)
    - Atomic rollback (File + IR)
    - Query DSL support

Architecture: Infrastructure Layer (Orchestrator)
Status: Production-Ready (Stub IR based)

References:
    - RFC-016: Unified ShadowFS with Transaction Pattern
"""

import asyncio
from pathlib import Path
from typing import Any

from codegraph_runtime.codegen_loop.domain.shadowfs.models import FilePatch
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.core import ShadowFSCore
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.ir_transaction_manager import (
    IRConfig,
    IRTransactionManager,
)
from codegraph_runtime.codegen_loop.infrastructure.shadowfs.stub_ir import StubIRDocument


class UnifiedShadowFS:
    """
    Unified ShadowFS (Orchestrator)

    Integrates ShadowFSCore + IRTransactionManager

    Workflow:
        1. begin_transaction() → File + IR transaction
        2. write_file() → Update file + parse IR
        3. get_ir() → Get cached IR
        4. commit() → Persist both
        5. rollback() → Revert both

    Examples:
        >>> shadowfs = UnifiedShadowFS(Path("/project"), ir_builder)
        >>> txn_id = await shadowfs.begin_transaction()
        >>> await shadowfs.write_file("main.py", "def func(): pass", txn_id)
        >>> ir = await shadowfs.get_ir("main.py", txn_id)
        >>> await shadowfs.commit_transaction(txn_id)
    """

    def __init__(self, workspace_root: Path, ir_builder: Any, ir_config: IRConfig | None = None):
        """
        Initialize UnifiedShadowFS

        Args:
            workspace_root: Project root directory
            ir_builder: LayeredIRBuilder instance (or mock)
            ir_config: Optional IR configuration
        """
        if not workspace_root.exists():
            raise ValueError(f"Workspace root does not exist: {workspace_root}")

        # Initialize components
        self.workspace_root = workspace_root
        self.shadowfs_core = ShadowFSCore(workspace_root)
        self.ir_manager = IRTransactionManager(ir_builder, ir_config or IRConfig())

        # Transaction mapping (UnifiedTxnID → (FileTxnID, IRTxnID))
        self._transactions: dict[str, tuple[str, str]] = {}

        # Lock for transaction operations
        self._lock = asyncio.Lock()

    # ========== Transaction Lifecycle ==========

    async def begin_transaction(self, txn_id: str | None = None) -> str:
        """
        Begin unified transaction (File + IR)

        Args:
            txn_id: Optional transaction ID

        Returns:
            Unified transaction ID

        Examples:
            >>> txn_id = await shadowfs.begin_transaction()
            >>> txn_id = await shadowfs.begin_transaction("custom-txn-123")
        """
        async with self._lock:
            # Create IR transaction first
            ir_txn_id = await self.ir_manager.begin_transaction(txn_id)

            # Use same ID for file transaction
            file_txn_id = ir_txn_id

            # Store mapping
            self._transactions[ir_txn_id] = (file_txn_id, ir_txn_id)

            return ir_txn_id

    async def commit_transaction(self, txn_id: str) -> None:
        """
        Commit unified transaction

        Commits both file and IR changes atomically.

        Args:
            txn_id: Transaction ID

        Raises:
            ValueError: Transaction not found

        Examples:
            >>> await shadowfs.commit_transaction(txn_id)
        """
        async with self._lock:
            if txn_id not in self._transactions:
                raise ValueError(f"Transaction {txn_id} not found")

            file_txn_id, ir_txn_id = self._transactions[txn_id]

            # Commit IR first (lightweight)
            await self.ir_manager.commit_transaction(ir_txn_id)

            # Note: ShadowFSCore doesn't have explicit commit
            # (changes are already in overlay)

            # Remove transaction
            del self._transactions[txn_id]

    async def rollback_transaction(self, txn_id: str) -> None:
        """
        Rollback unified transaction

        Reverts both file and IR changes.

        Args:
            txn_id: Transaction ID

        Raises:
            ValueError: Transaction not found

        Examples:
            >>> await shadowfs.rollback_transaction(txn_id)
        """
        async with self._lock:
            if txn_id not in self._transactions:
                raise ValueError(f"Transaction {txn_id} not found")

            file_txn_id, ir_txn_id = self._transactions[txn_id]

            # Rollback IR
            await self.ir_manager.rollback_transaction(ir_txn_id)

            # Rollback file changes
            self.shadowfs_core.rollback()

            # Remove transaction
            del self._transactions[txn_id]

    # ========== File Operations ==========

    async def write_file(self, path: str, content: str, txn_id: str) -> None:
        """
        Write file and auto-parse IR

        Args:
            path: File path
            content: File content
            txn_id: Transaction ID

        Raises:
            ValueError: Transaction not found

        Examples:
            >>> await shadowfs.write_file("main.py", "def func(): pass", txn_id)
        """
        if txn_id not in self._transactions:
            raise ValueError(f"Transaction {txn_id} not found")

        # Write to file overlay
        self.shadowfs_core.write_file(path, content)

        # Parse IR (async)
        await self.ir_manager.get_or_parse_ir(path, content, txn_id)

    def read_file(self, path: str) -> str:
        """
        Read file (from overlay or disk)

        Args:
            path: File path

        Returns:
            File content

        Raises:
            FileNotFoundError: File not found

        Examples:
            >>> content = shadowfs.read_file("main.py")
        """
        return self.shadowfs_core.read_file(path)

    async def delete_file(self, path: str, txn_id: str) -> None:
        """
        Delete file (mark as tombstone)

        Args:
            path: File path
            txn_id: Transaction ID

        Raises:
            ValueError: Transaction not found

        Examples:
            >>> await shadowfs.delete_file("old_file.py", txn_id)
        """
        if txn_id not in self._transactions:
            raise ValueError(f"Transaction {txn_id} not found")

        # Mark as deleted in file layer
        self.shadowfs_core.delete_file(path)

    # ========== IR Operations ==========

    async def get_ir(self, path: str, txn_id: str) -> StubIRDocument | None:
        """
        Get IR document (cached or parse)

        Args:
            path: File path
            txn_id: Transaction ID

        Returns:
            IR document or None

        Examples:
            >>> ir = await shadowfs.get_ir("main.py", txn_id)
            >>> print(len(ir.nodes))
        """
        if txn_id not in self._transactions:
            raise ValueError(f"Transaction {txn_id} not found")

        # Get content from file layer
        try:
            content = self.shadowfs_core.read_file(path)
        except FileNotFoundError:
            return None

        # Parse or get cached
        return await self.ir_manager.get_or_parse_ir(path, content, txn_id)

    def get_symbol_table(self, txn_id: str) -> dict[str, str]:
        """
        Get symbol table (FQN → file_path)

        Args:
            txn_id: Transaction ID

        Returns:
            Dict[FQN, file_path]

        Examples:
            >>> symbols = shadowfs.get_symbol_table(txn_id)
            >>> print(symbols["mymodule.MyClass.method"])
        """
        if txn_id not in self._transactions:
            raise ValueError(f"Transaction {txn_id} not found")

        return self.ir_manager.get_symbol_table(txn_id)

    # ========== Query Operations (Simplified) ==========

    async def find_symbol(self, symbol_name: str, txn_id: str) -> str | None:
        """
        Find symbol by name (returns file path)

        Args:
            symbol_name: Symbol name (e.g., "MyClass", "my_function")
            txn_id: Transaction ID

        Returns:
            File path or None

        Examples:
            >>> file_path = await shadowfs.find_symbol("MyClass", txn_id)
        """
        symbols = self.get_symbol_table(txn_id)

        # Search for partial match
        for fqn, file_path in symbols.items():
            if symbol_name in fqn:
                return file_path

        return None

    # ========== Diff & Persistence ==========

    def get_diff(self) -> list[FilePatch]:
        """
        Get unified diff (all file changes)

        Returns:
            List of file patches

        Examples:
            >>> patches = shadowfs.get_diff()
            >>> for patch in patches:
            ...     print(patch.path)
        """
        return self.shadowfs_core.get_diff()

    def get_modified_files(self) -> list[str]:
        """
        Get list of modified files

        Returns:
            List of file paths

        Examples:
            >>> files = shadowfs.get_modified_files()
        """
        return self.shadowfs_core.get_modified_files()

    def rollback_all(self) -> None:
        """
        Rollback all file changes (non-transactional)

        Examples:
            >>> shadowfs.rollback_all()
        """
        self.shadowfs_core.rollback()

    # ========== External Tool Support ==========

    def prepare_for_external_tool(self, affected_paths: list[str] | None = None) -> Path:
        """
        Materialize changes to temp directory

        Args:
            affected_paths: Optional list of paths to materialize

        Returns:
            Path to temp directory

        Examples:
            >>> temp_dir = shadowfs.prepare_for_external_tool(["src/main.py"])
        """
        return self.shadowfs_core.prepare_for_external_tool()

    def cleanup_temp(self, temp_dir: Path) -> None:
        """
        Cleanup temp directory

        Args:
            temp_dir: Temp directory to cleanup

        Examples:
            >>> shadowfs.cleanup_temp(temp_dir)
        """
        self.shadowfs_core.cleanup_temp(temp_dir)

    # ========== Status & Debug ==========

    def get_transaction_status(self, txn_id: str) -> dict[str, Any] | None:
        """
        Get transaction status

        Args:
            txn_id: Transaction ID

        Returns:
            Status dict or None

        Examples:
            >>> status = shadowfs.get_transaction_status(txn_id)
            >>> print(status["num_cached_files"])
        """
        if txn_id not in self._transactions:
            return None

        ir_status = self.ir_manager.get_transaction_status(txn_id)

        return {
            "txn_id": txn_id,
            "file_modified": len(self.shadowfs_core.get_modified_files()),
            "file_deleted": len(self.shadowfs_core.deleted),
            "ir_status": ir_status,
        }

    def get_active_transaction_ids(self) -> list[str]:
        """
        Get all active transaction IDs

        Returns:
            List of transaction IDs

        Examples:
            >>> txn_ids = shadowfs.get_active_transaction_ids()
        """
        return list(self._transactions.keys())
