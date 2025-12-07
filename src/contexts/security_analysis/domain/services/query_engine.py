"""
Query Engine

Orchestrates security rule execution with performance optimizations.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from pathlib import Path
import logging
import time

from ..models.security_rule import SecurityRule, RuleRegistry, get_registry
from ..models.vulnerability import Vulnerability, ScanResult, Severity

logger = logging.getLogger(__name__)


@dataclass
class QueryConfig:
    """
    Configuration for query execution

    Controls which rules run and how.
    """

    enabled_rules: Optional[List[str]] = None
    """Specific rules to run (None = all)"""

    disabled_rules: List[str] = field(default_factory=list)
    """Rules to skip"""

    min_severity: Severity = Severity.INFO
    """Minimum severity to report"""

    max_vulnerabilities: int = 1000
    """Max vulnerabilities to report (防爆)"""

    timeout_ms: int = 300000  # 5 minutes
    """Timeout per file in milliseconds"""

    parallel: bool = False
    """Run rules in parallel (Future)"""

    use_cache: bool = True
    """Use function summary cache"""


class QueryEngine:
    """
    Security query execution engine

    Features:
    - Rule orchestration
    - Performance optimization (caching)
    - Progress tracking
    - Error handling

    Usage:
        engine = QueryEngine(config)

        # Scan single file
        result = engine.scan_file(ir_doc)

        # Scan repository
        result = engine.scan_repository(repo_path)
    """

    def __init__(
        self,
        config: Optional[QueryConfig] = None,
        registry: Optional[RuleRegistry] = None,
    ):
        """
        Initialize query engine

        Args:
            config: Query configuration
            registry: Rule registry (uses global if None)
        """
        self.config = config or QueryConfig()
        self.registry = registry or get_registry()

        # Statistics
        self.stats = {
            "files_scanned": 0,
            "rules_executed": 0,
            "vulnerabilities_found": 0,
            "errors": 0,
        }

        logger.info(f"QueryEngine initialized with {len(self._get_active_rules())} rules")

    def scan_file(self, ir_document) -> ScanResult:
        """
        Scan single IR document

        Args:
            ir_document: IR document to analyze

        Returns:
            Scan results
        """
        start_time = time.time()
        vulnerabilities = []

        # Get active rules
        rules = self._get_active_rules()

        logger.info(f"Scanning {ir_document.file_path} with {len(rules)} rules")

        # Run each rule
        for rule in rules:
            try:
                rule_vulns = self._run_rule(rule, ir_document)
                vulnerabilities.extend(rule_vulns)

                self.stats["rules_executed"] += 1

                # Check limit
                if len(vulnerabilities) >= self.config.max_vulnerabilities:
                    logger.warning(f"Hit vulnerability limit ({self.config.max_vulnerabilities})")
                    break

            except Exception as e:
                logger.error(f"Rule {rule.get_name()} failed: {e}", exc_info=True)
                self.stats["errors"] += 1

        # Filter by severity
        vulnerabilities = self._filter_by_severity(vulnerabilities)

        # Sort by severity
        vulnerabilities.sort(key=lambda v: v.severity, reverse=True)

        # Create result
        scan_duration = int((time.time() - start_time) * 1000)

        result = ScanResult(
            vulnerabilities=vulnerabilities,
            files_scanned=1,
            scan_duration_ms=scan_duration,
            metadata={
                "rules_run": len(rules),
                "config": {
                    "min_severity": self.config.min_severity.value,
                    "use_cache": self.config.use_cache,
                },
            },
        )

        self.stats["files_scanned"] += 1
        self.stats["vulnerabilities_found"] += len(vulnerabilities)

        logger.info(f"Scan complete: {len(vulnerabilities)} vulnerabilities in {scan_duration}ms")

        return result

    def scan_repository(self, repo_path: Path) -> ScanResult:
        """
        Scan entire repository

        Args:
            repo_path: Path to repository root

        Returns:
            Combined scan results

        TODO: Implement repository scanning
        - Find all Python files
        - Index each file
        - Combine results
        """
        # Placeholder for Phase 1
        # Full implementation in Phase 2

        logger.warning("scan_repository not fully implemented yet")
        return ScanResult()

    def _get_active_rules(self) -> List[SecurityRule]:
        """
        Get active rules based on config

        Returns:
            List of active SecurityRule instances
        """
        all_rules = self.registry.get_all_rules()

        # Filter by enabled_rules
        if self.config.enabled_rules:
            all_rules = [r for r in all_rules if r.get_name() in self.config.enabled_rules]

        # Filter by disabled_rules
        all_rules = [r for r in all_rules if r.get_name() not in self.config.disabled_rules]

        return all_rules

    def _run_rule(
        self,
        rule: SecurityRule,
        ir_document,
    ) -> List[Vulnerability]:
        """
        Run single rule on IR document

        Args:
            rule: Security rule
            ir_document: IR document

        Returns:
            Vulnerabilities found by this rule
        """
        logger.debug(f"Running rule: {rule.get_name()}")

        start_time = time.time()

        try:
            vulnerabilities = rule.analyze(ir_document)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.debug(f"Rule {rule.get_name()} found {len(vulnerabilities)} vulnerabilities in {duration_ms}ms")

            return vulnerabilities

        except Exception as e:
            logger.error(f"Rule {rule.get_name()} crashed: {e}", exc_info=True)
            raise

    def _filter_by_severity(
        self,
        vulnerabilities: List[Vulnerability],
    ) -> List[Vulnerability]:
        """
        Filter vulnerabilities by minimum severity

        Args:
            vulnerabilities: All vulnerabilities

        Returns:
            Filtered vulnerabilities
        """
        return [
            v
            for v in vulnerabilities
            if v.severity.value >= self.config.min_severity.value or v.severity == self.config.min_severity
        ]

    def get_stats(self) -> dict:
        """Get engine statistics"""
        return self.stats.copy()

    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            "files_scanned": 0,
            "rules_executed": 0,
            "vulnerabilities_found": 0,
            "errors": 0,
        }


# Convenience function


def create_query_engine(
    enabled_rules: Optional[List[str]] = None,
    min_severity: Severity = Severity.INFO,
) -> QueryEngine:
    """
    Create query engine with common config

    Args:
        enabled_rules: Specific rules to enable
        min_severity: Minimum severity to report

    Returns:
        QueryEngine instance

    Example:
        # All rules, report HIGH+ only
        engine = create_query_engine(min_severity=Severity.HIGH)

        # Only SQL injection
        engine = create_query_engine(
            enabled_rules=["SQLInjectionQuery"],
            min_severity=Severity.MEDIUM
        )
    """
    config = QueryConfig(
        enabled_rules=enabled_rules,
        min_severity=min_severity,
    )

    return QueryEngine(config)
