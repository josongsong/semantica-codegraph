"""
Speculative Execution Models

Data models for speculative graph execution.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List
from enum import Enum, auto


class PatchType(Enum):
    """Type of code patch"""
    
    CODE_MOVE = "code_move"  # Move code to different location
    RENAME = "rename"  # Rename symbol
    ADD_FIELD = "add_field"  # Add new field/property
    ADD_METHOD = "add_method"  # Add new method
    CHANGE_SIGNATURE = "change_signature"  # Change function signature
    REFACTOR = "refactor"  # General refactoring
    DELETE = "delete"  # Delete code
    MODIFY = "modify"  # Modify existing code


class RiskLevel(Enum):
    """Risk level of applying a patch"""
    
    SAFE = auto()  # No breaking changes
    LOW = auto()  # Minor impact
    MEDIUM = auto()  # Moderate impact
    HIGH = auto()  # Significant impact
    CRITICAL = auto()  # Breaking changes
    
    def __lt__(self, other):
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.value < other.value
    
    def __le__(self, other):
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.value <= other.value
    
    def __gt__(self, other):
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.value > other.value
    
    def __ge__(self, other):
        if not isinstance(other, RiskLevel):
            return NotImplemented
        return self.value >= other.value


@dataclass
class SpeculativePatch:
    """
    Represents a speculative code patch
    
    Example:
        # Rename variable
        patch = SpeculativePatch(
            patch_type=PatchType.RENAME,
            target_symbol="old_name",
            new_value="new_name",
            file_path="service.py"
        )
        
        # Add new field
        patch = SpeculativePatch(
            patch_type=PatchType.ADD_FIELD,
            target_symbol="MyClass",
            new_value="new_field: str",
            file_path="models.py"
        )
    """
    
    # Identity
    patch_id: str
    patch_type: PatchType
    
    # Target
    file_path: str
    target_symbol: str  # Symbol to modify
    
    # Patch content
    old_value: Optional[str] = None  # Original code/value
    new_value: Optional[str] = None  # New code/value
    
    # Context
    description: str = ""  # Human-readable description
    reason: str = ""  # Why this patch is needed
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_breaking_change(self) -> bool:
        """Check if patch is likely a breaking change"""
        return self.patch_type in (
            PatchType.CHANGE_SIGNATURE,
            PatchType.DELETE,
            PatchType.RENAME,
        )
    
    def __repr__(self) -> str:
        return (
            f"SpeculativePatch("
            f"type={self.patch_type.value}, "
            f"target={self.target_symbol}, "
            f"file={self.file_path})"
        )


@dataclass
class GraphDelta:
    """
    Represents changes to the graph
    
    Tracks:
    - Added/removed nodes
    - Added/removed edges
    - Modified properties
    """
    
    # Node changes
    nodes_added: Set[str] = field(default_factory=set)
    nodes_removed: Set[str] = field(default_factory=set)
    nodes_modified: Set[str] = field(default_factory=set)
    
    # Edge changes
    edges_added: Set[tuple[str, str]] = field(default_factory=set)  # (source, target)
    edges_removed: Set[tuple[str, str]] = field(default_factory=set)
    
    # Property changes
    properties_changed: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # Call graph changes
    call_graph_delta: Optional[Dict[str, Any]] = None
    
    # Type flow changes
    type_flow_delta: Optional[Dict[str, Any]] = None
    
    def is_empty(self) -> bool:
        """Check if delta is empty (no changes)"""
        return (
            not self.nodes_added and
            not self.nodes_removed and
            not self.nodes_modified and
            not self.edges_added and
            not self.edges_removed and
            not self.properties_changed
        )
    
    def size(self) -> int:
        """Total number of changes"""
        return (
            len(self.nodes_added) +
            len(self.nodes_removed) +
            len(self.nodes_modified) +
            len(self.edges_added) +
            len(self.edges_removed) +
            len(self.properties_changed)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "nodes_added": list(self.nodes_added),
            "nodes_removed": list(self.nodes_removed),
            "nodes_modified": list(self.nodes_modified),
            "edges_added": [list(e) for e in self.edges_added],
            "edges_removed": [list(e) for e in self.edges_removed],
            "properties_changed": self.properties_changed,
            "total_changes": self.size(),
        }
    
    def __repr__(self) -> str:
        return (
            f"GraphDelta("
            f"+{len(self.nodes_added)} nodes, "
            f"-{len(self.nodes_removed)} nodes, "
            f"~{len(self.nodes_modified)} nodes, "
            f"+{len(self.edges_added)} edges, "
            f"-{len(self.edges_removed)} edges)"
        )


@dataclass
class SpeculativeResult:
    """
    Result of speculative execution
    
    Contains:
    - Predicted graph changes
    - Risk analysis
    - Recommendations
    
    Example:
        result = execute_speculatively(patch)
        
        if result.risk_level == RiskLevel.SAFE:
            apply_patch(patch)
        else:
            print(f"Risk: {result.risk_reasons}")
    """
    
    # Input
    patch: SpeculativePatch
    
    # Predicted changes
    graph_delta: GraphDelta
    
    # Risk analysis
    risk_level: RiskLevel
    risk_reasons: List[str] = field(default_factory=list)
    
    # Impact analysis
    affected_symbols: Set[str] = field(default_factory=set)
    affected_files: Set[str] = field(default_factory=set)
    breaking_changes: List[str] = field(default_factory=list)
    
    # Call graph changes
    callers_affected: Set[str] = field(default_factory=set)
    callees_affected: Set[str] = field(default_factory=set)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    
    # Performance estimates
    estimated_rebuild_time_ms: float = 0.0
    estimated_test_time_ms: float = 0.0
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_safe(self) -> bool:
        """Check if patch is safe to apply"""
        return self.risk_level in (RiskLevel.SAFE, RiskLevel.LOW)
    
    def has_breaking_changes(self) -> bool:
        """Check if patch has breaking changes"""
        return len(self.breaking_changes) > 0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of speculative execution"""
        return {
            "patch_type": self.patch.patch_type.value,
            "target": self.patch.target_symbol,
            "risk_level": self.risk_level.name,
            "graph_changes": self.graph_delta.size(),
            "affected_symbols": len(self.affected_symbols),
            "affected_files": len(self.affected_files),
            "breaking_changes": len(self.breaking_changes),
            "is_safe": self.is_safe(),
            "recommendations": len(self.recommendations),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "patch": {
                "type": self.patch.patch_type.value,
                "target": self.patch.target_symbol,
                "file": self.patch.file_path,
            },
            "graph_delta": self.graph_delta.to_dict(),
            "risk_level": self.risk_level.name,
            "risk_reasons": self.risk_reasons,
            "affected_symbols": list(self.affected_symbols),
            "affected_files": list(self.affected_files),
            "breaking_changes": self.breaking_changes,
            "callers_affected": list(self.callers_affected),
            "recommendations": self.recommendations,
            "estimated_rebuild_time_ms": self.estimated_rebuild_time_ms,
            "is_safe": self.is_safe(),
        }
    
    def __repr__(self) -> str:
        summary = self.get_summary()
        return (
            f"SpeculativeResult("
            f"risk={summary['risk_level']}, "
            f"changes={summary['graph_changes']}, "
            f"affected={summary['affected_symbols']}, "
            f"safe={summary['is_safe']})"
        )


@dataclass
class SimulationContext:
    """
    Context for graph simulation
    
    Contains current state needed for simulation
    """
    
    # Current IR
    current_ir: Dict[str, Any] = field(default_factory=dict)
    
    # Current call graph
    call_graph: Optional[Any] = None
    
    # Current type graph
    type_graph: Optional[Any] = None
    
    # Symbol table
    symbol_table: Dict[str, Any] = field(default_factory=dict)
    
    # File cache
    file_cache: Dict[str, str] = field(default_factory=dict)
    
    def get_symbol(self, symbol_id: str) -> Optional[Any]:
        """Get symbol from table"""
        return self.symbol_table.get(symbol_id)
    
    def get_file_ir(self, file_path: str) -> Optional[Any]:
        """Get IR for file"""
        return self.current_ir.get(file_path)
    
    def __repr__(self) -> str:
        return (
            f"SimulationContext("
            f"files={len(self.current_ir)}, "
            f"symbols={len(self.symbol_table)})"
        )

