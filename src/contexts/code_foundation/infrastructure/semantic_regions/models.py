"""
Semantic Region Models

Data models for semantic region indexing.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List
from enum import Enum


class RegionType(Enum):
    """Type of semantic region"""
    
    FUNCTION_BODY = "function_body"
    CLASS_DEF = "class_def"
    CONTROL_BLOCK = "control_block"  # if/else/for/while
    ERROR_HANDLING = "error_handling"  # try/catch
    INITIALIZATION = "initialization"
    COMPUTATION = "computation"
    IO_OPERATION = "io_operation"
    API_CALL = "api_call"
    DATA_TRANSFORM = "data_transform"
    VALIDATION = "validation"


class RegionPurpose(Enum):
    """Purpose/responsibility of region"""
    
    INPUT_PROCESSING = "input_processing"
    BUSINESS_LOGIC = "business_logic"
    DATA_ACCESS = "data_access"
    ERROR_RECOVERY = "error_recovery"
    LOGGING = "logging"
    CACHING = "caching"
    VALIDATION_CHECK = "validation_check"
    TRANSFORMATION = "transformation"
    AGGREGATION = "aggregation"
    FILTERING = "filtering"


@dataclass
class TypeFlowInfo:
    """
    Type flow information for a region
    
    Tracks:
    - Input types
    - Output types
    - Type transformations
    """
    
    input_types: Set[str] = field(default_factory=set)
    output_types: Set[str] = field(default_factory=set)
    type_transforms: List[tuple[str, str]] = field(default_factory=list)  # (from_type, to_type)
    
    def add_transform(self, from_type: str, to_type: str):
        """Add type transformation"""
        self.type_transforms.append((from_type, to_type))
    
    def __repr__(self) -> str:
        return (
            f"TypeFlow("
            f"in={len(self.input_types)}, "
            f"out={len(self.output_types)}, "
            f"transforms={len(self.type_transforms)})"
        )


@dataclass
class ControlFlowInfo:
    """
    Control flow information for a region
    
    Tracks:
    - Branching conditions
    - Loop structures
    - Early returns/exits
    """
    
    has_branching: bool = False
    has_loops: bool = False
    has_early_exit: bool = False
    branch_conditions: List[str] = field(default_factory=list)
    complexity_score: int = 1  # Cyclomatic complexity
    
    def __repr__(self) -> str:
        return (
            f"ControlFlow("
            f"branch={self.has_branching}, "
            f"loop={self.has_loops}, "
            f"exit={self.has_early_exit}, "
            f"complexity={self.complexity_score})"
        )


@dataclass
class SemanticRegion:
    """
    A semantic region represents a meaningful unit of code
    
    Example:
        File: discount_calculator.py
        Region 1:
          - Type: FUNCTION_BODY
          - Purpose: BUSINESS_LOGIC
          - Description: "Calculate discount based on customer tier"
          - Symbols: [calculate_discount, apply_tier_discount]
          - Type Flow: Customer → float
          - Control Flow: branching (if-else for tiers)
        
        Region 2:
          - Type: VALIDATION
          - Purpose: VALIDATION_CHECK
          - Description: "Validate discount percentage"
          - Symbols: [validate_percentage]
          - Type Flow: float → bool
          - Control Flow: simple (no branching)
    """
    
    # Identity
    region_id: str  # Unique ID
    file_path: str
    start_line: int
    end_line: int
    
    # Classification
    region_type: RegionType
    purpose: RegionPurpose
    
    # Semantic info
    description: str  # Natural language description
    responsibility: str  # What this region is responsible for
    
    # Symbols
    symbols: Set[str] = field(default_factory=set)  # Symbol IDs in this region
    primary_symbol: Optional[str] = None  # Main symbol (e.g., function name)
    
    # Type & Control Flow
    type_flow: TypeFlowInfo = field(default_factory=TypeFlowInfo)
    control_flow: ControlFlowInfo = field(default_factory=ControlFlowInfo)
    
    # Dependencies
    depends_on: Set[str] = field(default_factory=set)  # Other region IDs
    depended_by: Set[str] = field(default_factory=set)  # Other region IDs
    
    # Tags for LLM
    semantic_tags: List[str] = field(default_factory=list)  # ["discount", "pricing", "calculation"]
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate region"""
        if self.start_line > self.end_line:
            raise ValueError(f"Invalid region: start_line > end_line")
    
    @property
    def line_count(self) -> int:
        """Number of lines in region"""
        return self.end_line - self.start_line + 1
    
    @property
    def complexity(self) -> int:
        """Estimated complexity"""
        return self.control_flow.complexity_score
    
    def add_tag(self, tag: str):
        """Add semantic tag"""
        if tag not in self.semantic_tags:
            self.semantic_tags.append(tag)
    
    def add_symbol(self, symbol_id: str):
        """Add symbol to region"""
        self.symbols.add(symbol_id)
    
    def add_dependency(self, region_id: str):
        """Add dependency on another region"""
        self.depends_on.add(region_id)
    
    def matches_query(self, query_tags: Set[str]) -> bool:
        """Check if region matches query tags"""
        region_tag_set = set(self.semantic_tags)
        return bool(query_tags & region_tag_set)
    
    def similarity_score(self, query_tags: Set[str]) -> float:
        """Compute similarity score with query tags"""
        if not query_tags or not self.semantic_tags:
            return 0.0
        
        region_tag_set = set(self.semantic_tags)
        intersection = query_tags & region_tag_set
        union = query_tags | region_tag_set
        
        # Jaccard similarity
        return len(intersection) / len(union) if union else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "region_id": self.region_id,
            "file_path": self.file_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "line_count": self.line_count,
            "region_type": self.region_type.value,
            "purpose": self.purpose.value,
            "description": self.description,
            "responsibility": self.responsibility,
            "symbols": list(self.symbols),
            "primary_symbol": self.primary_symbol,
            "type_flow": {
                "input_types": list(self.type_flow.input_types),
                "output_types": list(self.type_flow.output_types),
                "transforms": self.type_flow.type_transforms,
            },
            "control_flow": {
                "has_branching": self.control_flow.has_branching,
                "has_loops": self.control_flow.has_loops,
                "has_early_exit": self.control_flow.has_early_exit,
                "complexity": self.control_flow.complexity_score,
            },
            "semantic_tags": self.semantic_tags,
            "depends_on": list(self.depends_on),
            "depended_by": list(self.depended_by),
            "metadata": self.metadata,
        }
    
    def __repr__(self) -> str:
        return (
            f"SemanticRegion("
            f"id={self.region_id}, "
            f"type={self.region_type.value}, "
            f"lines={self.line_count}, "
            f"symbols={len(self.symbols)}, "
            f"tags={len(self.semantic_tags)})"
        )


