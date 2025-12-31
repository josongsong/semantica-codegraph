"""
Co-change Pattern Analysis

Identifies files that frequently change together.
Co-change patterns indicate:
- Logical coupling (files depend on each other)
- Missing abstractions (should be refactored together)
- Test-code relationships
"""

import subprocess
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CoChangePattern:
    """Co-change pattern between files."""

    # Files involved
    file_a: str
    file_b: str

    # Statistics
    cochange_count: int = 0  # Times changed together
    file_a_changes: int = 0  # Total changes to file A
    file_b_changes: int = 0  # Total changes to file B

    # Derived metrics
    coupling_strength: float = 0.0  # 0-1, how often they change together
    confidence_a_to_b: float = 0.0  # P(B changes | A changes)
    confidence_b_to_a: float = 0.0  # P(A changes | B changes)

    # Commit details
    cochange_commits: list[str] = field(default_factory=list)

    def calculate_metrics(self) -> None:
        """Calculate derived coupling metrics."""
        if self.file_a_changes > 0:
            self.confidence_a_to_b = self.cochange_count / self.file_a_changes

        if self.file_b_changes > 0:
            self.confidence_b_to_a = self.cochange_count / self.file_b_changes

        # Coupling strength: Jaccard similarity
        total_changes = self.file_a_changes + self.file_b_changes - self.cochange_count
        if total_changes > 0:
            self.coupling_strength = self.cochange_count / total_changes


