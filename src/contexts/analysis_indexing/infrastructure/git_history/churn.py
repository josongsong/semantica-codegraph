"""
Code Churn Analysis

Tracks change frequency and volatility of code.
Churn = measure of how often code changes (higher churn = higher risk).
"""

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class ChurnMetrics:
    """Churn metrics for a file or set of files."""

    # Basic metrics
    total_commits: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    total_changes: int = 0  # additions + deletions

    # Time-based metrics
    first_commit_date: datetime | None = None
    last_commit_date: datetime | None = None
    days_active: int = 0

    # Derived metrics
    churn_rate: float = 0.0  # changes per day
    commit_frequency: float = 0.0  # commits per week

    # Commit details
    commit_dates: list[datetime] = field(default_factory=list)
    commit_hashes: list[str] = field(default_factory=list)

    def calculate_derived_metrics(self) -> None:
        """Calculate derived metrics from raw data."""
        if not self.commit_dates:
            return

        # Calculate days active
        if self.first_commit_date and self.last_commit_date:
            delta = self.last_commit_date - self.first_commit_date
            self.days_active = max(1, delta.days)

            # Churn rate (changes per day)
            self.churn_rate = self.total_changes / self.days_active

            # Commit frequency (commits per week)
            weeks = self.days_active / 7.0
            self.commit_frequency = self.total_commits / max(1.0, weeks)


