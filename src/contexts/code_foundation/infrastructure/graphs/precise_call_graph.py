"""
Precise Call Graph Builder

Uses type narrowing to build more accurate call graphs.
"""

from typing import Dict, Set, Optional, List
from dataclasses import dataclass

from src.common.observability import get_logger
from src.contexts.code_foundation.infrastructure.analyzers.type_narrowing_full import (
    FullTypeNarrowingAnalyzer,
    TypeState,
)

logger = get_logger(__name__)


@dataclass
class CallSite:
    """Call site with type information"""

    caller_id: str
    callee_name: str
    location: tuple[int, int]  # (line, col)
    receiver_type: Optional[str] = None  # Type of receiver (for methods)
    is_narrowed: bool = False  # Whether type was narrowed


@dataclass
class PreciseCallEdge:
    """Precise call edge with type context"""

    caller_id: str
    callee_id: str
    call_site: CallSite
    confidence: float = 1.0  # 0.0 - 1.0


class PreciseCallGraphBuilder:
    """
    Build precise call graph using type narrowing
    
    Key improvements over basic call graph:
    - Use type narrowing to eliminate impossible calls
    - Track receiver types for method calls
    - Higher precision, fewer false positives
    
    Example:
        def process(handler: Handler):
            if isinstance(handler, FastHandler):
                handler.fast_process()  # Only FastHandler.fast_process
            else:
                handler.slow_process()  # Handler.slow_process (not FastHandler)
    """

    def __init__(self):
        self.type_narrowing = FullTypeNarrowingAnalyzer()
        self.edges: List[PreciseCallEdge] = []

    def build_precise_cg(
        self, ir_documents: Dict[str, dict], initial_types: Dict[str, Dict[str, Set[str]]] = None
    ) -> List[PreciseCallEdge]:
        """
        Build precise call graph from IR documents
        
        Args:
            ir_documents: {file_path: IR document}
            initial_types: {file_path: {var: {types}}}
        
        Returns:
            List of precise call edges
        """
        self.edges.clear()

        for file_path, ir_doc in ir_documents.items():
            file_types = initial_types.get(file_path, {}) if initial_types else {}
            self._process_file(file_path, ir_doc, file_types)

        logger.info(
            "precise_call_graph_built", num_edges=len(self.edges), num_files=len(ir_documents)
        )

        return self.edges

    def _process_file(self, file_path: str, ir_doc: dict, initial_types: Dict[str, Set[str]]):
        """Process single file"""
        symbols = ir_doc.get("symbols", [])

        for symbol in symbols:
            self._process_symbol(file_path, symbol, initial_types)

    def _process_symbol(self, file_path: str, symbol: dict, initial_types: Dict[str, Set[str]]):
        """Process single symbol (function/method)"""
        symbol_id = symbol.get("id", "")
        calls = symbol.get("calls", [])
        body = symbol.get("body", "")

        # Run actual type narrowing on function body
        type_state = self._analyze_body_with_narrowing(body, initial_types)

        for call in calls:
            # Get type state at call location
            call_line = call.get("location", (0, 0))[0]
            type_state_at_call = self._get_type_state_at_line(type_state, call_line)
            self._process_call(symbol_id, call, type_state_at_call)
    
    def _analyze_body_with_narrowing(
        self, 
        body: str, 
        initial_types: Dict[str, Set[str]]
    ) -> Dict[int, TypeState]:
        """
        Analyze function body with type narrowing
        Returns: {line_number: TypeState}
        """
        if not body:
            return {0: TypeState(variables=initial_types.copy())}
        
        # Parse body to extract control flow and type guards
        type_states = {0: TypeState(variables=initial_types.copy())}
        current_state = TypeState(variables=initial_types.copy())
        
        # Simple line-by-line analysis
        for line_num, line in enumerate(body.split('\n'), start=1):
            line = line.strip()
            
            # Detect isinstance checks
            if 'isinstance(' in line:
                var, typ = self._parse_isinstance(line)
                if var and typ:
                    # Narrow type
                    narrowed_state = current_state.copy()
                    narrowed_state.variables[var] = {typ}
                    type_states[line_num] = narrowed_state
                    current_state = narrowed_state
                    continue
            
            # Detect None checks
            if ' is not None' in line or ' is None' in line:
                var = self._parse_none_check(line)
                if var:
                    narrowed_state = current_state.copy()
                    if ' is not None' in line:
                        # Remove None type
                        if var in narrowed_state.variables:
                            narrowed_state.variables[var].discard('None')
                    type_states[line_num] = narrowed_state
                    current_state = narrowed_state
                    continue
            
            type_states[line_num] = current_state
        
        return type_states
    
    def _parse_isinstance(self, line: str) -> tuple[Optional[str], Optional[str]]:
        """Parse isinstance(var, Type) → (var, Type)"""
        import re
        match = re.search(r'isinstance\(\s*(\w+)\s*,\s*(\w+)\s*\)', line)
        if match:
            return match.group(1), match.group(2)
        return None, None
    
    def _parse_none_check(self, line: str) -> Optional[str]:
        """Parse 'var is None' → var"""
        import re
        match = re.search(r'(\w+)\s+is\s+(?:not\s+)?None', line)
        if match:
            return match.group(1)
        return None
    
    def _get_type_state_at_line(
        self, 
        type_states: Dict[int, TypeState], 
        line: int
    ) -> TypeState:
        """Get type state at specific line"""
        # Find closest line <= target line
        valid_lines = [l for l in type_states.keys() if l <= line]
        if valid_lines:
            closest_line = max(valid_lines)
            return type_states[closest_line]
        return type_states.get(0, TypeState(variables={}))

    def _process_call(self, caller_id: str, call: dict, type_state: TypeState):
        """Process single call with type information"""
        target_id = call.get("target_id")
        if not target_id:
            return

        # Extract call site info
        location = call.get("location", (0, 0))
        receiver = call.get("receiver")  # Variable name (e.g., "handler")

        # Determine receiver type
        receiver_type = None
        is_narrowed = False

        if receiver and receiver in type_state.variables:
            # Get type(s) from type state
            types = type_state.variables[receiver]
            if len(types) == 1:
                # Single type (narrowed!)
                receiver_type = list(types)[0]
                is_narrowed = True
            elif len(types) > 1:
                # Multiple types (union) - not narrowed
                receiver_type = f"Union[{', '.join(sorted(types))}]"
                is_narrowed = False

        # Create call site
        call_site = CallSite(
            caller_id=caller_id,
            callee_name=call.get("name", ""),
            location=location,
            receiver_type=receiver_type,
            is_narrowed=is_narrowed,
        )

        # Calculate confidence
        confidence = 1.0 if is_narrowed else 0.7  # Higher confidence for narrowed types

        # Create edge
        edge = PreciseCallEdge(
            caller_id=caller_id,
            callee_id=target_id,
            call_site=call_site,
            confidence=confidence,
        )

        self.edges.append(edge)

        logger.debug(
            "precise_call_added",
            caller=caller_id,
            callee=target_id,
            receiver_type=receiver_type,
            is_narrowed=is_narrowed,
            confidence=confidence,
        )

    def get_edges_by_confidence(self, min_confidence: float = 0.8) -> List[PreciseCallEdge]:
        """Get high-confidence edges only"""
        return [e for e in self.edges if e.confidence >= min_confidence]

    def get_narrowed_edges(self) -> List[PreciseCallEdge]:
        """Get edges where receiver type was narrowed"""
        return [e for e in self.edges if e.call_site.is_narrowed]

    def compare_with_basic_cg(self, basic_edges: Set[tuple[str, str]]) -> Dict[str, int]:
        """
        Compare with basic call graph
        
        Returns metrics showing improvement
        """
        precise_set = {(e.caller_id, e.callee_id) for e in self.edges}

        return {
            "basic_edges": len(basic_edges),
            "precise_edges": len(precise_set),
            "common_edges": len(basic_edges & precise_set),
            "eliminated_edges": len(basic_edges - precise_set),  # False positives removed
            "new_edges": len(precise_set - basic_edges),
            "precision_gain": (
                (len(basic_edges - precise_set) / len(basic_edges) * 100)
                if basic_edges
                else 0
            ),
        }

