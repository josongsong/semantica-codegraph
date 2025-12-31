"""Telemetry - RFC-036.

Self-improving rule engine through telemetry collection and analysis.

Exports:
    - TelemetryCollector: Collect match events
    - RuleMatchTelemetry: Individual match event
    - SessionTelemetry: Session-level aggregation
    - RuleStatistics: Per-rule statistics
    - FrequencyAnalyzer: Identify common patterns
    - FPTPEstimator: Estimate false positive rates
    - RuleHealthChecker: Identify unhealthy rules
"""

from trcr.telemetry.analyzer import (
    FPTPEstimator,
    FrequencyAnalyzer,
    RuleHealthChecker,
    RuleHealthReport,
    TelemetryAnalysisReport,
    analyze_telemetry,
)
from trcr.telemetry.collector import (
    CollectorConfig,
    TelemetryCollector,
    get_default_collector,
)
from trcr.telemetry.schema import (
    PatternStats,
    RuleMatchTelemetry,
    RuleStatistics,
    SessionTelemetry,
)

__all__ = [
    # Schema
    "RuleMatchTelemetry",
    "SessionTelemetry",
    "RuleStatistics",
    "PatternStats",
    # Collector
    "TelemetryCollector",
    "CollectorConfig",
    "get_default_collector",
    # Analyzer
    "FrequencyAnalyzer",
    "FPTPEstimator",
    "RuleHealthChecker",
    "RuleHealthReport",
    "TelemetryAnalysisReport",
    "analyze_telemetry",
]
