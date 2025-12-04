"""
Impact Models

Data models for impact-based partial graph rebuild.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List
from enum import Enum, auto


class ChangeImpactLevel(Enum):
    """
    Level of impact a code change has on the graph
    
    Determines rebuild scope:
    - NONE: No rebuild needed
    - METADATA: Only metadata update
    - LOCAL: Only local symbol update
    - CFG_DFG: Control/data flow update
    - SIGNATURE: Signature change, rebuild callers
    - STRUCTURAL: Structure change, full rebuild
    """
    
    NONE = auto()  # Comment change, whitespace
    METADATA = auto()  # Documentation, annotations
    LOCAL = auto()  # Variable rename, local logic
    CFG_DFG = auto()  # Control flow, data flow change
    SIGNATURE = auto()  # Function signature, interface change
    STRUCTURAL = auto()  # Class hierarchy, module structure
    
    def __lt__(self, other):
        """Allow comparison of impact levels"""
        if not isinstance(other, ChangeImpactLevel):
            return NotImplemented
        return self.value < other.value
    
    def __le__(self, other):
        if not isinstance(other, ChangeImpactLevel):
            return NotImplemented
        return self.value <= other.value
    
    def __gt__(self, other):
        if not isinstance(other, ChangeImpactLevel):
            return NotImplemented
        return self.value > other.value
    
    def __ge__(self, other):
        if not isinstance(other, ChangeImpactLevel):
            return NotImplemented
        return self.value >= other.value


@dataclass
class ChangeImpact:
    """
    Represents the impact of a code change
    
    Example:
        Change: Rename parameter in function signature
        Impact:
          - Level: SIGNATURE
          - Affected: [caller1, caller2, ...]
          - Rebuild: [function, callers]
          - Reason: "Parameter renamed: old_name -> new_name"
    """
    
    # Identity
    file_path: str
    symbol_id: str  # Changed symbol
    
    # Impact level
    level: ChangeImpactLevel
    
    # Affected symbols
    affected_symbols: Set[str] = field(default_factory=set)
    
    # What needs rebuild
    needs_rebuild: Set[str] = field(default_factory=set)  # Symbol IDs
    
    # Reason for impact
    reason: str = ""
    
    # Detailed change info
    change_type: str = ""  # "parameter_added", "return_type_changed", etc.
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_affected(self, symbol_id: str):
        """Add affected symbol"""
        self.affected_symbols.add(symbol_id)
    
    def add_rebuild_target(self, symbol_id: str):
        """Add symbol that needs rebuild"""
        self.needs_rebuild.add(symbol_id)
    
    def is_breaking_change(self) -> bool:
        """Check if this is a breaking change"""
        return self.level >= ChangeImpactLevel.SIGNATURE
    
    def rebuild_depth(self) -> int:
        """
        Get rebuild depth
        
        Returns:
            0: No rebuild
            1: Local only
            2: Local + callers
            3: Full transitive
        """
        if self.level == ChangeImpactLevel.NONE:
            return 0
        elif self.level in (ChangeImpactLevel.METADATA, ChangeImpactLevel.LOCAL):
            return 1
        elif self.level == ChangeImpactLevel.CFG_DFG:
            return 1  # Local CFG/DFG only
        elif self.level == ChangeImpactLevel.SIGNATURE:
            return 2  # Local + direct callers
        else:  # STRUCTURAL
            return 3  # Full transitive
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "file_path": self.file_path,
            "symbol_id": self.symbol_id,
            "level": self.level.name,
            "affected_symbols": list(self.affected_symbols),
            "needs_rebuild": list(self.needs_rebuild),
            "reason": self.reason,
            "change_type": self.change_type,
            "rebuild_depth": self.rebuild_depth(),
            "is_breaking": self.is_breaking_change(),
        }
    
    def __repr__(self) -> str:
        return (
            f"ChangeImpact("
            f"symbol={self.symbol_id}, "
            f"level={self.level.name}, "
            f"affected={len(self.affected_symbols)}, "
            f"rebuild={len(self.needs_rebuild)})"
        )


@dataclass
class RebuildStrategy:
    """
    Strategy for partial graph rebuild
    
    Determines:
    - What to rebuild
    - How deep to rebuild
    - What to invalidate
    """
    
    # Symbols to rebuild
    rebuild_symbols: Set[str] = field(default_factory=set)
    
    # Depth of rebuild
    max_depth: int = 1  # How many levels of dependents to rebuild
    
    # Invalidate cache
    invalidate_cache: bool = True
    
    # Rebuild specific graph components
    rebuild_cfg: bool = False
    rebuild_dfg: bool = False
    rebuild_call_graph: bool = False
    rebuild_type_graph: bool = False
    
    # Performance optimization
    parallel: bool = True
    batch_size: int = 10
    
    def from_impact(self, impact: ChangeImpact) -> "RebuildStrategy":
        """
        Create rebuild strategy from impact analysis
        
        Args:
            impact: ChangeImpact to build strategy from
        
        Returns:
            RebuildStrategy optimized for the impact level
        """
        strategy = RebuildStrategy()
        
        # Set rebuild targets
        strategy.rebuild_symbols = impact.needs_rebuild.copy()
        
        # Set depth based on impact level
        strategy.max_depth = impact.rebuild_depth()
        
        # Determine what to rebuild
        if impact.level == ChangeImpactLevel.NONE:
            # Nothing to rebuild
            strategy.invalidate_cache = False
        
        elif impact.level == ChangeImpactLevel.METADATA:
            # Only metadata
            strategy.invalidate_cache = False
        
        elif impact.level == ChangeImpactLevel.LOCAL:
            # Local symbol only
            strategy.max_depth = 1
        
        elif impact.level == ChangeImpactLevel.CFG_DFG:
            # Control/data flow
            strategy.rebuild_cfg = True
            strategy.rebuild_dfg = True
            strategy.max_depth = 1
        
        elif impact.level == ChangeImpactLevel.SIGNATURE:
            # Signature change - rebuild callers
            strategy.rebuild_call_graph = True
            strategy.rebuild_type_graph = True
            strategy.max_depth = 2  # Self + direct callers
        
        else:  # STRUCTURAL
            # Full rebuild
            strategy.rebuild_cfg = True
            strategy.rebuild_dfg = True
            strategy.rebuild_call_graph = True
            strategy.rebuild_type_graph = True
            strategy.max_depth = 3  # Full transitive
        
        return strategy
    
    def estimate_cost(self, num_symbols: int) -> Dict[str, Any]:
        """
        Estimate rebuild cost
        
        Returns:
            {
                "rebuild_count": int,
                "estimated_time_ms": float,
                "memory_mb": float,
            }
        """
        rebuild_count = len(self.rebuild_symbols)
        
        # Rough estimates (in real impl, use profiling)
        time_per_symbol_ms = 10.0
        memory_per_symbol_mb = 0.5
        
        # Multiply by depth
        total_rebuild = rebuild_count * self.max_depth
        
        estimated_time = total_rebuild * time_per_symbol_ms
        estimated_memory = total_rebuild * memory_per_symbol_mb
        
        # Parallel speedup
        if self.parallel:
            estimated_time /= 4  # Assume 4 cores
        
        return {
            "rebuild_count": total_rebuild,
            "estimated_time_ms": estimated_time,
            "memory_mb": estimated_memory,
        }
    
    def __repr__(self) -> str:
        components = []
        if self.rebuild_cfg:
            components.append("CFG")
        if self.rebuild_dfg:
            components.append("DFG")
        if self.rebuild_call_graph:
            components.append("CG")
        if self.rebuild_type_graph:
            components.append("TG")
        
        return (
            f"RebuildStrategy("
            f"symbols={len(self.rebuild_symbols)}, "
            f"depth={self.max_depth}, "
            f"components={components})"
        )


@dataclass
class ImpactAnalysisResult:
    """
    Result of impact analysis
    
    Contains:
    - All detected impacts
    - Recommended rebuild strategy
    - Statistics
    """
    
    impacts: List[ChangeImpact] = field(default_factory=list)
    strategy: Optional[RebuildStrategy] = None
    
    def add_impact(self, impact: ChangeImpact):
        """Add impact to results"""
        self.impacts.append(impact)
    
    def get_max_impact_level(self) -> ChangeImpactLevel:
        """Get maximum impact level across all impacts"""
        if not self.impacts:
            return ChangeImpactLevel.NONE
        return max(impact.level for impact in self.impacts)
    
    def get_total_affected(self) -> Set[str]:
        """Get all affected symbols"""
        affected = set()
        for impact in self.impacts:
            affected.update(impact.affected_symbols)
        return affected
    
    def get_total_rebuild_needed(self) -> Set[str]:
        """Get all symbols that need rebuild"""
        rebuild = set()
        for impact in self.impacts:
            rebuild.update(impact.needs_rebuild)
        return rebuild
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get analysis statistics"""
        total_affected = self.get_total_affected()
        total_rebuild = self.get_total_rebuild_needed()
        max_level = self.get_max_impact_level()
        
        # Count by level
        level_counts = {}
        for impact in self.impacts:
            level_name = impact.level.name
            level_counts[level_name] = level_counts.get(level_name, 0) + 1
        
        return {
            "total_impacts": len(self.impacts),
            "total_affected": len(total_affected),
            "total_rebuild": len(total_rebuild),
            "max_level": max_level.name,
            "level_distribution": level_counts,
            "has_breaking_changes": any(i.is_breaking_change() for i in self.impacts),
        }
    
    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"ImpactAnalysisResult("
            f"{stats['total_impacts']} impacts, "
            f"{stats['total_rebuild']} rebuild, "
            f"max_level={stats['max_level']})"
        )

