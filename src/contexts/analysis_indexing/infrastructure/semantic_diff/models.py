"""
Semantic Change Models

Data models for semantic change detection.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List
from enum import Enum, auto


class ChangeType(Enum):
    """Type of semantic change"""
    
    # Signature changes
    PARAMETER_ADDED = "parameter_added"
    PARAMETER_REMOVED = "parameter_removed"
    PARAMETER_REORDERED = "parameter_reordered"
    PARAMETER_TYPE_CHANGED = "parameter_type_changed"
    RETURN_TYPE_CHANGED = "return_type_changed"
    
    # Behavioral changes
    SIDE_EFFECT_ADDED = "side_effect_added"
    SIDE_EFFECT_REMOVED = "side_effect_removed"
    ERROR_PATH_CHANGED = "error_path_changed"
    CONTROL_FLOW_CHANGED = "control_flow_changed"
    
    # Structural changes
    INHERITANCE_CHANGED = "inheritance_changed"
    INTERFACE_CHANGED = "interface_changed"
    VISIBILITY_CHANGED = "visibility_changed"
    
    # Dependency changes
    DEPENDENCY_ADDED = "dependency_added"
    DEPENDENCY_REMOVED = "dependency_removed"
    REACHABLE_SET_CHANGED = "reachable_set_changed"
    
    # Logic changes
    ALGORITHM_CHANGED = "algorithm_changed"
    COMPLEXITY_CHANGED = "complexity_changed"


class ChangeSeverity(Enum):
    """Severity of semantic change"""
    
    TRIVIAL = auto()  # Comment, formatting
    MINOR = auto()  # Local variable rename
    MODERATE = auto()  # Logic change, no API impact
    MAJOR = auto()  # API change, backward compatible
    BREAKING = auto()  # Breaking change
    
    def __lt__(self, other):
        if not isinstance(other, ChangeSeverity):
            return NotImplemented
        return self.value < other.value
    
    def __le__(self, other):
        if not isinstance(other, ChangeSeverity):
            return NotImplemented
        return self.value <= other.value
    
    def __gt__(self, other):
        if not isinstance(other, ChangeSeverity):
            return NotImplemented
        return self.value > other.value
    
    def __ge__(self, other):
        if not isinstance(other, ChangeSeverity):
            return NotImplemented
        return self.value >= other.value


@dataclass
class SemanticChange:
    """
    Represents a semantic change
    
    Example:
        # Parameter removed
        change = SemanticChange(
            change_type=ChangeType.PARAMETER_REMOVED,
            severity=ChangeSeverity.BREAKING,
            symbol_id="calculate_price",
            description="Parameter 'discount' removed",
            old_value="discount: float",
            new_value=None,
        )
    """
    
    # Identity
    change_type: ChangeType
    severity: ChangeSeverity
    
    # Target
    file_path: str
    symbol_id: str
    
    # Details
    description: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    
    # Impact
    affected_symbols: Set[str] = field(default_factory=set)
    breaking_callers: Set[str] = field(default_factory=set)
    
    # Evidence
    evidence: List[str] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_breaking(self) -> bool:
        """Check if change is breaking"""
        return self.severity == ChangeSeverity.BREAKING
    
    def add_affected(self, symbol_id: str):
        """Add affected symbol"""
        self.affected_symbols.add(symbol_id)
    
    def add_evidence(self, evidence: str):
        """Add evidence for this change"""
        self.evidence.append(evidence)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "change_type": self.change_type.value,
            "severity": self.severity.name,
            "file_path": self.file_path,
            "symbol_id": self.symbol_id,
            "description": self.description,
            "old_value": str(self.old_value) if self.old_value else None,
            "new_value": str(self.new_value) if self.new_value else None,
            "affected_symbols": list(self.affected_symbols),
            "breaking_callers": list(self.breaking_callers),
            "is_breaking": self.is_breaking(),
            "evidence": self.evidence,
        }
    
    def __repr__(self) -> str:
        return (
            f"SemanticChange("
            f"type={self.change_type.value}, "
            f"severity={self.severity.name}, "
            f"symbol={self.symbol_id})"
        )


@dataclass
class SemanticDiff:
    """
    Collection of semantic changes between two versions
    
    Represents all semantic changes detected between
    old and new versions of code.
    """
    
    changes: List[SemanticChange] = field(default_factory=list)
    
    # Statistics
    _stats: Optional[Dict[str, Any]] = None
    
    def add_change(self, change: SemanticChange):
        """Add semantic change"""
        self.changes.append(change)
        self._stats = None  # Invalidate cache
    
    def get_breaking_changes(self) -> List[SemanticChange]:
        """Get all breaking changes"""
        return [c for c in self.changes if c.is_breaking()]
    
    def get_by_severity(self, severity: ChangeSeverity) -> List[SemanticChange]:
        """Get changes by severity"""
        return [c for c in self.changes if c.severity == severity]
    
    def get_by_type(self, change_type: ChangeType) -> List[SemanticChange]:
        """Get changes by type"""
        return [c for c in self.changes if c.change_type == change_type]
    
    def get_affected_symbols(self) -> Set[str]:
        """Get all affected symbols"""
        affected = set()
        for change in self.changes:
            affected.add(change.symbol_id)
            affected.update(change.affected_symbols)
        return affected
    
    def has_breaking_changes(self) -> bool:
        """Check if diff has breaking changes"""
        return any(c.is_breaking() for c in self.changes)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get diff statistics"""
        if self._stats is not None:
            return self._stats
        
        # Count by severity
        severity_counts = {}
        for sev in ChangeSeverity:
            severity_counts[sev.name] = len(self.get_by_severity(sev))
        
        # Count by type
        type_counts = {}
        for change in self.changes:
            type_name = change.change_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
        
        # Breaking changes
        breaking = self.get_breaking_changes()
        
        self._stats = {
            "total_changes": len(self.changes),
            "breaking_changes": len(breaking),
            "affected_symbols": len(self.get_affected_symbols()),
            "severity_distribution": severity_counts,
            "type_distribution": type_counts,
            "has_breaking": self.has_breaking_changes(),
        }
        
        return self._stats
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "changes": [c.to_dict() for c in self.changes],
            "statistics": self.get_statistics(),
        }
    
    def __len__(self) -> int:
        return len(self.changes)
    
    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"SemanticDiff("
            f"{stats['total_changes']} changes, "
            f"{stats['breaking_changes']} breaking)"
        )


