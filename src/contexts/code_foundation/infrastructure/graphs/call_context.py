"""
Call Context Model for Context-Sensitive Call Graph

Represents the calling context of a function invocation.
This enables distinguishing different call sites and argument values.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any
from enum import Enum


class ContextSensitivity(Enum):
    """Level of context sensitivity"""
    
    CALL_SITE = "call_site"  # Distinguish by call location
    ARGUMENT = "argument"  # Distinguish by argument values
    FULL = "full"  # Both call site and arguments


@dataclass(frozen=True)
class CallContext:
    """
    Immutable call context
    
    Represents the context in which a function is called:
    - Where it's called from (call_site)
    - What arguments are passed (argument_values)
    - Previous call context (caller_context) for call chains
    
    Example:
        run(flag=True) at main.py:10
        └─> CallContext(
                call_site="main.py:10:5",
                argument_values={"flag": True},
                caller_context=None
            )
    """
    
    call_site: str  # "file.py:line:col"
    argument_values: tuple = field(default_factory=tuple)  # Frozen tuple of (param, value) pairs
    caller_context: Optional["CallContext"] = None  # Parent context
    depth: int = 0  # Call depth (for limiting recursion)
    
    def __post_init__(self):
        """Validate context"""
        if self.depth > 100:  # Safety limit
            raise ValueError(f"Call depth too deep: {self.depth}")
    
    @classmethod
    def from_dict(cls, call_site: str, args: Dict[str, Any], parent: Optional["CallContext"] = None) -> "CallContext":
        """Create context from dictionary of arguments"""
        # Convert dict to sorted tuple for immutability and hashing
        arg_tuple = tuple(sorted(args.items())) if args else tuple()
        depth = (parent.depth + 1) if parent else 0
        return cls(
            call_site=call_site,
            argument_values=arg_tuple,
            caller_context=parent,
            depth=depth,
        )
    
    def context_id(self) -> str:
        """Unique ID for this context"""
        # Include call site and argument values in ID
        args_str = ",".join(f"{k}={v}" for k, v in self.argument_values)
        return f"{self.call_site}#{args_str}"
    
    def short_id(self) -> str:
        """Short ID without full context chain"""
        return self.call_site
    
    def get_argument(self, param_name: str) -> Optional[Any]:
        """Get argument value for parameter"""
        args_dict = dict(self.argument_values)
        return args_dict.get(param_name)
    
    def matches_pattern(self, pattern: Dict[str, Any]) -> bool:
        """Check if context matches a pattern"""
        args_dict = dict(self.argument_values)
        for key, value in pattern.items():
            if args_dict.get(key) != value:
                return False
        return True
    
    def __repr__(self) -> str:
        args_str = ", ".join(f"{k}={v}" for k, v in self.argument_values)
        return f"CallContext({self.call_site}, [{args_str}], depth={self.depth})"


@dataclass
class ContextSensitiveCallGraph:
    """
    Context-sensitive call graph
    
    Maps (caller_context, callee) → Set[CallContext]
    
    This allows distinguishing:
    - Different call sites
    - Different argument values
    - Different call chains
    
    Example:
        run(True) → fast()   (context 1)
        run(False) → slow()  (context 2)
    """
    
    # (caller_id, callee_id) → Set[CallContext]
    edges: Dict[tuple[str, str], Set[CallContext]] = field(default_factory=dict)
    
    # caller_id → Set[callee_id]
    _basic_edges: Optional[Set[tuple[str, str]]] = None
    
    def add_edge(self, caller: str, callee: str, context: CallContext):
        """Add context-sensitive edge"""
        key = (caller, callee)
        if key not in self.edges:
            self.edges[key] = set()
        self.edges[key].add(context)
        
        # Invalidate basic edges cache
        self._basic_edges = None
    
    def get_contexts(self, caller: str, callee: str) -> Set[CallContext]:
        """Get all contexts for a call edge"""
        return self.edges.get((caller, callee), set())
    
    def get_callees(self, caller: str, context: Optional[CallContext] = None) -> Set[str]:
        """Get callees from caller (optionally filtered by context)"""
        callees = set()
        for (c, callee), contexts in self.edges.items():
            if c == caller:
                if context is None:
                    # Return all callees
                    callees.add(callee)
                else:
                    # Return callees matching context
                    if context in contexts:
                        callees.add(callee)
        return callees
    
    def get_reachable(
        self,
        start: str,
        context: CallContext,
        max_depth: int = 10,
    ) -> Set[tuple[str, CallContext]]:
        """
        Get all reachable functions from start in given context
        
        Returns: Set of (function_id, context) tuples
        """
        visited = set()
        queue = [(start, context)]
        
        while queue:
            current, ctx = queue.pop(0)
            
            # Check depth limit
            if ctx.depth >= max_depth:
                continue
            
            # Check if already visited
            if (current, ctx) in visited:
                continue
            visited.add((current, ctx))
            
            # Find callees in this context
            for (caller, callee), contexts in self.edges.items():
                if caller == current:
                    for callee_ctx in contexts:
                        # Check if contexts are compatible
                        if self._contexts_compatible(ctx, callee_ctx):
                            queue.append((callee, callee_ctx))
        
        return visited
    
    def _contexts_compatible(self, parent: CallContext, child: CallContext) -> bool:
        """Check if child context is compatible with parent context"""
        # For now, simple check: child's caller_context should match parent
        # In more sophisticated implementation, could check argument flow
        return True  # Simplified
    
    def to_basic_cg(self) -> Set[tuple[str, str]]:
        """Convert to basic (context-insensitive) call graph"""
        if self._basic_edges is None:
            self._basic_edges = set(self.edges.keys())
        return self._basic_edges
    
    def compare_with_basic(self, basic_cg: Set[tuple[str, str]]) -> Dict[str, Any]:
        """
        Compare with basic call graph
        
        Returns metrics showing how context sensitivity refined the graph
        """
        cs_basic = self.to_basic_cg()
        
        # Count distinct contexts
        total_contexts = sum(len(contexts) for contexts in self.edges.values())
        
        return {
            "basic_edges": len(basic_cg),
            "cs_edges": len(cs_basic),
            "total_contexts": total_contexts,
            "avg_contexts_per_edge": total_contexts / len(cs_basic) if cs_basic else 0,
            "common_edges": len(basic_cg & cs_basic),
            "precision_gain_pct": (
                (len(basic_cg) - len(cs_basic)) / len(basic_cg) * 100
                if basic_cg
                else 0
            ),
        }
    
    def __len__(self) -> int:
        """Total number of context-sensitive edges"""
        return sum(len(contexts) for contexts in self.edges.values())
    
    def __repr__(self) -> str:
        return f"ContextSensitiveCallGraph({len(self.edges)} edge types, {len(self)} contexts)"

