"""
Taint Rules Metrics & Logging

Rule hit 추적 및 분석
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class RuleHit:
    """개별 Rule Hit 기록"""

    rule_id: str
    file_path: str
    line: int
    project: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    # Additional context
    code_snippet: str | None = None
    is_false_positive: bool = False
    reviewer_note: str | None = None


@dataclass
class RuleMetrics:
    """Rule별 집계 메트릭"""

    rule_id: str
    total_hits: int = 0
    files_affected: set[str] = field(default_factory=set)
    projects_affected: set[str] = field(default_factory=set)
    false_positive_count: int = 0

    # Distribution
    severity_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rule_id": self.rule_id,
            "total_hits": self.total_hits,
            "files_affected": len(self.files_affected),
            "projects_affected": len(self.projects_affected),
            "false_positive_count": self.false_positive_count,
            "false_positive_rate": (self.false_positive_count / self.total_hits if self.total_hits > 0 else 0.0),
        }


class MetricsCollector:
    """
    Taint Rules 메트릭 수집기

    Usage:
        collector = MetricsCollector()

        # Record hit
        collector.record_hit(
            rule_id="PY_CORE_SINK_001",
            file_path="app.py",
            line=42,
            project="myapp",
        )

        # Get metrics
        metrics = collector.get_metrics("PY_CORE_SINK_001")

        # Export
        collector.export_json("metrics.json")
    """

    def __init__(self):
        self.hits: list[RuleHit] = []
        self.metrics: dict[str, RuleMetrics] = {}

    def record_hit(
        self,
        rule_id: str,
        file_path: str,
        line: int,
        project: str,
        code_snippet: str | None = None,
    ):
        """Record a rule hit"""
        hit = RuleHit(
            rule_id=rule_id,
            file_path=file_path,
            line=line,
            project=project,
            code_snippet=code_snippet,
        )
        self.hits.append(hit)

        # Update metrics
        if rule_id not in self.metrics:
            self.metrics[rule_id] = RuleMetrics(rule_id=rule_id)

        metrics = self.metrics[rule_id]
        metrics.total_hits += 1
        metrics.files_affected.add(file_path)
        metrics.projects_affected.add(project)

    def mark_false_positive(
        self,
        rule_id: str,
        file_path: str,
        line: int,
        reviewer_note: str | None = None,
    ):
        """Mark a hit as false positive"""
        for hit in self.hits:
            if hit.rule_id == rule_id and hit.file_path == file_path and hit.line == line:
                hit.is_false_positive = True
                hit.reviewer_note = reviewer_note

                # Update metrics
                if rule_id in self.metrics:
                    self.metrics[rule_id].false_positive_count += 1
                break

    def get_metrics(self, rule_id: str) -> RuleMetrics | None:
        """Get metrics for a specific rule"""
        return self.metrics.get(rule_id)

    def get_all_metrics(self) -> dict[str, RuleMetrics]:
        """Get all metrics"""
        return self.metrics

    def get_noisy_rules(self, threshold: float = 0.3) -> list[str]:
        """
        Get rules with high false positive rate

        Args:
            threshold: False positive rate threshold (0.0-1.0)

        Returns:
            List of rule IDs
        """
        noisy = []
        for rule_id, metrics in self.metrics.items():
            if metrics.total_hits == 0:
                continue

            fp_rate = metrics.false_positive_count / metrics.total_hits
            if fp_rate >= threshold:
                noisy.append(rule_id)

        return noisy

    def export_json(self, path: Path):
        """Export metrics to JSON"""
        data = {
            "total_hits": len(self.hits),
            "unique_rules": len(self.metrics),
            "metrics": {rule_id: metrics.to_dict() for rule_id, metrics in self.metrics.items()},
            "noisy_rules": self.get_noisy_rules(),
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def get_coverage_heatmap(self) -> dict[str, dict[str, int]]:
        """
        Get coverage heatmap (project × rule)

        Returns:
            {
                "project1": {"PY_CORE_SINK_001": 5, "PY_CORE_SINK_002": 3},
                "project2": {"PY_CORE_SINK_001": 2},
            }
        """
        heatmap = {}

        for hit in self.hits:
            if hit.project not in heatmap:
                heatmap[hit.project] = {}

            if hit.rule_id not in heatmap[hit.project]:
                heatmap[hit.project][hit.rule_id] = 0

            heatmap[hit.project][hit.rule_id] += 1

        return heatmap


# Global singleton
_global_collector = MetricsCollector()


def get_global_collector() -> MetricsCollector:
    """Get global metrics collector"""
    return _global_collector