class ChurnAnalyzer:
    """
    Analyzes code churn to identify volatile/risky files.

    High churn indicates:
    - Frequently changing code (potential instability)
    - Active development areas
    - Hot spots for bugs

    Example:
        ```python
        analyzer = ChurnAnalyzer("/path/to/repo")

        # Get churn for single file
        metrics = analyzer.analyze_file("src/api.py", days=30)
        print(f"Churn rate: {metrics.churn_rate:.2f} changes/day")

        # Get hotspots (high churn files)
        hotspots = analyzer.find_hotspots(days=30, top_n=10)
        for file_path, metrics in hotspots:
            print(f"{file_path}: {metrics.total_changes} changes")
        ```
    """

    def __init__(self, repo_path: str | Path):
        """
        Initialize churn analyzer.

        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path)
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {repo_path}")

    def analyze_file(
        self,
        file_path: str,
        days: int | None = None,
        since: datetime | None = None,
    ) -> ChurnMetrics:
        """
        Analyze churn for a single file.

        Args:
            file_path: Relative path to file from repo root
            days: Number of days to look back (optional)
            since: Start date for analysis (optional)

        Returns:
            ChurnMetrics for the file
        """
        # Build git log command
        cmd = [
            "git",
            "log",
            "--numstat",
            "--pretty=format:%H|%ai",  # hash|date
            "--",
            file_path,
        ]

        # Add time filter if specified
        if days:
            cmd.insert(2, f"--since={days} days ago")
        elif since:
            cmd.insert(2, f"--since={since.isoformat()}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            return ChurnMetrics()

        return self._parse_numstat_output(result.stdout)

    def analyze_directory(self, dir_path: str = ".", days: int | None = None) -> dict[str, ChurnMetrics]:
        """
        Analyze churn for all files in directory.

        Args:
            dir_path: Directory to analyze (relative to repo root)
            days: Number of days to look back

        Returns:
            Dictionary mapping file paths to ChurnMetrics
        """
        # Get all files in directory
        cmd = [
            "git",
            "log",
            "--numstat",
            "--pretty=format:%H|%ai",
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
            return {}

        # Group changes by file
        file_changes = {}
        current_commit = None
        current_date = None

        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Check if this is a commit header
            if "|" in line and len(line.split("|")) == 2:
                commit_hash, date_str = line.split("|")
                current_commit = commit_hash
                current_date = datetime.fromisoformat(date_str.replace(" ", "T"))
                continue

            # Parse numstat line: <additions> <deletions> <file>
            parts = line.split("\t")
            if len(parts) != 3:
                continue

            additions, deletions, file_path = parts

            # Skip binary files (shown as "-")
            if additions == "-" or deletions == "-":
                continue

            try:
                adds = int(additions)
                dels = int(deletions)
            except ValueError:
                continue

            # Initialize file metrics if needed
            if file_path not in file_changes:
                file_changes[file_path] = {
                    "additions": [],
                    "deletions": [],
                    "commits": [],
                    "dates": [],
                }

            file_changes[file_path]["additions"].append(adds)
            file_changes[file_path]["deletions"].append(dels)
            file_changes[file_path]["commits"].append(current_commit)
            if current_date:
                file_changes[file_path]["dates"].append(current_date)

        # Convert to ChurnMetrics
        result = {}
        for file_path, changes in file_changes.items():
            metrics = ChurnMetrics(
                total_commits=len(changes["commits"]),
                total_additions=sum(changes["additions"]),
                total_deletions=sum(changes["deletions"]),
                total_changes=sum(changes["additions"]) + sum(changes["deletions"]),
                commit_dates=changes["dates"],
                commit_hashes=changes["commits"],
            )

            if metrics.commit_dates:
                metrics.first_commit_date = min(metrics.commit_dates)
                metrics.last_commit_date = max(metrics.commit_dates)
                metrics.calculate_derived_metrics()

            result[file_path] = metrics

        return result

    def find_hotspots(
        self,
        days: int = 90,
        top_n: int = 20,
        min_changes: int = 5,
    ) -> list[tuple[str, ChurnMetrics]]:
        """
        Find code hotspots (high-churn files).

        Args:
            days: Number of days to analyze
            top_n: Number of hotspots to return
            min_changes: Minimum number of changes to qualify

        Returns:
            List of (file_path, ChurnMetrics) sorted by churn rate
        """
        all_metrics = self.analyze_directory(".", days=days)

        # Filter and sort
        hotspots = [(path, metrics) for path, metrics in all_metrics.items() if metrics.total_changes >= min_changes]

        # Sort by churn rate (changes per day)
        hotspots.sort(key=lambda x: x[1].churn_rate, reverse=True)

        return hotspots[:top_n]

    def compare_periods(self, file_path: str, period1_days: int, period2_days: int) -> dict[str, float]:
        """
        Compare churn between two time periods.

        Args:
            file_path: File to analyze
            period1_days: Days for first period (e.g., last 30 days)
            period2_days: Days for second period (e.g., 30-60 days ago)

        Returns:
            Dictionary with comparison metrics
        """
        # Analyze recent period
        recent = self.analyze_file(file_path, days=period1_days)

        # Analyze previous period
        since_date = datetime.now() - timedelta(days=period1_days + period2_days)

        previous = self.analyze_file(file_path, since=since_date)

        # Calculate changes
        return {
            "recent_churn_rate": recent.churn_rate,
            "previous_churn_rate": previous.churn_rate,
            "churn_change_percent": (
                ((recent.churn_rate - previous.churn_rate) / previous.churn_rate * 100)
                if previous.churn_rate > 0
                else 0.0
            ),
            "recent_commits": recent.total_commits,
            "previous_commits": previous.total_commits,
        }

    def _parse_numstat_output(self, output: str) -> ChurnMetrics:
        """Parse git log --numstat output."""
        metrics = ChurnMetrics()
        current_commit = None
        current_date = None

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Check if this is a commit header: hash|date
            if "|" in line:
                parts = line.split("|")
                if len(parts) == 2:
                    current_commit = parts[0]
                    current_date = datetime.fromisoformat(parts[1].replace(" ", "T"))
                    metrics.commit_hashes.append(current_commit)
                    if current_date:
                        metrics.commit_dates.append(current_date)
                    continue

            # Parse numstat line: <additions> <deletions> <file>
            parts = line.split("\t")
            if len(parts) != 3:
                continue

            additions, deletions, _ = parts

            if additions == "-" or deletions == "-":
                continue

            try:
                metrics.total_additions += int(additions)
                metrics.total_deletions += int(deletions)
            except ValueError:
                continue

        metrics.total_commits = len(set(metrics.commit_hashes))
        metrics.total_changes = metrics.total_additions + metrics.total_deletions

        if metrics.commit_dates:
            metrics.first_commit_date = min(metrics.commit_dates)
            metrics.last_commit_date = max(metrics.commit_dates)
            metrics.calculate_derived_metrics()

        return metrics


def _example_usage():
    """Example demonstrating churn analysis."""
    analyzer = ChurnAnalyzer(".")

    # Analyze single file
    print("=== Churn for src/memory/working.py (last 90 days) ===")
    metrics = analyzer.analyze_file("src/memory/working.py", days=90)
    print(f"Total commits: {metrics.total_commits}")
    print(f"Total changes: {metrics.total_changes}")
    print(f"Churn rate: {metrics.churn_rate:.2f} changes/day")
    print(f"Commit frequency: {metrics.commit_frequency:.2f} commits/week")

    # Find hotspots
    print("\n=== Top 10 Hotspots (last 30 days) ===")
    hotspots = analyzer.find_hotspots(days=30, top_n=10)
    for i, (file_path, metrics) in enumerate(hotspots, 1):
        print(f"{i}. {file_path}")
        print(f"   Changes: {metrics.total_changes}, Rate: {metrics.churn_rate:.2f}/day")

    # Compare periods
    print("\n=== Churn comparison: last 30 vs previous 30 days ===")
    comparison = analyzer.compare_periods("src/memory/working.py", 30, 30)
    print(f"Recent churn rate: {comparison['recent_churn_rate']:.2f}")
    print(f"Previous churn rate: {comparison['previous_churn_rate']:.2f}")
    print(f"Change: {comparison['churn_change_percent']:.1f}%")


if __name__ == "__main__":
    _example_usage()
