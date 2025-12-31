"""
Transaction Port

Abstract interface for IR transaction management.
"""

from abc import ABC, abstractmethod
from typing import Any


class TransactionPort(ABC):
    """
    Transaction Port (IR Layer)

    Responsibilities:
        - Transaction lifecycle (begin/commit/rollback)
        - IR caching & parsing
        - Symbol table management
        - Edge case handling (23 scenarios)

    NOT responsible for:
        - File operations (handled by ShadowFSPort)
        - Query execution (handled by QueryEngine)

    References:
        - MVCC (Bernstein & Goodman, 1983)
        - Software Transactional Memory (Herlihy & Moss, 1993)

    Examples:
        >>> txn_mgr = IRTransactionManagerAdapter(ir_builder, config)
        >>> txn_id = await txn_mgr.begin_transaction()
        >>> ir = await txn_mgr.get_or_parse_ir("main.py", content, txn_id)
        >>> await txn_mgr.commit_transaction(txn_id)
    """

    @abstractmethod
    async def begin_transaction(self, txn_id: str | None = None) -> str:
        """
        Begin transaction

        Args:
            txn_id: Optional transaction ID (auto-generated if None)

        Returns:
            Transaction ID
        """
        raise NotImplementedError

    @abstractmethod
    async def commit_transaction(self, txn_id: str) -> None:
        """
        Commit transaction

        Action:
            Clear transaction state

        Args:
            txn_id: Transaction ID

        Raises:
            ValueError: Transaction not found
        """
        raise NotImplementedError

    @abstractmethod
    async def rollback_transaction(self, txn_id: str) -> None:
        """
        Rollback transaction

        Action:
            1. Clear IR cache
            2. Explicit disposal (if configured)

        Args:
            txn_id: Transaction ID
        """
        raise NotImplementedError

    @abstractmethod
    async def get_or_parse_ir(self, file_path: str, file_content: str, txn_id: str) -> Any | None:  # Any = IRDocument
        """
        Get or parse IR (with caching)

        Strategy:
            1. Check cache → return if exists
            2. Parse file → cache result

        Args:
            file_path: File path
            file_content: File content (from ShadowFS)
            txn_id: Transaction ID

        Returns:
            IRDocument or None

        Raises:
            ValueError: Transaction not found
        """
        raise NotImplementedError

    @abstractmethod
    def get_symbol_table(self, txn_id: str) -> dict[str, str]:
        """
        Get transaction-specific symbol table

        Features:
            - Lazy build (on first access)
            - FQN → file_path mapping

        Args:
            txn_id: Transaction ID

        Returns:
            Dict[FQN, file_path]

        Raises:
            ValueError: Transaction not found
        """
        raise NotImplementedError

    @abstractmethod
    async def find_callers(self, function_fqn: str, txn_id: str) -> list[str]:
        """
        Find all callers

        Args:
            function_fqn: Target function FQN
            txn_id: Transaction ID

        Returns:
            List of caller FQNs

        Raises:
            ValueError: Transaction not found
        """
        raise NotImplementedError

    @abstractmethod
    def has_transaction(self, txn_id: str) -> bool:
        """
        Check if transaction exists

        Args:
            txn_id: Transaction ID

        Returns:
            True if transaction exists
        """
        raise NotImplementedError

    @abstractmethod
    def get_transaction_age(self, txn_id: str) -> float:
        """
        Get transaction age in seconds

        Args:
            txn_id: Transaction ID

        Returns:
            Age in seconds

        Raises:
            ValueError: Transaction not found
        """
        raise NotImplementedError
