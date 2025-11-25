"""
IR Generator Adapter

Wraps language-specific IR generators to provide a unified interface
for chunk refresh operations, with support for incremental parsing.
"""

from typing import Protocol

from ..generators.base import IRGenerator
from ..ir.models import IRDocument
from ..parsing import SourceFile
from .git_loader import GitFileLoader


class IRGeneratorProtocol(Protocol):
    """Protocol for IR generation operations."""

    def generate_for_file(
        self, repo_id: str, file_path: str, commit: str
    ) -> IRDocument:
        """Generate IR for a file at a specific commit."""
        ...


class IRGeneratorAdapter:
    """
    Adapter for IR generators with incremental parsing support.

    Wraps PythonIRGenerator (or other language generators) to provide
    a unified interface for chunk refresh operations.

    Responsibilities:
    - Load file content from git
    - Create SourceFile instances
    - Call generator.generate() with incremental parsing params when available
    """

    def __init__(
        self,
        generator: IRGenerator,
        git_loader: GitFileLoader,
        language: str = "python",
    ):
        """
        Initialize IR generator adapter.

        Args:
            generator: Language-specific IR generator (e.g., PythonIRGenerator)
            git_loader: Git file loader for fetching file content
            language: Programming language (default: "python")
        """
        self.generator = generator
        self.git_loader = git_loader
        self.language = language

    def generate_for_file(
        self,
        repo_id: str,
        file_path: str,
        commit: str,
        old_commit: str | None = None,
    ) -> IRDocument:
        """
        Generate IR for a file at a specific commit.

        Supports incremental parsing when old_commit is provided.

        Args:
            repo_id: Repository identifier
            file_path: Path to file in repository
            commit: Current commit hash
            old_commit: Previous commit hash (for incremental parsing)

        Returns:
            IRDocument for the file
        """
        # Load new file content
        new_content = self.git_loader.get_file_at_commit(file_path, commit)

        # Create source file
        source = SourceFile(
            file_path=file_path,
            content=new_content,
            language=self.language,
            encoding="utf-8",
        )

        # Check if we can use incremental parsing
        if old_commit is not None:
            try:
                # Load old content
                old_content = self.git_loader.get_file_at_commit(file_path, old_commit)

                # Get diff
                diff_text = self.git_loader.get_file_diff(
                    file_path, old_commit, commit
                )

                # Generate IR with incremental parsing
                if diff_text:  # Only use incremental if there's a diff
                    return self.generator.generate(
                        source=source,
                        snapshot_id=commit,
                        old_content=old_content,
                        diff_text=diff_text,
                    )
            except Exception:
                # Fall back to full parsing if incremental fails
                pass

        # Full parsing (no old_commit or incremental failed)
        return self.generator.generate(source=source, snapshot_id=commit)
