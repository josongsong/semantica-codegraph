"""
Git History Integration for RepoMap

Computes change frequency metrics from git history.

Phase 1 (P0-1) Implementation:
1. Git Blame Integration - Line-level authorship
2. Code Churn Metrics - Change frequency (DONE)
3. Evolution Graph - Co-change mining
4. Incremental Update - Delta-based updates

Metrics:
- change_freq: commits per month for each file/symbol
- last_modified: timestamp of last modification
- contributors: number of unique contributors
- churn_score: change frequency / time
- stability_index: 1 / change_freq
- co_change_files: files frequently modified together
"""

import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.contexts.repo_structure.infrastructure.models import RepoMapNode


@dataclass
class BlameInfo:
    """Line-level blame information."""

    author: str
    author_email: str
    commit_sha: str
    commit_time: datetime
    line_content: str
    line_number: int


@dataclass
class FileBlame:
    """Complete blame information for a file."""

    file_path: str
    lines: list[BlameInfo] = field(default_factory=list)

    @property
    def primary_author(self) -> str:
        """Get author who wrote the most lines."""
        if not self.lines:
            return "unknown"
        author_lines = defaultdict(int)
        for line in self.lines:
            author_lines[line.author] += 1
        return max(author_lines.items(), key=lambda x: x[1])[0]

    @property
    def last_modified_by(self) -> str:
        """Get author of most recent change."""
        if not self.lines:
            return "unknown"
        most_recent = max(self.lines, key=lambda x: x.commit_time)
        return most_recent.author


@dataclass
class CoChangePattern:
    """Files that are frequently changed together."""

    file1: str
    file2: str
    co_change_count: int
    confidence: float  # co_change_count / total_changes


@dataclass
class EvolutionGraph:
    """Graph of file evolution and co-change patterns."""

    patterns: list[CoChangePattern] = field(default_factory=list)

    def get_related_files(self, file_path: str, min_confidence: float = 0.3) -> list[tuple[str, float]]:
        """
        Get files frequently changed with given file.

        Args:
            file_path: Target file path
            min_confidence: Minimum confidence threshold

        Returns:
            List of (related_file, confidence) tuples sorted by confidence
        """
        related = []
        for pattern in self.patterns:
            if pattern.file1 == file_path and pattern.confidence >= min_confidence:
                related.append((pattern.file2, pattern.confidence))
            elif pattern.file2 == file_path and pattern.confidence >= min_confidence:
                related.append((pattern.file1, pattern.confidence))

        related.sort(key=lambda x: x[1], reverse=True)
        return related


