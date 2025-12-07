"""
Path-Sensitive Taint Analysis with State Merging

Key techniques:
1. Path-sensitive: Track taint per execution path
2. Meet-Over-Paths: Conservative state merging at join points
3. Strong/Weak updates: Precise when safe, conservative when needed

Performance:
- Without merging: Exponential state explosion
- With merging: Linear growth, controlled memory
"""

import logging
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TaintState:
    """
    Taint state at a program point

    Tracks:
    - Which variables are tainted
    - Path conditions leading here
    - Depth (for loop limiting)

    Example:
        if user_is_admin:
            # State: tainted_vars={input}, path_condition=["user_is_admin"]
            safe_execute(query)
        else:
            # State: tainted_vars={input}, path_condition=["!user_is_admin"]
            dangerous_execute(query)
    """

    tainted_vars: set[str] = field(default_factory=set)
    """Set of tainted variable names"""

    path_condition: list[str] = field(default_factory=list)
    """Conditions on this execution path"""

    depth: int = 0
    """Path depth (for loop/recursion limiting)"""

    metadata: dict = field(default_factory=dict)
    """Additional metadata"""

    def copy(self):
        """Create deep copy of state"""
        return TaintState(
            tainted_vars=self.tainted_vars.copy(),
            path_condition=self.path_condition.copy(),
            depth=self.depth,
            metadata=self.metadata.copy(),
        )

    def __repr__(self):
        return f"TaintState(tainted={self.tainted_vars}, conditions={len(self.path_condition)}, depth={self.depth})"


