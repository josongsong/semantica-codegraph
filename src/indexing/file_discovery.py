"""
File Discovery Utilities

Utilities for discovering and filtering source files for indexing.
"""

import mimetypes
from pathlib import Path

from .models import IndexingConfig


class FileDiscovery:
    """Discovers and filters source files for indexing."""

    def __init__(self, config: IndexingConfig):
        """
        Initialize file discovery.

        Args:
            config: Indexing configuration
        """
        self.config = config

        # Language to extensions mapping
        self.language_extensions = {
            "python": [".py", ".pyi"],
            "typescript": [".ts", ".tsx"],
            "javascript": [".js", ".jsx", ".mjs", ".cjs"],
            "java": [".java"],
            "go": [".go"],
            "rust": [".rs"],
            "c": [".c", ".h"],
            "cpp": [".cpp", ".hpp", ".cc", ".hh", ".cxx", ".hxx"],
        }

    def discover_files(
        self, repo_path: Path, changed_files: list[str] | None = None
    ) -> list[Path]:
        """
        Discover source files in repository.

        Args:
            repo_path: Path to repository
            changed_files: If provided, only return these files (for incremental)

        Returns:
            List of file paths to process
        """
        if changed_files is not None:
            # Incremental mode: only process changed files
            discovered = []
            for file_path_str in changed_files:
                file_path = repo_path / file_path_str
                if file_path.exists() and self._should_process_file(file_path):
                    discovered.append(file_path)
            return discovered

        # Full mode: discover all source files
        discovered = []

        for file_path in repo_path.rglob("*"):
            # Skip directories
            if not file_path.is_file():
                continue

            # Check if should process
            if self._should_process_file(file_path):
                discovered.append(file_path)

        return discovered

    def _should_process_file(self, file_path: Path) -> bool:
        """
        Check if a file should be processed.

        Args:
            file_path: Path to file

        Returns:
            True if file should be processed
        """
        # Check if in excluded directory
        for excluded_dir in self.config.excluded_dirs:
            if excluded_dir in file_path.parts:
                return False

        # Check file extension
        if file_path.suffix in self.config.excluded_extensions:
            return False

        # Check if it's a supported language
        if not self._is_supported_language(file_path):
            return False

        # Check file size
        try:
            file_size_mb = file_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.config.max_file_size_mb:
                return False
        except OSError:
            return False

        # Check if it's a text file
        if not self._is_text_file(file_path):
            return False

        return True

    def _is_supported_language(self, file_path: Path) -> bool:
        """Check if file is a supported language."""
        extension = file_path.suffix.lower()

        for lang in self.config.supported_languages:
            lang_extensions = self.language_extensions.get(lang, [])
            if extension in lang_extensions:
                return True

        return False

    def _is_text_file(self, file_path: Path) -> bool:
        """
        Check if file is a text file.

        Args:
            file_path: Path to file

        Returns:
            True if text file
        """
        # Check by extension first
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if mime_type and mime_type.startswith("text/"):
            return True

        # Check by reading first bytes
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(512)
                # Check for null bytes (binary indicator)
                if b"\x00" in chunk:
                    return False
                return True
        except (OSError, UnicodeDecodeError):
            return False

    def get_language(self, file_path: Path) -> str | None:
        """
        Determine the programming language of a file.

        Args:
            file_path: Path to file

        Returns:
            Language name or None
        """
        extension = file_path.suffix.lower()

        for lang, extensions in self.language_extensions.items():
            if extension in extensions:
                return lang

        return None

    def get_file_stats(self, files: list[Path]) -> dict:
        """
        Get statistics about discovered files.

        Args:
            files: List of file paths

        Returns:
            Statistics dictionary
        """
        stats = {
            "total_files": len(files),
            "by_language": {},
            "total_size_mb": 0.0,
        }

        for file_path in files:
            # Count by language
            lang = self.get_language(file_path)
            if lang:
                stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1

            # Total size
            try:
                size_mb = file_path.stat().st_size / (1024 * 1024)
                stats["total_size_mb"] += size_mb
            except OSError:
                pass

        return stats
