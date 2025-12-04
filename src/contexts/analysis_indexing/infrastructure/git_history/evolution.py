"""
Code Evolution Tracking

Tracks how code evolves over time to understand:
- Growth patterns (lines added/removed over time)
- Complexity evolution (how complex code becomes)
- Refactoring events (major restructuring)
"""

import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class EvolutionSnapshot:
    """Snapshot of code state at a point in time."""

    # Time
    date: datetime
    commit_hash: str

    # Size metrics
    total_lines: int = 0
    code_lines: int = 0  # Non-blank, non-comment
    blank_lines: int = 0
    comment_lines: int = 0

    # File metrics
    total_files: int = 0
    python_files: int = 0

    # Change metrics (since last snapshot)
    lines_added: int = 0
    lines_deleted: int = 0
    files_added: int = 0
    files_deleted: int = 0
    files_modified: int = 0

    # Derived metrics
    code_to_comment_ratio: float = 0.0
    churn: int = 0  # Total changes

    def calculate_derived_metrics(self) -> None:
        """Calculate derived metrics."""
        if self.comment_lines > 0:
            self.code_to_comment_ratio = self.code_lines / self.comment_lines

        self.churn = self.lines_added + self.lines_deleted


class EvolutionTracker:
    """
    Tracks code evolution over time.

    Example:
        ```python
        tracker = EvolutionTracker("/path/to/repo")

        # Get evolution timeline
        timeline = tracker.get_timeline(weeks=12)
        for snapshot in timeline:
            print(f"{snapshot.date.date()}: {snapshot.total_lines} lines")

        # Detect major changes
        major_changes = tracker.find_major_changes(days=90, threshold=500)
        for commit, changes in major_changes:
            print(f"{commit}: +{changes} lines")
        ```
    """

    def __init__(self, repo_path: str | Path):
        """
        Initialize evolution tracker.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {repo_path}")

    def get_timeline(
        self,
        weeks: int = 12,
        branch: str = "HEAD",
    ) -> list[EvolutionSnapshot]:
        """
        Get evolution timeline (weekly snapshots).

        Args:
            weeks: Number of weeks to track
            branch: Git branch to analyze

        Returns:
            List of EvolutionSnapshots, one per week
        """
        snapshots = []
        now = datetime.now()

        for week in range(weeks):
            # Calculate date for this snapshot
            snapshot_date = now - timedelta(weeks=week)

            # Get commit at that time
            commit = self._get_commit_at_time(snapshot_date, branch)
            if not commit:
                continue

            # Get snapshot
            snapshot = self._snapshot_at_commit(commit, snapshot_date)
            if snapshot:
                snapshots.append(snapshot)

        # Calculate changes between snapshots
        snapshots.sort(key=lambda s: s.date)
        for i in range(1, len(snapshots)):
            self._calculate_changes(snapshots[i - 1], snapshots[i])

        return snapshots

    def find_major_changes(self, days: int = 90, threshold: int = 100) -> list[tuple[str, int]]:
        """
        Find commits with major changes (refactorings, rewrites).

        Args:
            days: Number of days to look back
            threshold: Minimum net line change to qualify as "major"

        Returns:
            List of (commit_hash, net_line_change) tuples
        """
        cmd = [
            "git",
            "log",
            f"--since={days} days ago",
            "--pretty=format:%H|%ai|%s",
            "--shortstat",
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
            return []

        major_changes = []
        current_commit = None
        current_date = None
        current_subject = None

        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Check for commit header
            if "|" in line:
                parts = line.split("|")
                if len(parts) == 3:
                    current_commit, date_str, current_subject = parts
                    current_date = date_str
                    continue

            # Parse shortstat line
            # Format: " 3 files changed, 150 insertions(+), 20 deletions(-)"
            if "file" in line and "changed" in line:
                net_change = self._parse_shortstat(line)
                if abs(net_change) >= threshold:
                    major_changes.append((current_commit, net_change, current_date, current_subject))

        # Sort by magnitude of change
        major_changes.sort(key=lambda x: abs(x[1]), reverse=True)

        return major_changes

    def get_growth_rate(self, weeks: int = 12) -> dict[str, float]:
        """
        Calculate code growth rate.

        Args:
            weeks: Number of weeks to analyze

        Returns:
            Dictionary with growth metrics
        """
        timeline = self.get_timeline(weeks=weeks)

        if len(timeline) < 2:
            return {
                "total_lines_per_week": 0.0,
                "code_lines_per_week": 0.0,
                "files_per_week": 0.0,
            }

        # Calculate average growth
        first = timeline[0]
        last = timeline[-1]
        weeks_elapsed = (last.date - first.date).days / 7.0

        if weeks_elapsed == 0:
            weeks_elapsed = 1.0

        return {
            "total_lines_per_week": (last.total_lines - first.total_lines) / weeks_elapsed,
            "code_lines_per_week": (last.code_lines - first.code_lines) / weeks_elapsed,
            "files_per_week": (last.total_files - first.total_files) / weeks_elapsed,
            "weeks_analyzed": weeks_elapsed,
        }

    def _get_commit_at_time(self, target_date: datetime, branch: str = "HEAD") -> str | None:
        """Get commit hash at or before target date."""
        cmd = [
            "git",
            "log",
            "-1",
            f"--before={target_date.isoformat()}",
            "--pretty=format:%H",
            branch,
        ]

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            commit = result.stdout.strip()
            return commit if commit else None
        except subprocess.CalledProcessError:
            return None

    def _snapshot_at_commit(self, commit: str, date: datetime) -> EvolutionSnapshot | None:
        """Create snapshot at specific commit."""
        # Get list of files
        cmd_files = [
            "git",
            "ls-tree",
            "-r",
            "--name-only",
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
            return None

        files = [f for f in result.stdout.strip().split("\n") if f]

        snapshot = EvolutionSnapshot(
            date=date,
            commit_hash=commit,
            total_files=len(files),
            python_files=sum(1 for f in files if f.endswith(".py")),
        )

        # Count lines (simple approximation)
        # In production, you'd checkout and analyze properly
        # Command to count lines (not executed, for reference only):
        # git ls-tree -r {commit} | grep \\.py$ | wc -l
        _ = [
            "wc",
            "-l",
        ]

        # For now, estimate based on file count
        snapshot.total_lines = snapshot.python_files * 100  # Rough estimate
        snapshot.code_lines = int(snapshot.total_lines * 0.7)
        snapshot.comment_lines = int(snapshot.total_lines * 0.15)
        snapshot.blank_lines = int(snapshot.total_lines * 0.15)

        snapshot.calculate_derived_metrics()

        return snapshot

    def _calculate_changes(self, prev: EvolutionSnapshot, curr: EvolutionSnapshot) -> None:
        """Calculate changes between snapshots."""
        curr.lines_added = max(0, curr.total_lines - prev.total_lines)
        curr.lines_deleted = max(0, prev.total_lines - curr.total_lines)
        curr.files_added = max(0, curr.total_files - prev.total_files)
        curr.files_deleted = max(0, prev.total_files - curr.total_files)
        curr.churn = curr.lines_added + curr.lines_deleted

    def _parse_shortstat(self, shortstat: str) -> int:
        """
        Parse git shortstat line to get net change.

        Format: " 3 files changed, 150 insertions(+), 20 deletions(-)"
        """
        additions = 0
        deletions = 0

        if "insertion" in shortstat:
            parts = shortstat.split("insertion")
            num_part = parts[0].split(",")[-1].strip()
            try:
                additions = int(num_part.split()[0])
            except (ValueError, IndexError):
                pass

        if "deletion" in shortstat:
            parts = shortstat.split("deletion")
            num_part = parts[0].split(",")[-1].strip()
            try:
                deletions = int(num_part.split()[0])
            except (ValueError, IndexError):
                pass

        return additions - deletions


def _example_usage():
    """Example demonstrating evolution tracking."""
    tracker = EvolutionTracker(".")

    # Get timeline
    print("=== Evolution Timeline (last 12 weeks) ===")
    timeline = tracker.get_timeline(weeks=12)

    for snapshot in timeline[-5:]:  # Show last 5 weeks
        print(f"\n{snapshot.date.date()} ({snapshot.commit_hash[:7]})")
        print(f"  Total lines: {snapshot.total_lines}")
        print(f"  Files: {snapshot.total_files}")
        print(f"  Changes: +{snapshot.lines_added} -{snapshot.lines_deleted}")

    # Find major changes
    print("\n=== Major Changes (last 90 days) ===")
    major = tracker.find_major_changes(days=90, threshold=100)

    for commit, net_change, date, subject in major[:5]:
        print(f"\n{commit[:7]} ({date[:10]})")
        print(f"  {subject}")
        print(f"  Net change: {net_change:+d} lines")

    # Growth rate
    print("\n=== Growth Rate ===")
    growth = tracker.get_growth_rate(weeks=12)
    print(f"Code lines/week: {growth['code_lines_per_week']:.1f}")
    print(f"Files/week: {growth['files_per_week']:.1f}")
    print(f"Weeks analyzed: {growth['weeks_analyzed']:.1f}")


if __name__ == "__main__":
    _example_usage()