class CoChangeAnalyzer:
    """
    Analyzes co-change patterns to identify coupled files.

    Example:
        ```python
        analyzer = CoChangeAnalyzer("/path/to/repo")

        # Find files that change with api.py
        patterns = analyzer.find_cochanges("src/api.py", days=90)
        for pattern in patterns:
            print(f"{pattern.file_b}: {pattern.coupling_strength:.2%} coupled")

        # Find strongly coupled pairs
        strong_couples = analyzer.find_strong_couples(
            min_cochanges=5,
            min_coupling=0.5
        )
        ```
    """

    def __init__(self, repo_path: str | Path):
        """
        Initialize co-change analyzer.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {repo_path}")

    def find_cochanges(
        self,
        target_file: str,
        days: int | None = None,
        min_cochanges: int = 2,
    ) -> list[CoChangePattern]:
        """
        Find files that co-change with target file.

        Args:
            target_file: File to analyze
            days: Number of days to look back (optional)
            min_cochanges: Minimum number of co-changes to include

        Returns:
            List of CoChangePatterns sorted by coupling strength
        """
        # Get commits that modified target file
        cmd_target = [
            "git",
            "log",
            "--pretty=format:%H",
            "--",
            target_file,
        ]

        if days:
            cmd_target.insert(2, f"--since={days} days ago")

        try:
            result = subprocess.run(
                cmd_target,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            return []

        target_commits = set(result.stdout.strip().split("\n"))
        if not target_commits:
            return []

        # Get all files changed in those commits
        cochange_counts = defaultdict(int)
        file_change_counts = defaultdict(int)

        for commit in target_commits:
            if not commit:
                continue

            # Get files changed in this commit
            cmd_files = [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit,
            ]

            try:
                result = subprocess.run(
                    cmd_files,
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError:
                continue

            files_in_commit = set(result.stdout.strip().split("\n"))

            # Count co-changes
            for file_path in files_in_commit:
                if file_path and file_path != target_file:
                    cochange_counts[file_path] += 1
                    file_change_counts[file_path] += 1

        # Build CoChangePatterns
        patterns = []
        for file_path, cochange_count in cochange_counts.items():
            if cochange_count < min_cochanges:
                continue

            pattern = CoChangePattern(
                file_a=target_file,
                file_b=file_path,
                cochange_count=cochange_count,
                file_a_changes=len(target_commits),
                file_b_changes=file_change_counts[file_path],
            )
            pattern.calculate_metrics()
            patterns.append(pattern)

        # Sort by coupling strength
        patterns.sort(key=lambda p: p.coupling_strength, reverse=True)

        return patterns

    def find_strong_couples(
        self,
        days: int | None = 90,
        min_cochanges: int = 5,
        min_coupling: float = 0.5,
        dir_path: str = ".",
    ) -> list[CoChangePattern]:
        """
        Find strongly coupled file pairs.

        Args:
            days: Number of days to analyze
            min_cochanges: Minimum co-change count
            min_coupling: Minimum coupling strength (0-1)
            dir_path: Directory to analyze

        Returns:
            List of strongly coupled pairs
        """
        # Get all commits in directory
        cmd = [
            "git",
            "log",
            "--pretty=format:%H",
            "--",
            dir_path,
        ]

        if days:
            cmd.insert(2, f"--since={days} days ago")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            return []

        commits = [c for c in result.stdout.strip().split("\n") if c]

        # Track file pairs that change together
        pair_cochanges: dict[tuple[str, str], dict[str, int | list[str]]] = defaultdict(
            lambda: {"count": 0, "commits": []}
        )
        file_commits = defaultdict(set)

        for commit in commits:
            # Get files in commit
            cmd_files = [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit,
            ]

            try:
                result = subprocess.run(
                    cmd_files,
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError:
                continue

            files = [f for f in result.stdout.strip().split("\n") if f]

            # Record file changes
            for file_path in files:
                file_commits[file_path].add(commit)

            # Record co-changes (all pairs in commit)
            for i, file_a in enumerate(files):
                for file_b in files[i + 1 :]:
                    # Ensure consistent ordering
                    if file_a > file_b:
                        file_a, file_b = file_b, file_a

                    pair_key = (file_a, file_b)
                    entry = pair_cochanges[pair_key]
                    entry["count"] = int(entry["count"]) + 1
                    commits_list = entry["commits"]
                    if isinstance(commits_list, list):
                        commits_list.append(commit)

        # Build patterns
        patterns = []
        for (file_a, file_b), data in pair_cochanges.items():
            count = int(data["count"])
            if count < min_cochanges:
                continue

            commits_data = data["commits"]
            pattern = CoChangePattern(
                file_a=file_a,
                file_b=file_b,
                cochange_count=count,
                file_a_changes=len(file_commits[file_a]),
                file_b_changes=len(file_commits[file_b]),
                cochange_commits=commits_data if isinstance(commits_data, list) else [],
            )
            pattern.calculate_metrics()

            if pattern.coupling_strength >= min_coupling:
                patterns.append(pattern)

        # Sort by coupling strength
        patterns.sort(key=lambda p: p.coupling_strength, reverse=True)

        return patterns

    def find_cluster(self, file_path: str, days: int = 90, threshold: float = 0.3) -> set[str]:
        """
        Find cluster of related files (transitive co-changes).

        Args:
            file_path: Starting file
            days: Days to analyze
            threshold: Minimum coupling strength to include

        Returns:
            Set of related file paths
        """
        cluster = {file_path}
        to_process = [file_path]

        while to_process:
            current = to_process.pop()

            # Find co-changes
            cochanges = self.find_cochanges(current, days=days, min_cochanges=2)

            # Add strongly coupled files
            for pattern in cochanges:
                if pattern.coupling_strength >= threshold:
                    if pattern.file_b not in cluster:
                        cluster.add(pattern.file_b)
                        to_process.append(pattern.file_b)

        return cluster


def _example_usage():
    """Example demonstrating co-change analysis."""
    analyzer = CoChangeAnalyzer(".")

    # Find co-changes for a file
    print("=== Files that co-change with src/memory/working.py ===")
    patterns = analyzer.find_cochanges("src/memory/working.py", days=90, min_cochanges=2)

    for i, pattern in enumerate(patterns[:10], 1):
        print(f"{i}. {pattern.file_b}")
        print(f"   Co-changes: {pattern.cochange_count}")
        print(f"   Coupling: {pattern.coupling_strength:.2%}")
        print(f"   Confidence: {pattern.confidence_a_to_b:.2%}")

    # Find strong couples
    print("\n=== Strongly Coupled Pairs ===")
    couples = analyzer.find_strong_couples(days=90, min_cochanges=5, min_coupling=0.5)

    for i, pattern in enumerate(couples[:5], 1):
        print(f"{i}. {pattern.file_a} <-> {pattern.file_b}")
        print(f"   Coupling: {pattern.coupling_strength:.2%}")
        print(f"   Co-changes: {pattern.cochange_count}")

    # Find cluster
    print("\n=== File Cluster for src/memory/working.py ===")
    cluster = analyzer.find_cluster("src/memory/working.py", days=90, threshold=0.3)
    print(f"Cluster size: {len(cluster)} files")
    for file_path in sorted(cluster)[:10]:
        print(f"  - {file_path}")


if __name__ == "__main__":
    _example_usage()
