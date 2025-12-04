"""
Git Blame Analysis

Tracks authorship and modification history for code lines.
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BlameInfo:
    """Information about a line from git blame."""

    # Line info
    line_number: int
    line_content: str

    # Commit info
    commit_hash: str
    author_name: str
    author_email: str
    author_date: datetime

    # Committer info (can differ from author)
    committer_name: str
    committer_email: str
    committer_date: datetime

    # Commit message
    commit_summary: str


class GitBlameAnalyzer:
    """
    Analyzes git blame for files to track authorship.

    Example:
        ```python
        analyzer = GitBlameAnalyzer("/path/to/repo")

        # Get blame for entire file
        blame_data = analyzer.blame_file("src/module.py")
        for line_num, blame in blame_data.items():
            print(f"Line {line_num}: {blame.author_name} on {blame.author_date}")

        # Get blame for specific function
        function_blame = analyzer.blame_range("src/module.py", start=10, end=25)
        ```
    """

    def __init__(self, repo_path: str | Path):
        """
        Initialize git blame analyzer.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {repo_path}")

    def blame_file(self, file_path: str, commit: str = "HEAD") -> dict[int, BlameInfo]:
        """
        Get git blame for entire file.

        Args:
            file_path: Relative path to file from repo root
            commit: Commit to blame (default: HEAD)

        Returns:
            Dictionary mapping line numbers to BlameInfo
        """
        # Run git blame with porcelain format for easy parsing
        cmd = [
            "git",
            "blame",
            "--porcelain",
            commit,
            "--",
            file_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Git blame failed for {file_path}: {e.stderr}") from e

        return self._parse_blame_output(result.stdout)

    def blame_range(self, file_path: str, start: int, end: int, commit: str = "HEAD") -> dict[int, BlameInfo]:
        """
        Get git blame for specific line range.

        Args:
            file_path: Relative path to file from repo root
            start: Starting line number (1-indexed)
            end: Ending line number (inclusive)
            commit: Commit to blame

        Returns:
            Dictionary mapping line numbers to BlameInfo
        """
        cmd = [
            "git",
            "blame",
            "--porcelain",
            f"-L{start},{end}",
            commit,
            "--",
            file_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Git blame failed for {file_path}:{start}-{end}: {e.stderr}") from e

        return self._parse_blame_output(result.stdout)

    def _parse_blame_output(self, output: str) -> dict[int, BlameInfo]:
        """
        Parse git blame porcelain output.

        Porcelain format is machine-readable:
        <commit> <original-line> <final-line> <num-lines>
        author <author-name>
        author-mail <author-email>
        author-time <timestamp>
        ...
        \t<line-content>
        """
        blame_data = {}
        lines = output.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # First line: <commit> <original-line> <final-line> <num-lines>
            parts = line.split()
            if len(parts) < 3:
                i += 1
                continue

            commit_hash = parts[0]
            line_number = int(parts[2])

            # Parse metadata
            metadata = {}
            i += 1
            while i < len(lines) and not lines[i].startswith("\t"):
                meta_line = lines[i].strip()
                if " " in meta_line:
                    key, value = meta_line.split(" ", 1)
                    metadata[key] = value
                i += 1

            # Parse line content (starts with tab)
            line_content = ""
            if i < len(lines) and lines[i].startswith("\t"):
                line_content = lines[i][1:]  # Remove leading tab
                i += 1

            # Create BlameInfo
            try:
                author_timestamp = int(metadata.get("author-time", "0"))
                committer_timestamp = int(metadata.get("committer-time", "0"))

                blame_info = BlameInfo(
                    line_number=line_number,
                    line_content=line_content,
                    commit_hash=commit_hash,
                    author_name=metadata.get("author", "Unknown"),
                    author_email=metadata.get("author-mail", "").strip("<>"),
                    author_date=datetime.fromtimestamp(author_timestamp),
                    committer_name=metadata.get("committer", "Unknown"),
                    committer_email=metadata.get("committer-mail", "").strip("<>"),
                    committer_date=datetime.fromtimestamp(committer_timestamp),
                    commit_summary=metadata.get("summary", ""),
                )

                blame_data[line_number] = blame_info

            except (ValueError, KeyError):
                # Skip malformed entries
                continue

        return blame_data

    def get_recent_authors(self, file_path: str, days: int = 90) -> dict[str, int]:
        """
        Get authors who modified file in recent days.

        Args:
            file_path: File to analyze
            days: Number of days to look back

        Returns:
            Dictionary mapping author email to number of changes
        """
        cmd = [
            "git",
            "log",
            f"--since={days} days ago",
            "--pretty=format:%ae",
            "--",
            file_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            return {}

        # Count commits per author
        authors = {}
        for email in result.stdout.strip().split("\n"):
            if email:
                authors[email] = authors.get(email, 0) + 1

        return authors

    def get_primary_author(self, file_path: str) -> str | None:
        """
        Get primary author (most lines) of a file.

        Args:
            file_path: File to analyze

        Returns:
            Email of primary author
        """
        blame_data = self.blame_file(file_path)
        if not blame_data:
            return None

        # Count lines per author
        author_counts = {}
        for blame_info in blame_data.values():
            email = blame_info.author_email
            author_counts[email] = author_counts.get(email, 0) + 1

        # Return author with most lines
        return max(author_counts, key=author_counts.get)


def _example_usage():
    """Example demonstrating git blame usage."""
    # Initialize analyzer
    analyzer = GitBlameAnalyzer(".")

    # Blame entire file
    print("=== Blaming src/memory/working.py ===")
    blame = analyzer.blame_file("src/memory/working.py")

    # Show first 5 lines
    for line_num in sorted(blame.keys())[:5]:
        info = blame[line_num]
        print(f"Line {line_num}: {info.author_name} ({info.author_date.date()})")
        print(f"  {info.line_content[:60]}...")

    # Get recent authors
    print("\n=== Recent authors (last 90 days) ===")
    recent = analyzer.get_recent_authors("src/memory/working.py", days=90)
    for email, count in sorted(recent.items(), key=lambda x: x[1], reverse=True):
        print(f"{email}: {count} commits")

    # Get primary author
    primary = analyzer.get_primary_author("src/memory/working.py")
    print(f"\nPrimary author: {primary}")


if __name__ == "__main__":
    _example_usage()