class PathSensitiveTaintAnalyzer:
    """
    Path-sensitive taint analysis with state merging

    Algorithm:
    1. Worklist iteration on CFG
    2. Transfer function per node type
    3. State merging at join points
    4. Loop limiting (k-limiting)

    Example:
        user_input = request.get("id")  # Source

        if is_admin:
            # Path 1: admin check passes
            execute(query)  # NOT tainted (sanitized by condition)
        else:
            # Path 2: admin check fails
            execute(query)  # Tainted!

    Performance:
        - Max states per node: 1 (with merging)
        - Memory: O(CFG nodes)
        - Time: O(CFG edges × transfer cost)
    """

    def __init__(self, cfg, dfg, max_depth: int = 100):
        """
        Initialize analyzer

        Args:
            cfg: Control Flow Graph
            dfg: Data Flow Graph
            max_depth: Max path depth (loop limiting)
        """
        self.cfg = cfg
        self.dfg = dfg
        self.max_depth = max_depth

        # Analysis state
        self.states: dict[str, TaintState] = {}  # node_id → state
        self.worklist: deque = deque()

    def analyze(
        self,
        sources: set[str],
        sinks: set[str],
        sanitizers: set[str] | None = None,
    ) -> list[dict]:
        """
        Run path-sensitive taint analysis

        Args:
            sources: Taint sources (variable names)
            sinks: Taint sinks (node IDs)
            sanitizers: Sanitizing functions (optional)

        Returns:
            List of vulnerabilities (unsanitized paths to sinks)

        Example:
            sources = {"user_input"}
            sinks = {"db_execute_node_1", "db_execute_node_2"}

            vulns = analyzer.analyze(sources, sinks)
            # Returns: [
            #   {
            #     "sink": "db_execute_node_2",
            #     "tainted_vars": {"user_input"},
            #     "path": ["!is_admin"],
            #   }
            # ]
        """
        sanitizers = sanitizers or set()

        # Initialize entry state
        entry_state = TaintState(
            tainted_vars=sources.copy(),
            path_condition=[],
            depth=0,
        )

        entry_node = self._get_entry_node()
        self.states[entry_node] = entry_state
        self.worklist.append(entry_node)

        # Worklist iteration
        while self.worklist:
            node_id = self.worklist.popleft()
            current_state = self.states.get(node_id)

            if not current_state:
                continue

            # Check depth limit
            if current_state.depth > self.max_depth:
                logger.warning(f"Max depth reached at {node_id}")
                continue

            # Transfer function
            new_state = self._transfer(node_id, current_state, sanitizers)

            # Propagate to successors
            for succ_id in self._get_successors(node_id):
                self._propagate_state(node_id, succ_id, new_state)

        # Check sinks for vulnerabilities
        return self._check_sinks(sinks)

    def _transfer(
        self,
        node_id: str,
        state: TaintState,
        sanitizers: set[str],
    ) -> TaintState:
        """
        Transfer function: Apply node's effect on taint state

        Node types:
        - Assignment: x = y
        - Call: f(x)
        - Branch: if condition

        Args:
            node_id: CFG node ID
            state: Input state
            sanitizers: Known sanitizers

        Returns:
            Output state
        """
        new_state = state.copy()
        node = self._get_node(node_id)

        if not node:
            return new_state

        # Assignment: x = y
        if node.type == "assignment":
            new_state = self._transfer_assignment(node, new_state)

        # Call: result = f(x)
        elif node.type == "call":
            new_state = self._transfer_call(node, new_state, sanitizers)

        # Branch: if condition
        elif node.type == "branch":
            # Handled in propagate_state
            pass

        return new_state

    def _transfer_assignment(self, node, state: TaintState) -> TaintState:
        """
        Transfer for assignment: x = expr

        Rules:
        - If RHS is tainted → LHS becomes tainted
        - If RHS is clean → LHS becomes clean (strong update)

        Example:
            x = user_input  # x becomes tainted
            y = 5           # y is clean
            x = y           # x becomes clean (strong update)
        """
        lhs = node.lhs  # Variable being assigned
        rhs_vars = self._get_vars_in_expr(node.rhs)

        # Check if any RHS variable is tainted
        if any(var in state.tainted_vars for var in rhs_vars):
            # Taint propagates
            state.tainted_vars.add(lhs)
        else:
            # Clean assignment - remove taint (strong update)
            state.tainted_vars.discard(lhs)

        return state

    def _transfer_call(
        self,
        node,
        state: TaintState,
        sanitizers: set[str],
    ) -> TaintState:
        """
        Transfer for function call: result = f(arg1, arg2)

        Rules:
        - If function is sanitizer → remove taint from args
        - If args are tainted → result becomes tainted

        Example:
            clean = escape_html(user_input)  # clean is NOT tainted
            dirty = process(user_input)      # dirty IS tainted
        """
        func_name = node.function_name
        args = self._get_call_args(node)
        result_var = getattr(node, "result_var", None)

        # Check if sanitizer
        if func_name in sanitizers:
            # Sanitizer - result is clean
            if result_var:
                state.tainted_vars.discard(result_var)
            return state

        # Check if any argument is tainted
        tainted_args = any(arg in state.tainted_vars for arg in args)

        if tainted_args and result_var:
            # Taint propagates to result
            state.tainted_vars.add(result_var)

        return state

    def _propagate_state(
        self,
        from_node: str,
        to_node: str,
        state: TaintState,
    ):
        """
        Propagate state to successor with merging

        Key decision: Merge or replace?
        - Single predecessor → Strong update (replace)
        - Multiple predecessors → Weak update (merge)

        Args:
            from_node: Source node
            to_node: Target node
            state: State to propagate
        """
        # Get branch condition (if any)
        edge = self._get_edge(from_node, to_node)
        if edge and edge.condition:
            # Add condition to path
            state_with_cond = state.copy()
            state_with_cond.path_condition.append(edge.condition)

            # Check if condition sanitizes
            if self._sanitizes_condition(edge.condition, state.tainted_vars):
                # Condition acts as sanitizer
                state_with_cond.tainted_vars.clear()

            state = state_with_cond

        # Increment depth
        state.depth += 1

        # Merge or replace
        predecessors = self._get_predecessors(to_node)

        if len(predecessors) == 1:
            # Strong update: Single predecessor
            self._strong_update(to_node, state)
        else:
            # Weak update: Multiple predecessors (join point)
            self._merge_state(to_node, state)

        # Add to worklist if changed
        if to_node not in self.worklist:
            self.worklist.append(to_node)

    def _strong_update(self, node_id: str, new_state: TaintState):
        """
        Strong update: Replace state (precise)

        Use case:
            x = user_input  # Tainted
            x = 5           # Clean (strong update: x is NOT tainted)

        Only safe when:
        - Single reaching definition
        - No merge point
        """
        self.states[node_id] = new_state
        logger.debug(f"Strong update at {node_id}: {new_state}")

    def _merge_state(self, node_id: str, new_state: TaintState):
        """
        Weak update: Merge states (conservative)

        Meet-Over-Paths strategy: Union of tainted vars

        Example:
            if condition:
                x = tainted     # Path 1: {x}
            else:
                y = tainted     # Path 2: {y}
            # Join: {x, y}  (union, conservative)

        Trade-off:
            Precision: Lower (may report false positives)
            Performance: Higher (fewer states)

        Args:
            node_id: Node to merge at
            new_state: New state to merge
        """
        if node_id not in self.states:
            # First state for this node
            self.states[node_id] = new_state
            logger.debug(f"First state at {node_id}: {new_state}")
            return

        existing = self.states[node_id]

        # Conservative union: Any variable tainted on any path
        existing.tainted_vars.update(new_state.tainted_vars)

        # Keep longer path condition (more context)
        if len(new_state.path_condition) > len(existing.path_condition):
            existing.path_condition = new_state.path_condition

        # Max depth
        existing.depth = max(existing.depth, new_state.depth)

        logger.debug(f"Merged state at {node_id}: {len(existing.tainted_vars)} tainted vars")

    def _sanitizes_condition(
        self,
        condition: str,
        tainted_vars: set[str],
    ) -> bool:
        """
        Check if condition sanitizes tainted variables

        Sanitizing conditions:
        - is_admin, is_authenticated (authorization)
        - x.isdigit(), x.isalnum() (validation)
        - re.match(pattern, x) (regex validation)

        Args:
            condition: Condition string
            tainted_vars: Currently tainted variables

        Returns:
            True if condition sanitizes

        Example:
            if is_admin:
                # This path is sanitized
                execute(query)
        """
        # Authorization checks
        auth_patterns = [
            r"is_admin",
            r"is_authenticated",
            r"is_authorized",
            r"has_permission",
        ]
        for pattern in auth_patterns:
            if pattern in condition.lower():
                return True

        # Validation checks
        validation_patterns = [
            r"\.isdigit\(\)",
            r"\.isalnum\(\)",
            r"\.isnumeric\(\)",
            r"re\.match",
            r"re\.fullmatch",
        ]
        for pattern in validation_patterns:
            if pattern in condition:
                return True

        return False

    def _check_sinks(self, sinks: set[str]) -> list[dict]:
        """
        Check sinks for tainted variables

        Args:
            sinks: Set of sink node IDs

        Returns:
            List of vulnerabilities
        """
        vulnerabilities = []

        for sink_id in sinks:
            state = self.states.get(sink_id)
            if not state:
                continue

            # Check if any variables are tainted at this sink
            if state.tainted_vars:
                # Check if sanitized on this path
                if not self._is_sanitized_on_path(state):
                    vulnerabilities.append(
                        {
                            "sink": sink_id,
                            "tainted_vars": state.tainted_vars.copy(),
                            "path": state.path_condition.copy(),
                            "depth": state.depth,
                        }
                    )

        return vulnerabilities

    def _is_sanitized_on_path(self, state: TaintState) -> bool:
        """
        Check if path conditions sanitize taint

        Args:
            state: Taint state

        Returns:
            True if sanitized by path conditions
        """
        for condition in state.path_condition:
            if self._sanitizes_condition(condition, state.tainted_vars):
                return True

        return False

    # Helper methods (placeholders for actual CFG/DFG integration)

    def _get_entry_node(self) -> str:
        """Get CFG entry node ID"""
        return getattr(self.cfg, "entry", "entry")

    def _get_node(self, node_id: str):
        """Get CFG node by ID"""
        return getattr(self.cfg, "nodes", {}).get(node_id)

    def _get_successors(self, node_id: str) -> list[str]:
        """Get successor node IDs"""
        return getattr(self.cfg, "successors", {}).get(node_id, [])

    def _get_predecessors(self, node_id: str) -> list[str]:
        """Get predecessor node IDs"""
        return getattr(self.cfg, "predecessors", {}).get(node_id, [])

    def _get_edge(self, from_node: str, to_node: str):
        """Get edge between nodes"""
        edges = getattr(self.cfg, "edges", [])
        for edge in edges:
            if edge.from_node == from_node and edge.to_node == to_node:
                return edge
        return None

    def _get_vars_in_expr(self, expr) -> set[str]:
        """Extract variable names from expression"""
        # TODO: Implement actual expression analysis
        return set()

    def _get_call_args(self, call_node) -> list[str]:
        """Extract argument variable names from call"""
        # TODO: Implement actual call analysis
        return []


# Convenience function


def create_path_sensitive_analyzer(cfg, dfg, max_depth: int = 100):
    """
    Create path-sensitive taint analyzer

    Args:
        cfg: Control Flow Graph
        dfg: Data Flow Graph
        max_depth: Maximum path depth

    Returns:
        PathSensitiveTaintAnalyzer

    Example:
        analyzer = create_path_sensitive_analyzer(cfg, dfg)

        vulns = analyzer.analyze(
            sources={"user_input"},
            sinks={"db_execute"},
            sanitizers={"escape_html"},
        )

        for vuln in vulns:
            print(f"Vulnerability at {vuln['sink']}")
            print(f"  Tainted: {vuln['tainted_vars']}")
            print(f"  Path: {vuln['path']}")
    """
    return PathSensitiveTaintAnalyzer(cfg, dfg, max_depth)
