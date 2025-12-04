"""Rollback Manager - All-or-nothing patch application."""

import shutil
from dataclasses import dataclass
from pathlib import Path

from src.infra.observability import get_logger

logger = get_logger(__name__)


@dataclass
class FileBackup:
    """Backup of a file before modification."""

    file_path: Path
    backup_path: Path
    content: str


class RollbackManager:
    """Manages file backups for rollback on failure.

    Provides all-or-nothing guarantees for patch application:
    - Success: all patches applied, backups deleted
    - Failure: all changes rolled back
    """

    def __init__(self, backup_dir: Path | None = None):
        """Initialize rollback manager.

        Args:
            backup_dir: Directory for backups (default: /tmp/codegraph_backups)
        """
        self.backup_dir = backup_dir or Path("/tmp/codegraph_backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.backups: dict[str, FileBackup] = {}

    def backup_file(self, file_path: Path) -> None:
        """Create backup of a file.

        Args:
            file_path: File to backup
        """
        if not file_path.exists():
            # File doesn't exist yet (new file)
            self.backups[str(file_path)] = FileBackup(
                file_path=file_path,
                backup_path=self.backup_dir / f"{file_path.name}.backup",
                content="",
            )
            logger.debug("file_backup_new", file_path=str(file_path))
            return

        # Read current content
        content = file_path.read_text()

        # Create backup file
        backup_path = self.backup_dir / f"{file_path.name}.{file_path.stat().st_mtime}.backup"
        backup_path.write_text(content)

        self.backups[str(file_path)] = FileBackup(
            file_path=file_path,
            backup_path=backup_path,
            content=content,
        )

        logger.debug(
            "file_backed_up",
            file_path=str(file_path),
            backup_path=str(backup_path),
        )

    def rollback(self) -> None:
        """Rollback all changes to backed up state."""
        for file_path_str, backup in self.backups.items():
            try:
                if not backup.content:
                    # File was newly created, delete it
                    if backup.file_path.exists():
                        backup.file_path.unlink()
                        logger.info("file_deleted_rollback", file_path=file_path_str)
                else:
                    # Restore from backup
                    backup.file_path.write_text(backup.content)
                    logger.info(
                        "file_restored",
                        file_path=file_path_str,
                        from_backup=str(backup.backup_path),
                    )
            except Exception as e:
                logger.error(
                    "rollback_failed",
                    file_path=file_path_str,
                    error=str(e),
                )

    def commit(self) -> None:
        """Commit changes by deleting backups."""
        for backup in self.backups.values():
            if backup.backup_path.exists():
                backup.backup_path.unlink()

        logger.info("backups_committed", count=len(self.backups))
        self.backups.clear()

    def cleanup(self) -> None:
        """Clean up backup directory."""
        if self.backup_dir.exists():
            shutil.rmtree(self.backup_dir)
            self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.debug("backups_cleaned_up")