@dataclass
class RegionCollection:
    """
    Collection of semantic regions for a file or project
    """
    
    regions: List[SemanticRegion] = field(default_factory=list)
    
    # Index by region_id
    _index: Dict[str, SemanticRegion] = field(default_factory=dict)
    
    # Index by file
    _file_index: Dict[str, List[str]] = field(default_factory=dict)
    
    # Index by tags
    _tag_index: Dict[str, Set[str]] = field(default_factory=dict)
    
    def add_region(self, region: SemanticRegion):
        """Add region to collection"""
        self.regions.append(region)
        self._index[region.region_id] = region
        
        # Update file index
        if region.file_path not in self._file_index:
            self._file_index[region.file_path] = []
        self._file_index[region.file_path].append(region.region_id)
        
        # Update tag index
        for tag in region.semantic_tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = set()
            self._tag_index[tag].add(region.region_id)
    
    def get_region(self, region_id: str) -> Optional[SemanticRegion]:
        """Get region by ID"""
        return self._index.get(region_id)
    
    def get_regions_by_file(self, file_path: str) -> List[SemanticRegion]:
        """Get all regions in a file"""
        region_ids = self._file_index.get(file_path, [])
        return [self._index[rid] for rid in region_ids]
    
    def search_by_tags(self, tags: Set[str], min_score: float = 0.3) -> List[SemanticRegion]:
        """Search regions by tags"""
        # Find candidate regions (regions with any matching tag)
        candidates = set()
        for tag in tags:
            if tag in self._tag_index:
                candidates.update(self._tag_index[tag])
        
        # Score and filter
        results = []
        for region_id in candidates:
            region = self._index[region_id]
            score = region.similarity_score(tags)
            if score >= min_score:
                results.append((region, score))
        
        # Sort by score (descending)
        results.sort(key=lambda x: x[1], reverse=True)
        
        return [region for region, _ in results]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get collection statistics"""
        total_lines = sum(r.line_count for r in self.regions)
        avg_complexity = (
            sum(r.complexity for r in self.regions) / len(self.regions)
            if self.regions
            else 0
        )
        
        # Count by type
        type_counts = {}
        for region in self.regions:
            region_type = region.region_type.value
            type_counts[region_type] = type_counts.get(region_type, 0) + 1
        
        # Count by purpose
        purpose_counts = {}
        for region in self.regions:
            purpose = region.purpose.value
            purpose_counts[purpose] = purpose_counts.get(purpose, 0) + 1
        
        return {
            "total_regions": len(self.regions),
            "total_files": len(self._file_index),
            "total_lines": total_lines,
            "avg_lines_per_region": total_lines / len(self.regions) if self.regions else 0,
            "avg_complexity": avg_complexity,
            "type_distribution": type_counts,
            "purpose_distribution": purpose_counts,
            "total_tags": len(self._tag_index),
        }
    
    def __len__(self) -> int:
        return len(self.regions)
    
    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"RegionCollection("
            f"{stats['total_regions']} regions, "
            f"{stats['total_files']} files, "
            f"{stats['total_tags']} tags)"
        )

