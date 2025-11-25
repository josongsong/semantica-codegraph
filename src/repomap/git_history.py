"""
Git History Integration for RepoMap

Computes change frequency metrics from git history.

Metrics:
- change_freq: commits per month for each file/symbol
- last_modified: timestamp of last modification
- contributors: number of unique contributors
"""

import subprocess
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.repomap.models import RepoMapNode


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
