"""
SecurityRule base class

Abstract base for all security query rules.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Set, Optional
import logging

from .vulnerability import Vulnerability, CWE, Severity

logger = logging.getLogger(__name__)


@dataclass
class TaintSource:
    """
    Taint source pattern

    Identifies where untrusted data enters the system.
    """

    patterns: List[str]
    """Function/method patterns (e.g., "request.args.get", "os.environ.get")"""

    description: str
    """Human-readable description"""

    confidence: float = 1.0
    """Confidence that this is a real source (0.0-1.0)"""


@dataclass
class TaintSink:
    """
    Taint sink pattern

    Identifies dangerous operations that shouldn't receive tainted data.
    """

    patterns: List[str]
    """Function/method patterns (e.g., "cursor.execute", "os.system")"""

    description: str
    """Human-readable description"""

    severity: Severity = Severity.HIGH
    """Severity if taint reaches this sink"""


@dataclass
class TaintSanitizer:
    """
    Taint sanitizer pattern

    Identifies functions that clean/validate untrusted data.
    """

    patterns: List[str]
    """Function/method patterns (e.g., "html.escape", "int()")"""

    description: str
    """Human-readable description"""

    effectiveness: float = 1.0
    """How effective (0.0-1.0). 1.0 = complete sanitization"""


class SecurityRule(ABC):
    """
    Abstract base class for security rules

    All security queries inherit from this.

    Example:
        class SQLInjectionRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            SEVERITY = Severity.CRITICAL

            SOURCES = [
                TaintSource(
                    patterns=["request.args.get", "request.form"],
                    description="HTTP request parameters"
                )
            ]

            SINKS = [
                TaintSink(
                    patterns=["cursor.execute", "db.execute"],
                    description="Direct SQL execution"
                )
            ]

            def analyze(self, ir_document):
                # Implementation
                pass
    """

    # Class attributes (must be overridden)
    CWE_ID: CWE
    """CWE classification for this rule"""

    SEVERITY: Severity
    """Default severity for vulnerabilities"""

    SOURCES: List[TaintSource] = []
    """Taint sources for this rule"""

    SINKS: List[TaintSink] = []
    """Taint sinks for this rule"""

    SANITIZERS: List[TaintSanitizer] = []
    """Sanitizers for this rule"""

    def __init__(self):
        """Initialize rule"""
        # Validate class attributes
        if not hasattr(self, "CWE_ID"):
            raise ValueError(f"{self.__class__.__name__} must define CWE_ID")

        if not hasattr(self, "SEVERITY"):
            raise ValueError(f"{self.__class__.__name__} must define SEVERITY")

        logger.info(f"Initialized {self.__class__.__name__} (CWE-{self.CWE_ID.value}, {self.SEVERITY.value})")

    @abstractmethod
    def analyze(self, ir_document) -> List[Vulnerability]:
        """
        Analyze IR document for vulnerabilities

        Args:
            ir_document: IR document to analyze

        Returns:
            List of vulnerabilities found

        Implementation should:
        1. Find sources using self.SOURCES
        2. Find sinks using self.SINKS
        3. Run taint analysis (source → sink)
        4. Check for sanitizers
        5. Create Vulnerability objects
        """
        raise NotImplementedError

    def get_name(self) -> str:
        """Get human-readable rule name"""
        return self.__class__.__name__

    def get_description(self) -> str:
        """Get rule description"""
        return f"{self.CWE_ID.get_name()} ({self.CWE_ID.value})"

    def _find_sources(self, ir_document) -> List:
        """
        Find all taint sources in IR document

        Args:
            ir_document: IR document

        Returns:
            List of source nodes
        """
        sources = []

        for source_group in self.SOURCES:
            for pattern in source_group.patterns:
                matches = self._find_pattern(ir_document, pattern)
                sources.extend(matches)

        logger.debug(f"Found {len(sources)} sources for {self.get_name()}")
        return sources

    def _find_sinks(self, ir_document) -> List:
        """
        Find all taint sinks in IR document

        Args:
            ir_document: IR document

        Returns:
            List of sink nodes
        """
        sinks = []

        for sink_group in self.SINKS:
            for pattern in sink_group.patterns:
                matches = self._find_pattern(ir_document, pattern)
                sinks.extend(matches)

        logger.debug(f"Found {len(sinks)} sinks for {self.get_name()}")
        return sinks

    def _find_sanitizers(self, ir_document) -> List:
        """
        Find all sanitizers in IR document

        Args:
            ir_document: IR document

        Returns:
            List of sanitizer nodes
        """
        sanitizers = []

        for sanitizer_group in self.SANITIZERS:
            for pattern in sanitizer_group.patterns:
                matches = self._find_pattern(ir_document, pattern)
                sanitizers.extend(matches)

        logger.debug(f"Found {len(sanitizers)} sanitizers for {self.get_name()}")
        return sanitizers

    def _find_pattern(self, ir_document, pattern: str) -> List:
        """
        Find pattern in IR document

        Args:
            ir_document: IR document
            pattern: Pattern to find (e.g., "request.args.get")

        Returns:
            List of matching nodes

        TODO: Integrate with tree-sitter Query API (Phase 2)
        """
        # Placeholder implementation
        # In Phase 2, this will use tree-sitter Query API
        matches = []

        # For now, simple text search in IR
        # This is a simplified implementation

        return matches

    def _create_vulnerability(
        self,
        source,
        sink,
        taint_path: List,
        ir_document,
    ) -> Vulnerability:
        """
        Create vulnerability object

        Args:
            source: Source node
            sink: Sink node
            taint_path: Path from source to sink
            ir_document: IR document

        Returns:
            Vulnerability object
        """
        from .vulnerability import Location, Evidence

        # Extract locations
        source_loc = Location(
            file_path=ir_document.file_path,
            start_line=getattr(source, "start_line", 0),
            end_line=getattr(source, "end_line", 0),
        )

        sink_loc = Location(
            file_path=ir_document.file_path,
            start_line=getattr(sink, "start_line", 0),
            end_line=getattr(sink, "end_line", 0),
        )

        # Build evidence trail
        evidence = []
        for i, node in enumerate(taint_path):
            node_type = "source" if i == 0 else ("sink" if i == len(taint_path) - 1 else "propagation")

            evidence.append(
                Evidence(
                    location=Location(
                        file_path=ir_document.file_path,
                        start_line=getattr(node, "start_line", 0),
                        end_line=getattr(node, "end_line", 0),
                    ),
                    code_snippet=getattr(node, "code", ""),
                    description=f"{node_type.capitalize()} point",
                    node_type=node_type,
                )
            )

        # Create vulnerability
        return Vulnerability(
            cwe=self.CWE_ID,
            severity=self.SEVERITY,
            title=f"{self.CWE_ID.get_name()} in {ir_document.file_path}",
            description=self._generate_description(source, sink),
            source_location=source_loc,
            sink_location=sink_loc,
            taint_path=evidence,
            recommendation=self._get_recommendation(),
            references=self._get_references(),
            confidence=self._calculate_confidence(source, sink, taint_path),
        )

    def _generate_description(self, source, sink) -> str:
        """Generate vulnerability description"""
        return (
            f"Untrusted data from {getattr(source, 'description', 'source')} "
            f"flows to {getattr(sink, 'description', 'sink')} without sanitization."
        )

    def _get_recommendation(self) -> str:
        """Get fix recommendation"""
        return "Sanitize or validate untrusted input before use."

    def _get_references(self) -> List[str]:
        """Get reference URLs"""
        return [f"https://cwe.mitre.org/data/definitions/{self.CWE_ID.value.split('-')[1]}.html"]

    def _calculate_confidence(self, source, sink, taint_path: List) -> float:
        """
        Calculate confidence score

        Factors:
        - Source confidence
        - Sink confidence
        - Path length (shorter = higher confidence)
        - Sanitizers in path
        """
        # Base confidence
        confidence = 0.8

        # Adjust based on path length
        path_len = len(taint_path)
        if path_len <= 3:
            confidence += 0.1
        elif path_len > 10:
            confidence -= 0.1

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, confidence))


class RuleRegistry:
    """
    Registry of all security rules

    Manages rule discovery and instantiation.
    """

    def __init__(self):
        self._rules: dict[str, type[SecurityRule]] = {}

    def register(self, rule_class: type[SecurityRule]):
        """
        Register a security rule

        Args:
            rule_class: SecurityRule subclass
        """
        name = rule_class.__name__
        self._rules[name] = rule_class
        logger.info(f"Registered security rule: {name}")

    def get_rule(self, name: str) -> Optional[SecurityRule]:
        """
        Get rule instance by name

        Args:
            name: Rule class name

        Returns:
            Rule instance or None
        """
        rule_class = self._rules.get(name)
        if rule_class:
            return rule_class()
        return None

    def get_all_rules(self) -> List[SecurityRule]:
        """Get all registered rules"""
        return [rule_class() for rule_class in self._rules.values()]

    def get_rules_by_cwe(self, cwe: CWE) -> List[SecurityRule]:
        """Get rules for specific CWE"""
        return [rule for rule in self.get_all_rules() if rule.CWE_ID == cwe]


# Global registry
_registry = RuleRegistry()


def register_rule(rule_class: type[SecurityRule]):
    """
    Decorator to register a security rule

    Usage:
        @register_rule
        class MySQLInjectionRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            ...
    """
    _registry.register(rule_class)
    return rule_class


def get_registry() -> RuleRegistry:
    """Get global rule registry"""
    return _registry
