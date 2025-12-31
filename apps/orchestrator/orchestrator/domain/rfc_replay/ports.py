"""
RFC Replay Ports (RFC-027 Section 9)

Port interfaces for audit log storage (Hexagonal Architecture).
"""

from abc import ABC, abstractmethod

from apps.orchestrator.orchestrator.domain.rfc_replay.models import RequestAuditLog


class IAuditStore(ABC):
    """
    AuditStore Port (Hexagonal Architecture)

    Interface for audit log persistence.

    Responsibilities:
    - Save audit logs
    - Retrieve audit logs
    - List audit logs

    Implementations:
    - SQLiteAuditStore (Infrastructure layer)
    - PostgreSQLAuditStore (Future)
    """

    @abstractmethod
    def save(self, log: RequestAuditLog) -> None:
        """
        Save audit log.

        Args:
            log: RequestAuditLog to save

        Raises:
            RuntimeError: If save fails
        """
        pass

    @abstractmethod
    def get(self, request_id: str) -> RequestAuditLog | None:
        """
        Get audit log by request_id.

        Args:
            request_id: Request ID

        Returns:
            RequestAuditLog or None if not found
        """
        pass

    @abstractmethod
    def list(self, limit: int = 100) -> list[RequestAuditLog]:
        """
        List recent audit logs.

        Args:
            limit: Maximum number of logs

        Returns:
            List of RequestAuditLog (newest first)
        """
        pass
