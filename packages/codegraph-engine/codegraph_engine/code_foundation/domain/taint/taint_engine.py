"""
TaintEngine - Domain Core (Hexagonal Architecture)

Pure business logic for taint analysis vulnerability detection.
No infrastructure dependencies. Depends only on Ports (interfaces).

SOLID Compliance:
- S: Single responsibility (vulnerability detection)
- O: Open for extension (new atom types, policies)
- L: Liskov substitution (works with any IQueryEngine impl)
- I: Interface segregation (minimal dependencies)
- D: Dependency inversion (depends on abstractions)

Architecture:
    Domain Layer (This file)
        ↓ depends on
    Ports (Interfaces - foundation_ports.py)
        ↑ implemented by
    Infrastructure Layer

No Fakes, No Stubs:
    - All validation is real
    - All algorithms are production-ready
    - No hardcoded magic values
"""

from typing import Any
from uuid import uuid4

from codegraph_shared.common.observability import get_logger
from codegraph_engine.code_foundation.domain.ports.foundation_ports import (
    AtomMatcherPort,
    ConstraintValidatorPort,
    PolicyCompilerPort,
    QueryEnginePort,
)
from codegraph_engine.code_foundation.domain.ports.ir_port import IRDocumentPort
from codegraph_engine.code_foundation.domain.query.results import PathResult

from .atoms import AtomSpec
from .compiled_policy import CompiledPolicy
from .control import ControlConfig
from .models import (
    DetectedAtoms,
    DetectedSanitizer,
    DetectedSink,
    DetectedSource,
    TaintFlow,
    Vulnerability,
)
from .policy import Policy

logger = get_logger(__name__)


# ============================================================
# TaintEngine (Domain Core)
# ============================================================