@dataclass
class DiffContext:
    """
    Context for semantic diff
    
    Contains information needed for diff analysis
    """
    
    # Old version
    old_ir: Dict[str, Any] = field(default_factory=dict)
    old_call_graph: Optional[Any] = None
    
    # New version
    new_ir: Dict[str, Any] = field(default_factory=dict)
    new_call_graph: Optional[Any] = None
    
    # Configuration
    detect_side_effects: bool = True
    detect_error_paths: bool = True
    detect_reachability: bool = True
    
    def get_old_symbol(self, symbol_id: str) -> Optional[Any]:
        """Get symbol from old version"""
        for ir_doc in self.old_ir.values():
            nodes = getattr(ir_doc, "nodes", [])
            for node in nodes:
                if getattr(node, "id", "") == symbol_id:
                    return node
        return None
    
    def get_new_symbol(self, symbol_id: str) -> Optional[Any]:
        """Get symbol from new version"""
        for ir_doc in self.new_ir.values():
            nodes = getattr(ir_doc, "nodes", [])
            for node in nodes:
                if getattr(node, "id", "") == symbol_id:
                    return node
        return None
    
    def __repr__(self) -> str:
        return (
            f"DiffContext("
            f"old_files={len(self.old_ir)}, "
            f"new_files={len(self.new_ir)})"
        )