class GitHistoryAnalyzer:
    """
    Analyze git history to compute change frequency metrics.

    Uses git log to extract:
    - Commit frequency (commits per month)
    - Last modification time
    - Number of contributors
    """

    def __init__(self, repo_path: str):
        """
        Initialize Git history analyzer.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)

    def compute_change_freq(self, nodes: list[RepoMapNode], lookback_months: int = 6) -> None:
        """
        Compute change frequency for RepoMap nodes (in-place).

        Args:
            nodes: List of RepoMap nodes to update
            lookback_months: Number of months to look back in history
        """
        # Get file paths from nodes
        file_nodes = [n for n in nodes if n.path and n.kind in ("file", "dir")]
        if not file_nodes:
            return

        # Compute per-file statistics
        file_stats = self._get_file_stats(lookback_months)

        # Update node metrics
        for node in nodes:
            if node.path and node.path in file_stats:
                stats = file_stats[node.path]
                node.metrics.change_freq = stats["change_freq"]
                # Store additional metadata
                node.attrs["last_modified"] = stats["last_modified"]
                node.attrs["contributor_count"] = stats["contributor_count"]

    def _get_file_stats(self, lookback_months: int) -> dict[str, dict]:
        """
        Get git statistics for all files.

        Args:
            lookback_months: Number of months to look back

        Returns:
            Dict mapping file_path to stats dict
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=lookback_months * 30)
        since_str = since_date.strftime("%Y-%m-%d")

        try:
            # Get commit history with file changes
            # Format: commit_hash|author|date|file_path
            result = subprocess.run(
                [
                    "git",
                    "log",
                    f"--since={since_str}",
                    "--name-only",
                    "--format=%H|%an|%aI",
                    "--",
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            return self._parse_git_log(result.stdout, lookback_months)

        except subprocess.CalledProcessError as e:
            print(f"Git log error: {e}")
            return {}

    def _parse_git_log(self, log_output: str, lookback_months: int) -> dict[str, dict]:
        """
        Parse git log output and compute file statistics.

        Args:
            log_output: Raw git log output
            lookback_months: Number of months for normalization

        Returns:
            Dict mapping file_path to stats
        """
        # Track commits per file
        file_commits: dict[str, set[str]] = defaultdict(set)
        file_authors: dict[str, set[str]] = defaultdict(set)
        file_last_modified: dict[str, datetime] = {}

        lines = log_output.strip().split("\n")
        current_commit = None
        current_author = None
        current_date = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Parse commit line: hash|author|date
            if "|" in line:
                parts = line.split("|")
                if len(parts) == 3:
                    current_commit = parts[0]
                    current_author = parts[1]
                    try:
                        current_date = datetime.fromisoformat(parts[2].replace("Z", "+00:00"))
                    except ValueError:
                        current_date = None
                    continue

            # File path line
            if current_commit and line:
                file_path = line
                file_commits[file_path].add(current_commit)
                if current_author:
                    file_authors[file_path].add(current_author)
                if current_date:
                    # Track most recent modification
                    if file_path not in file_last_modified or current_date > file_last_modified[file_path]:
                        file_last_modified[file_path] = current_date

        # Compute statistics
        stats = {}
        for file_path in file_commits:
            commit_count = len(file_commits[file_path])
            # Normalize to commits per month
            change_freq = commit_count / max(1, lookback_months)

            stats[file_path] = {
                "change_freq": round(change_freq, 2),
                "last_modified": (
                    file_last_modified[file_path].isoformat() if file_path in file_last_modified else None
                ),
                "contributor_count": len(file_authors.get(file_path, set())),
            }

        return stats

    def get_hotspots(self, top_n: int = 20, lookback_months: int = 6) -> list[dict]:
        """
        Get top N most frequently changed files (hotspots).

        Args:
            top_n: Number of hotspots to return
            lookback_months: Number of months to analyze

        Returns:
            List of {file_path, change_freq, contributor_count}
        """
        file_stats = self._get_file_stats(lookback_months)

        # Sort by change frequency
        hotspots = [
            {
                "file_path": path,
                "change_freq": stats["change_freq"],
                "contributor_count": stats["contributor_count"],
                "last_modified": stats["last_modified"],
            }
            for path, stats in file_stats.items()
        ]

        hotspots.sort(key=lambda x: x["change_freq"], reverse=True)
        return hotspots[:top_n]

    # ============================================================
    # P0-1: Git Blame Integration
    # ============================================================

    def get_file_blame(self, file_path: str) -> FileBlame | None:
        """
        Get line-by-line blame information for a file.

        Uses git blame to track:
        - Who wrote each line
        - When each line was last modified
        - Which commit introduced each line

        Args:
            file_path: Path to file relative to repo root

        Returns:
            FileBlame object or None if file doesn't exist
        """
        full_path = self.repo_path / file_path

        if not full_path.exists():
            return None

        try:
            # git blame with porcelain format for easier parsing
            result = subprocess.run(
                [
                    "git",
                    "blame",
                    "--porcelain",
                    "--",
                    file_path,
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            return self._parse_blame_output(file_path, result.stdout)

        except subprocess.CalledProcessError as e:
            print(f"Git blame error for {file_path}: {e}")
            return None

    def _parse_blame_output(self, file_path: str, blame_output: str) -> FileBlame:
        """
        Parse git blame porcelain output.

        Porcelain format:
        <commit_sha> <orig_line> <final_line> <num_lines>
        author <author_name>
        author-mail <author_email>
        author-time <unix_timestamp>
        ...
        \t<line_content>

        Args:
            file_path: File path
            blame_output: Raw git blame output

        Returns:
            FileBlame object
        """
        lines = blame_output.split("\n")
        blame_lines = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Start of a new blame block
            if not line:
                i += 1
                continue

            # Parse commit line: <commit> <orig_line> <final_line> <num_lines>
            parts = line.split()
            if len(parts) < 3:
                i += 1
                continue

            commit_sha = parts[0]
            final_line_num = int(parts[2])

            # Parse metadata
            author = ""
            author_email = ""
            commit_time = None

            i += 1
            while i < len(lines):
                meta_line = lines[i]
                if meta_line.startswith("\t"):
                    # This is the actual line content
                    line_content = meta_line[1:]  # Remove leading tab

                    if commit_time:
                        blame_lines.append(
                            BlameInfo(
                                author=author,
                                author_email=author_email,
                                commit_sha=commit_sha,
                                commit_time=commit_time,
                                line_content=line_content,
                                line_number=final_line_num,
                            )
                        )

                    i += 1
                    break

                # Parse metadata fields
                if meta_line.startswith("author "):
                    author = meta_line[7:]
                elif meta_line.startswith("author-mail "):
                    author_email = meta_line[12:].strip("<>")
                elif meta_line.startswith("author-time "):
                    try:
                        timestamp = int(meta_line[12:])
                        commit_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                    except ValueError:
                        pass

                i += 1

        return FileBlame(file_path=file_path, lines=blame_lines)

    # ============================================================
    # P0-1: Evolution Graph (Co-change Mining)
    # ============================================================

    def compute_evolution_graph(self, lookback_months: int = 6, min_co_changes: int = 3) -> EvolutionGraph:
        """
        Compute file evolution graph by mining co-change patterns.

        Identifies files that are frequently modified together in the same commit.
        This reveals implicit dependencies and modularity violations.

        Args:
            lookback_months: Number of months to analyze
            min_co_changes: Minimum co-change count to include pattern

        Returns:
            EvolutionGraph with co-change patterns
        """
        since_date = datetime.now(timezone.utc) - timedelta(days=lookback_months * 30)
        since_str = since_date.strftime("%Y-%m-%d")

        try:
            # Get commits with changed files
            result = subprocess.run(
                [
                    "git",
                    "log",
                    f"--since={since_str}",
                    "--name-only",
                    "--format=%H",
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            return self._parse_co_changes(result.stdout, min_co_changes)

        except subprocess.CalledProcessError as e:
            print(f"Git log error: {e}")
            return EvolutionGraph()

    def _parse_co_changes(self, log_output: str, min_co_changes: int) -> EvolutionGraph:
        """
        Parse git log and extract co-change patterns.

        Args:
            log_output: Raw git log output
            min_co_changes: Minimum threshold

        Returns:
            EvolutionGraph
        """
        lines = log_output.strip().split("\n")

        # Track files per commit
        commit_files: dict[str, set[str]] = defaultdict(set)
        file_changes: dict[str, int] = defaultdict(int)  # Total changes per file
        co_change_count: dict[tuple[str, str], int] = defaultdict(int)

        current_commit = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Commit hash (40 hex chars)
            if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
                current_commit = line
                continue

            # File path
            if current_commit:
                file_path = line
                commit_files[current_commit].add(file_path)
                file_changes[file_path] += 1

        # Compute co-change patterns
        for _commit, files in commit_files.items():
            file_list = sorted(files)  # Sort for consistent ordering
            # Generate all pairs
            for i in range(len(file_list)):
                for j in range(i + 1, len(file_list)):
                    file1, file2 = file_list[i], file_list[j]
                    # Ensure consistent ordering (smaller file first)
                    if file1 > file2:
                        file1, file2 = file2, file1
                    co_change_count[(file1, file2)] += 1

        # Build patterns
        patterns = []
        for (file1, file2), count in co_change_count.items():
            if count >= min_co_changes:
                # Confidence = co_changes / total_changes(file1)
                total_changes = max(file_changes[file1], file_changes[file2])
                confidence = count / total_changes if total_changes > 0 else 0.0

                patterns.append(
                    CoChangePattern(
                        file1=file1,
                        file2=file2,
                        co_change_count=count,
                        confidence=round(confidence, 3),
                    )
                )

        # Sort by co-change count
        patterns.sort(key=lambda x: x.co_change_count, reverse=True)

        return EvolutionGraph(patterns=patterns)

    # ============================================================
    # P0-1: Incremental Update
    # ============================================================

    def incremental_update(
        self,
        since_commit: str,
        cached_stats: dict[str, dict] | None = None,
    ) -> dict[str, dict]:
        """
        Incrementally update file statistics since a commit.

        Instead of re-analyzing entire history, only process changes since
        the given commit hash. Reuses cached statistics for unchanged files.

        Args:
            since_commit: Commit hash to start from
            cached_stats: Previously computed file stats (reused for unchanged files)

        Returns:
            Updated file stats dict
        """
        if cached_stats is None:
            # No cache, do full analysis
            return self._get_file_stats(lookback_months=6)

        try:
            # Get files changed since commit
            result = subprocess.run(
                [
                    "git",
                    "diff",
                    "--name-status",
                    since_commit,
                    "HEAD",
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            changed_files = set()
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                # Format: <status>\t<file_path>
                parts = line.split("\t")
                if len(parts) >= 2:
                    changed_files.add(parts[1])

            # Reuse cached stats for unchanged files
            updated_stats = dict(cached_stats)

            # Re-compute only for changed files
            if changed_files:
                # Get delta stats (commits since since_commit)
                result = subprocess.run(
                    [
                        "git",
                        "log",
                        f"{since_commit}..HEAD",
                        "--name-only",
                        "--format=%H|%an|%aI",
                        "--",
                    ],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )

                # Parse delta and merge with cached stats
                delta_stats = self._parse_git_log(result.stdout, lookback_months=1)

                for file_path in changed_files:
                    if file_path in delta_stats:
                        # Merge delta with cached stats
                        old_stats = cached_stats.get(file_path, {})
                        new_stats = delta_stats[file_path]

                        # Combine metrics (simple additive for now)
                        merged_change_freq = old_stats.get("change_freq", 0) + new_stats.get("change_freq", 0)

                        updated_stats[file_path] = {
                            "change_freq": round(merged_change_freq, 2),
                            "last_modified": new_stats.get("last_modified") or old_stats.get("last_modified"),
                            "contributor_count": new_stats.get("contributor_count", 0)
                            + old_stats.get("contributor_count", 0),
                        }

            return updated_stats

        except subprocess.CalledProcessError as e:
            print(f"Incremental update error: {e}")
            # Fallback to cached stats
            return cached_stats if cached_stats else {}
