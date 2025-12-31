"""
SecurityRule base class

Abstract base for all security query rules.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .vulnerability import CWE, Severity, Vulnerability

logger = logging.getLogger(__name__)


@dataclass
class TaintSource:
    """
    Taint source pattern

    Identifies where untrusted data enters the system.
    """

    patterns: list[str]
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

    patterns: list[str]
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

    patterns: list[str]
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

    # Class attributes (must be overridden by subclasses)
    CWE_ID: CWE
    """CWE classification for this rule"""

    SEVERITY: Severity
    """Default severity for vulnerabilities"""

    # NOTE: These are declared as ClassVar to indicate they're class-level,
    # but subclasses should override them with their own lists.
    # We use tuple instead of list for immutability at class level.
    SOURCES: tuple[TaintSource, ...] = ()
    """Taint sources for this rule (override in subclass)"""

    SINKS: tuple[TaintSink, ...] = ()
    """Taint sinks for this rule (override in subclass)"""

    SANITIZERS: tuple[TaintSanitizer, ...] = ()
    """Sanitizers for this rule (override in subclass)"""

    def __init__(self):
        """Initialize rule"""
        # Validate class attributes
        if not hasattr(self, "CWE_ID"):
            raise ValueError(f"{self.__class__.__name__} must define CWE_ID")

        if not hasattr(self, "SEVERITY"):
            raise ValueError(f"{self.__class__.__name__} must define SEVERITY")

        logger.info(f"Initialized {self.__class__.__name__} (CWE-{self.CWE_ID.value}, {self.SEVERITY.value})")

    @abstractmethod
    def analyze(self, ir_document) -> list[Vulnerability]:
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

    def _find_sources(self, ir_document) -> list:
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

    def _find_sinks(self, ir_document) -> list:
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

    def _find_sanitizers(self, ir_document) -> list:
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

    def _find_pattern(self, ir_document, pattern: str) -> list:
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
        matches: list[object] = []

        # For now, simple text search in IR
        # This is a simplified implementation

        return matches

    def _create_vulnerability(
        self,
        source,
        sink,
        taint_path: list,
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
        from .vulnerability import Evidence, Location

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

    def _get_references(self) -> list[str]:
        """Get reference URLs"""
        return [f"https://cwe.mitre.org/data/definitions/{self.CWE_ID.value.split('-')[1]}.html"]

    # Confidence calculation configuration
    class ConfidenceSettings:
        """Confidence calculation settings (override in subclass if needed)"""

        BASE_CONFIDENCE: float = 0.8
        SHORT_PATH_BONUS: float = 0.1
        LONG_PATH_PENALTY: float = 0.1
        SHORT_PATH_THRESHOLD: int = 3
        LONG_PATH_THRESHOLD: int = 10

    def _calculate_confidence(self, source, sink, taint_path: list) -> float:
        """
        Calculate confidence score

        Factors:
        - Source confidence
        - Sink confidence
        - Path length (shorter = higher confidence)
        - Sanitizers in path
        """
        cfg = self.ConfidenceSettings
        confidence = cfg.BASE_CONFIDENCE

        # Adjust based on path length
        path_len = len(taint_path)
        if path_len <= cfg.SHORT_PATH_THRESHOLD:
            confidence += cfg.SHORT_PATH_BONUS
        elif path_len > cfg.LONG_PATH_THRESHOLD:
            confidence -= cfg.LONG_PATH_PENALTY

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, confidence))


class RuleRegistry:
    """
    Registry of all security rules

    Manages rule discovery and instantiation.

    Supports both singleton (default) and instance-based patterns.
    Use get_registry() for singleton, or create RuleRegistry() for isolated testing.
    """

    # Class-level cache for rule instances (singleton pattern within registry)
    _instance_cache: dict[str, SecurityRule]

    def __init__(self, *, use_cache: bool = True) -> None:
        """
        Initialize registry

        Args:
            use_cache: If True, cache rule instances (singleton per registry)
        """
        self._rules: dict[str, type[SecurityRule]] = {}
        self._use_cache = use_cache
        self._instance_cache = {}

    def register(self, rule_class: type[SecurityRule]) -> None:
        """
        Register a security rule

        Args:
            rule_class: SecurityRule subclass
        """
        name = rule_class.__name__
        self._rules[name] = rule_class
        # Clear cache for this rule if it was cached
        self._instance_cache.pop(name, None)
        logger.info(f"Registered security rule: {name}")

    def unregister(self, name: str) -> bool:
        """
        Unregister a security rule

        Args:
            name: Rule class name

        Returns:
            True if removed, False if not found
        """
        if name in self._rules:
            del self._rules[name]
            self._instance_cache.pop(name, None)
            logger.info(f"Unregistered security rule: {name}")
            return True
        return False

    def get_rule(self, name: str) -> SecurityRule | None:
        """
        Get rule instance by name

        Args:
            name: Rule class name

        Returns:
            Rule instance or None (cached if use_cache=True)
        """
        # Check cache first
        if self._use_cache and name in self._instance_cache:
            return self._instance_cache[name]

        rule_class = self._rules.get(name)
        if rule_class:
            instance = rule_class()
            if self._use_cache:
                self._instance_cache[name] = instance
            return instance
        return None

    def get_all_rules(self) -> list[SecurityRule]:
        """Get all registered rules (cached instances if use_cache=True)"""
        rules: list[SecurityRule] = []
        for name in self._rules:
            rule = self.get_rule(name)
            if rule is not None:
                rules.append(rule)
        return rules

    def get_rules_by_cwe(self, cwe: CWE) -> list[SecurityRule]:
        """Get rules for specific CWE"""
        return [rule for rule in self.get_all_rules() if rule.CWE_ID == cwe]

    def get_registered_names(self) -> list[str]:
        """Get list of registered rule names"""
        return list(self._rules.keys())

    def clear(self) -> None:
        """Clear all registered rules and cache (useful for testing)"""
        self._rules.clear()
        self._instance_cache.clear()
        logger.debug("Cleared rule registry")

    def __len__(self) -> int:
        """Return number of registered rules"""
        return len(self._rules)

    def __contains__(self, name: str) -> bool:
        """Check if rule is registered"""
        return name in self._rules


# =============================================================================
# Global Registry (Singleton Pattern with DI Support)
# =============================================================================

# Global registry instance (created lazily)
_registry: RuleRegistry | None = None


def get_registry() -> RuleRegistry:
    """
    Get global rule registry (singleton)

    For testing, create a new RuleRegistry() instance directly.

    Returns:
        Global RuleRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = RuleRegistry()
    return _registry


def set_registry(registry: RuleRegistry) -> None:
    """
    Set global rule registry (for testing/DI)

    Args:
        registry: RuleRegistry instance to use globally
    """
    global _registry
    _registry = registry
    logger.info("Global registry replaced")


def reset_registry() -> None:
    """Reset global registry to default (for testing)"""
    global _registry
    _registry = None
    logger.debug("Global registry reset")


def register_rule(rule_class: type[SecurityRule]):
    """
    Decorator to register a security rule

    Usage:
        @register_rule
        class MySQLInjectionRule(SecurityRule):
            CWE_ID = CWE.CWE_89
            ...
    """
    get_registry().register(rule_class)
    return rule_class