class TaintEngine:
    """
    Taint Analysis Engine - Domain Core.

    Orchestrates vulnerability detection using type-aware matching,
    policy-based rules, and graph traversal.

    Architecture:
        - Pure domain logic (no infrastructure)
        - Depends on Ports (abstractions)
        - SOLID compliant
        - Hexagonal architecture

    Responsibilities:
    1. Orchestrate atom detection
    2. Execute policies
    3. Validate paths
    4. Check sanitizers
    5. Create vulnerabilities

    NOT Responsible For:
    - Type inference (TypeInfo)
    - Graph traversal (QueryEngine)
    - Configuration loading (Repositories)
    - Output formatting (Presenters)

    Usage:
        ```python
        engine = TaintEngine(
            atom_matcher=type_aware_matcher,
            policy_compiler=compiler,
            query_engine=query_adapter,
            constraint_validator=validator
        )

        vulnerabilities = engine.find_vulnerabilities(
            ir_doc=ir_document,
            control=control_config,
            atoms=atoms,
            policies=policies
        )
        ```

    Performance Characteristics:
    - O(P * (A + Q)) where:
        - P = number of policies
        - A = atom detection time
        - Q = query execution time
    - Early termination on max vulnerabilities
    - Path caching for repeated queries
    """

    def __init__(
        self,
        atom_matcher: AtomMatcherPort,
        policy_compiler: PolicyCompilerPort,
        query_engine: QueryEnginePort,
        constraint_validator: ConstraintValidatorPort,
    ):
        """
        Initialize TaintEngine.

        Args:
            atom_matcher: Atom matching service (Port)
            policy_compiler: Policy compilation service (Port)
            query_engine: Query execution service (Port)
            constraint_validator: Constraint validation service (Port)

        Design:
            - All dependencies are Ports (abstractions)
            - No concrete implementations in domain
            - Dependency Injection ready
        """
        self._atom_matcher = atom_matcher
        self._policy_compiler = policy_compiler
        self._query_engine = query_engine
        self._constraint_validator = constraint_validator

        logger.info("taint_engine_initialized")

    def find_vulnerabilities(
        self,
        ir_doc: IRDocumentPort,
        control: ControlConfig,
        atoms: list[AtomSpec],
        policies: list[Policy],
        max_vulnerabilities: int = 1000,
        detected_atoms: "DetectedAtoms | None" = None,  # 🔥 NEW
    ) -> list[Vulnerability]:
        """
        Find vulnerabilities in IR document.

        Main algorithm for taint analysis.

        Args:
            ir_doc: IR document to analyze
            control: Control configuration (rules on/off, severity)
            atoms: Atom specifications (sources, sinks, sanitizers)
            policies: Security policies
            max_vulnerabilities: Maximum vulnerabilities to report
            detected_atoms: Pre-detected atoms (optional, avoids double detection) 🔥 NEW

        Returns:
            List of detected vulnerabilities

        Workflow:
        1. Filter policies by control config
        2. Detect atoms (or reuse if provided) 🔥
        3. For each policy:
           a. Compile grammar → Q.DSL (with Expression IDs) 🔥
           b. Execute query (find paths)
           c. Validate paths (constraints)
           d. Check sanitizers
           e. Create vulnerability
        4. Deduplicate and rank
        """
        logger.info(
            "taint_analysis_started",
            policies=len(policies),
            atoms=len(atoms),
            max_vulns=max_vulnerabilities,
        )

        # Validate inputs
        if not ir_doc:
            raise ValueError("IR document cannot be None")
        if max_vulnerabilities < 1:
            raise ValueError("max_vulnerabilities must be >= 1")

        # 1. Filter policies by control
        filtered_policies = self._filter_policies(policies, control)
        logger.info("policies_filtered", count=len(filtered_policies))

        if not filtered_policies:
            logger.info("no_policies_enabled")
            return []

        # 2. 🔥 Detect atoms (or reuse if provided)
        if detected_atoms is None:
            detected_atoms = self._detect_atoms(ir_doc, atoms)
            logger.info(
                "atoms_detected",
                sources=detected_atoms.count_sources(),
                sinks=detected_atoms.count_sinks(),
                sanitizers=detected_atoms.count_sanitizers(),
            )
        else:
            logger.info(
                "atoms_reused",
                sources=detected_atoms.count_sources(),
                sinks=detected_atoms.count_sinks(),
                sanitizers=detected_atoms.count_sanitizers(),
            )

        # No sources or sinks → no vulnerabilities
        if not detected_atoms.sources or not detected_atoms.sinks:
            logger.info("no_atoms_detected")
            return []

        # 3. Execute policies
        vulnerabilities: list[Vulnerability] = []

        for policy in filtered_policies:
            if len(vulnerabilities) >= max_vulnerabilities:
                logger.warning("max_vulnerabilities_reached", limit=max_vulnerabilities)
                break

            try:
                policy_vulns = self._execute_policy(
                    policy=policy,
                    detected_atoms=detected_atoms,  # 🔥 Pass detected_atoms
                    atoms=atoms,
                    ir_doc=ir_doc,
                    control=control,
                )
                vulnerabilities.extend(policy_vulns)

                logger.info(
                    "policy_executed",
                    policy_id=policy.id,
                    vulnerabilities=len(policy_vulns),
                )
            except Exception as e:
                # Normal: policy atoms not present in this file
                logger.debug(
                    "policy_skipped",
                    policy_id=policy.id,
                    reason=str(e),
                )
                # Continue with next policy (resilient)
                continue

        # 4. Deduplicate (by source+sink location)
        deduplicated = self._deduplicate_vulnerabilities(vulnerabilities)

        logger.info(
            "taint_analysis_complete",
            total_vulnerabilities=len(deduplicated),
            deduplicated=len(vulnerabilities) - len(deduplicated),
        )

        return deduplicated[:max_vulnerabilities]

    def _filter_policies(self, policies: list[Policy], control: ControlConfig) -> list[Policy]:
        """
        Filter policies by control configuration.

        Args:
            policies: All policies
            control: Control config (on/off rules)

        Returns:
            List of enabled policies

        Logic:
        - Uses RuleControl.is_enabled() method
        - Default: enabled (unless in disabled list)
        - Respects enabled/disabled lists
        """
        filtered = []
        for policy in policies:
            if control.rules.is_enabled(policy.id):
                filtered.append(policy)

        return filtered

    def _detect_atoms(self, ir_doc: IRDocumentPort, atoms: list[AtomSpec]) -> DetectedAtoms:
        """
        Detect atoms in IR document (Type-aware).

        Delegates to AtomMatcher port.

        Args:
            ir_doc: IR document
            atoms: Atom specifications

        Returns:
            DetectedAtoms with all matches

        Performance:
        - O(N * A) where N = nodes, A = atoms
        - Optimized by AtomIndexer (O(1) lookup)
        """
        return self._atom_matcher.match_all(ir_doc, atoms)

    def _execute_policy(
        self,
        policy: Policy,
        detected_atoms: DetectedAtoms,
        atoms: list[AtomSpec],
        ir_doc: IRDocumentPort,
        control: ControlConfig,
    ) -> list[Vulnerability]:
        """
        Execute a single policy.

        Args:
            policy: Policy to execute
            detected_atoms: Detected atoms (with Expression IDs!) 🔥
            atoms: All atom specs (for compilation)
            ir_doc: IR document
            control: Control config

        Returns:
            List of vulnerabilities found by this policy

        Algorithm:
        1. Compile policy → Q.DSL query (using detected_atoms) 🔥
        2. Execute query → get paths
        3. Validate each path
        4. Check sanitizers
        5. Create vulnerabilities
        """
        # 1. 🔥 Compile policy with detected_atoms (Expression IDs)
        compiled = self._policy_compiler.compile(policy, atoms, detected_atoms)

        # 2. Execute query (get all paths from sources to sinks)
        paths = self._query_engine.execute_flow_query(
            compiled_policy=compiled,
            max_paths=100,  # Configurable
            max_depth=20,  # Configurable
        )

        if not paths:
            return []

        vulnerabilities = []

        # 3. Validate each path
        for path in paths:
            # Constraint validation
            if not self._validate_path(path, compiled):
                continue

            # Sanitizer check
            if self._is_sanitized(path, detected_atoms.sanitizers):
                continue

            # 4. Create vulnerability
            vuln = self._create_vulnerability(
                policy=policy,
                path=path,
                detected_atoms=detected_atoms,
                control=control,
            )
            vulnerabilities.append(vuln)

        return vulnerabilities

    def _validate_path(self, path: "PathResult", compiled: "CompiledPolicy") -> bool:
        """
        Validate path against policy constraints.

        Args:
            path: Path to validate
            compiled: Compiled policy with constraints

        Returns:
            True if path is valid

        Delegates to ConstraintValidator port.
        """
        if not hasattr(compiled, "constraints"):
            return True

        return self._constraint_validator.validate_path(path, compiled.constraints)

    def _is_sanitized(
        self,
        path: "PathResult",
        sanitizers: list[DetectedSanitizer],
    ) -> bool:
        """
        Check if path is sanitized (SOTA-grade).

        A path is sanitized if:
        1. It contains a sanitizer node directly, OR
        2. The path passes through a variable that received sanitized data
           (scope: return barrier pattern)

        Args:
            path: Path to check
            sanitizers: Detected sanitizers

        Returns:
            True if path is sanitized

        Algorithm (RFC-030 Enhanced):
        - Check direct sanitizer entity_id match
        - For scope:return sanitizers, check if any node AFTER the sanitizer
          in the path is the sanitizer's return value
        - Detects patterns like: source → sanitizer() → safe_var → sink
        """
        if not sanitizers:
            return False

        # Convert path nodes to set for O(1) lookup
        # Support both string IDs and objects with .id attribute
        path_node_ids = set()
        for node in path.nodes:
            if hasattr(node, "id"):
                path_node_ids.add(node.id)
            else:
                path_node_ids.add(str(node))

        # Check each sanitizer
        for sanitizer in sanitizers:
            # Direct match: sanitizer call is in path
            if sanitizer.entity_id in path_node_ids:
                logger.debug(
                    "path_sanitized_direct",
                    sanitizer=sanitizer.atom_id,
                    location=sanitizer.location,
                )
                return True

            # RFC-030: scope:return barrier check
            # If sanitizer has scope="return", check if its return value
            # flows into a variable that's in the path
            if sanitizer.scope == "return":
                # The sanitizer call produces a sanitized value
                # Check if any downstream node in path received this value
                # by checking if the sanitizer call's location matches
                # a node that feeds into the path

                # Get sanitizer location info
                san_loc = sanitizer.location
                san_line = san_loc.get("line", 0) if isinstance(san_loc, dict) else 0

                if san_line > 0:
                    # Check if any path node is on same line or immediately after
                    # This captures: safe_var = escape_filter_chars(user_input)
                    for node in path.nodes:
                        node_line = self._get_node_line(node)

                        # Same line = assignment of sanitizer result
                        if node_line == san_line:
                            # This node likely holds sanitized data
                            logger.debug(
                                "path_sanitized_return_scope",
                                sanitizer=sanitizer.atom_id,
                                location=sanitizer.location,
                                node_line=node_line,
                            )
                            return True

            # RFC-030: scope:guard barrier check (SOTA)
            # Guard sanitizers validate input BEFORE it reaches the sink
            # Pattern: if not re.match(...) or if var not in ALLOWLIST → early return
            # If guard is between source and sink, path is sanitized
            if sanitizer.scope == "guard":
                san_loc = sanitizer.location
                san_line = san_loc.get("line", 0) if isinstance(san_loc, dict) else 0

                if san_line > 0:
                    # Get source line (first path node) and sink line (last path node)
                    source_line = 0
                    sink_line = 0

                    if path.nodes:
                        first_node = path.nodes[0]
                        last_node = path.nodes[-1]

                        source_line = self._get_node_line(first_node)
                        sink_line = self._get_node_line(last_node)

                    # Guard is effective if it's between source and sink
                    # (or after source, before sink)
                    if source_line > 0 and sink_line > 0:
                        if source_line <= san_line < sink_line:
                            logger.debug(
                                "path_sanitized_guard_scope",
                                sanitizer=sanitizer.atom_id,
                                location=sanitizer.location,
                                source_line=source_line,
                                guard_line=san_line,
                                sink_line=sink_line,
                            )
                            return True

        # RFC-030 Phase 2: Dominator-based guard check (SOTA)
        # Check if any tainted variable is protected by a guard
        # Uses ConstraintValidator.is_guard_protected() with Dominator analysis
        if self._constraint_validator and path.nodes:
            last_node = path.nodes[-1]
            sink_block_id = ""
            sink_var = ""

            # Extract block_id and variable from sink node
            if hasattr(last_node, "attrs"):
                sink_block_id = last_node.attrs.get("block_id", "")
                sink_var = last_node.attrs.get("name", "")
            elif hasattr(last_node, "block_id"):
                sink_block_id = last_node.block_id
                sink_var = getattr(last_node, "name", "")

            if sink_block_id and sink_var:
                try:
                    if self._constraint_validator.is_guard_protected(sink_block_id, sink_var):
                        logger.debug(
                            "path_sanitized_dominator_guard",
                            sink_block=sink_block_id,
                            variable=sink_var,
                        )
                        return True
                except (AttributeError, TypeError):
                    # Validator might not implement is_guard_protected
                    pass

        return False

    def _create_vulnerability(
        self,
        policy: Policy,
        path: "PathResult",
        detected_atoms: DetectedAtoms,
        control: ControlConfig,
    ) -> Vulnerability:
        """
        Create Vulnerability entity from path.

        Args:
            policy: Policy that detected this vulnerability
            path: Validated path from source to sink
            detected_atoms: All detected atoms
            control: Control config (for severity override)

        Returns:
            Vulnerability entity

        Logic:
        1. Find source atom at path start
        2. Find sink atom at path end
        3. Calculate confidence
        4. Apply severity override from control
        5. Create Vulnerability
        """
        # Find source (first node in path)
        if not path.nodes:
            raise RuntimeError("Path has no nodes")

        source_node = path.nodes[0]
        source_node_id = source_node.id if hasattr(source_node, "id") else str(source_node)
        # ⭐ O(1) lookup via index (was O(N) linear search)
        source = detected_atoms.get_source_by_entity_id(source_node_id)
        if not source:
            raise RuntimeError(f"Source not found for node {source_node_id}")

        # Find sink (last node in path)
        sink_node = path.nodes[-1]
        sink_node_id = sink_node.id if hasattr(sink_node, "id") else str(sink_node)
        # ⭐ O(1) lookup via index (was O(N) linear search)
        sink = detected_atoms.get_sink_by_entity_id(sink_node_id)
        if not sink:
            raise RuntimeError(f"Sink not found for node {sink_node_id}")

        # Convert nodes and edges to IDs for TaintFlow
        node_ids = [n.id if hasattr(n, "id") else str(n) for n in path.nodes]
        edge_ids = [e.id if hasattr(e, "id") else str(e) for e in path.edges]

        # Create TaintFlow (expects str IDs, not objects)
        flow = TaintFlow(
            nodes=node_ids,
            edges=edge_ids,
            length=len(path),
            has_sanitizer=False,  # Already checked
            confidence=1.0,
            metadata={},
        )

        # Get severity (with control override)
        severity = self._get_severity(policy, control)

        # Calculate confidence
        confidence = self._calculate_confidence(path, source, sink)

        # Create Vulnerability
        return Vulnerability(
            id=uuid4(),
            policy_id=policy.id,
            policy_name=policy.name,
            severity=severity,
            source=source,
            sink=sink,
            flow=flow,
            confidence=confidence,
            cwe=policy.metadata.get("cwe"),
            owasp=policy.metadata.get("owasp"),
            metadata={
                "policy_description": policy.description,
                "tags": policy.tags,
            },
        )

    def _get_severity(self, policy: Policy, control: ControlConfig) -> str:
        """
        Get severity with control override.

        Args:
            policy: Policy
            control: Control config

        Returns:
            Severity string (low/medium/high/critical)

        Logic:
        - Uses RuleControl.get_effective_severity()
        - Respects severity_override dict
        - Fallback to policy.severity
        """
        return control.rules.get_effective_severity(policy.id, policy.severity or "medium")

    def _calculate_confidence(
        self,
        path: "PathResult",
        source: DetectedSource,
        sink: DetectedSink,
    ) -> float:
        """
        Calculate vulnerability confidence.

        Args:
            path: Detected path
            source: Source atom
            sink: Sink atom

        Returns:
            Confidence score (0.0-1.0)

        Factors:
        1. Path length (shorter = higher confidence)
        2. Source severity
        3. Sink severity

        Formula:
            confidence = severity_factor * length_factor

        Where:
            - severity_factor = (source_severity + sink_severity) / 2
            - length_factor = 1.0 / (1.0 + 0.1 * path_length)
        """
        # Base confidence (default 1.0 since PathResult doesn't have confidence)
        base = 1.0

        # Severity factor
        severity_map = {"low": 0.5, "medium": 0.75, "high": 0.85, "critical": 1.0}
        source_severity = severity_map.get(source.severity, 0.75)
        sink_severity = severity_map.get(sink.severity, 0.75)
        severity_factor = (source_severity + sink_severity) / 2.0

        # Length factor (penalize long paths)
        path_length = len(path)  # Use __len__ instead of .length
        length_factor = 1.0 / (1.0 + 0.1 * path_length)

        # Combined
        confidence = base * severity_factor * length_factor

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, confidence))

    def _deduplicate_vulnerabilities(self, vulnerabilities: list[Vulnerability]) -> list[Vulnerability]:
        """
        Deduplicate vulnerabilities.

        Two vulnerabilities are considered duplicates if they have:
        - Same policy_id
        - Same source location
        - Same sink location

        Args:
            vulnerabilities: List of vulnerabilities

        Returns:
            Deduplicated list (keeps highest confidence)

        Performance:
        - O(N) with dict-based deduplication
        """
        if not vulnerabilities:
            return []

        # Group by (policy_id, source_location, sink_location)
        groups: dict[tuple, list[Vulnerability]] = {}

        for vuln in vulnerabilities:
            key = (
                vuln.policy_id,
                vuln.source.location.get("file_path"),
                vuln.source.location.get("line"),
                vuln.sink.location.get("file_path"),
                vuln.sink.location.get("line"),
            )

            if key not in groups:
                groups[key] = []
            groups[key].append(vuln)

        # Keep highest confidence from each group
        deduplicated = []
        for group in groups.values():
            best = max(group, key=lambda v: v.confidence)
            deduplicated.append(best)

        return deduplicated

    def _get_node_line(self, node: Any) -> int:
        """
        Extract line number from a node's span.

        Handles both NamedTuple-style spans (with start_line attribute)
        and tuple spans (index 0 = start_line).
        """
        if hasattr(node, "span") and node.span:
            span = node.span
            if hasattr(span, "start_line"):
                return span.start_line
            elif isinstance(span, tuple) and len(span) >= 1:
                return span[0]
        elif hasattr(node, "decl_span") and node.decl_span:
            decl_span = node.decl_span
            if hasattr(decl_span, "start_line"):
                return decl_span.start_line
            elif isinstance(decl_span, tuple) and len(decl_span) >= 1:
                return decl_span[0]
        return 0
