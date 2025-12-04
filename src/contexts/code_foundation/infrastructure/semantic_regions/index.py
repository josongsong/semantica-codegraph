"""
Region Index

Fast search and retrieval of semantic regions for LLM augmentation.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List, Tuple
import structlog

from .models import SemanticRegion, RegionCollection, RegionType, RegionPurpose

logger = structlog.get_logger(__name__)


@dataclass
class SearchQuery:
    """
    Search query for regions
    """
    
    # Text-based search
    tags: Set[str] = field(default_factory=set)
    keywords: List[str] = field(default_factory=list)
    
    # Filter criteria
    region_types: Set[RegionType] = field(default_factory=set)
    purposes: Set[RegionPurpose] = field(default_factory=set)
    files: Set[str] = field(default_factory=set)
    
    # Complexity filter
    min_complexity: Optional[int] = None
    max_complexity: Optional[int] = None
    
    # Size filter
    min_lines: Optional[int] = None
    max_lines: Optional[int] = None
    
    def matches_region(self, region: SemanticRegion) -> bool:
        """Check if region matches query filters"""
        # Type filter
        if self.region_types and region.region_type not in self.region_types:
            return False
        
        # Purpose filter
        if self.purposes and region.purpose not in self.purposes:
            return False
        
        # File filter
        if self.files and region.file_path not in self.files:
            return False
        
        # Complexity filter
        if self.min_complexity is not None and region.complexity < self.min_complexity:
            return False
        if self.max_complexity is not None and region.complexity > self.max_complexity:
            return False
        
        # Size filter
        if self.min_lines is not None and region.line_count < self.min_lines:
            return False
        if self.max_lines is not None and region.line_count > self.max_lines:
            return False
        
        return True


@dataclass
class SearchResult:
    """
    Search result with scoring
    """
    
    region: SemanticRegion
    score: float
    match_reasons: List[str] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return (
            f"SearchResult("
            f"region={self.region.region_id}, "
            f"score={self.score:.2f}, "
            f"reasons={len(self.match_reasons)})"
        )


@dataclass
class RegionIndex:
    """
    Fast index for semantic region search
    
    Supports:
    1. Tag-based search
    2. Symbol-based search
    3. Type/Purpose filtering
    4. Multi-criteria ranking
    
    Example:
        index = RegionIndex(collection)
        
        # Search for discount calculation regions
        results = index.search(
            tags={"discount", "calculate"},
            purposes={RegionPurpose.BUSINESS_LOGIC},
            top_k=5
        )
        
        for result in results:
            print(f"{result.region.description}: {result.score}")
    """
    
    collection: RegionCollection
    
    # Indexes
    _tag_index: Dict[str, Set[str]] = field(default_factory=dict)  # tag → region_ids
    _symbol_index: Dict[str, Set[str]] = field(default_factory=dict)  # symbol → region_ids
    _type_index: Dict[RegionType, Set[str]] = field(default_factory=dict)
    _purpose_index: Dict[RegionPurpose, Set[str]] = field(default_factory=dict)
    
    def __post_init__(self):
        """Build indexes"""
        self._build_indexes()
    
    def _build_indexes(self):
        """Build all indexes"""
        logger.info("building_region_indexes", num_regions=len(self.collection))
        
        for region in self.collection.regions:
            region_id = region.region_id
            
            # Tag index
            for tag in region.semantic_tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(region_id)
            
            # Symbol index
            for symbol in region.symbols:
                if symbol not in self._symbol_index:
                    self._symbol_index[symbol] = set()
                self._symbol_index[symbol].add(region_id)
            
            # Type index
            if region.region_type not in self._type_index:
                self._type_index[region.region_type] = set()
            self._type_index[region.region_type].add(region_id)
            
            # Purpose index
            if region.purpose not in self._purpose_index:
                self._purpose_index[region.purpose] = set()
            self._purpose_index[region.purpose].add(region_id)
        
        logger.info(
            "indexes_built",
            num_tags=len(self._tag_index),
            num_symbols=len(self._symbol_index),
            num_types=len(self._type_index),
            num_purposes=len(self._purpose_index),
        )
    
    def search(
        self,
        query: Optional[SearchQuery] = None,
        tags: Optional[Set[str]] = None,
        symbols: Optional[Set[str]] = None,
        top_k: int = 10,
    ) -> List[SearchResult]:
        """
        Search for regions
        
        Args:
            query: SearchQuery object (if provided, tags/symbols ignored)
            tags: Tags to search for (if query not provided)
            symbols: Symbols to search for (if query not provided)
            top_k: Number of results to return
        
        Returns:
            List of SearchResult, sorted by score (descending)
        """
        # Create query if not provided
        if query is None:
            query = SearchQuery(
                tags=tags or set(),
            )
            if symbols:
                # Add symbols as a separate search dimension
                pass
        
        # Find candidate regions
        candidates = self._find_candidates(query, symbols)
        
        # Score candidates
        results = []
        for region_id in candidates:
            region = self.collection.get_region(region_id)
            if not region:
                continue
            
            # Apply filters
            if not query.matches_region(region):
                continue
            
            # Compute score
            score, reasons = self._score_region(region, query, symbols)
            
            if score > 0:
                results.append(SearchResult(
                    region=region,
                    score=score,
                    match_reasons=reasons,
                ))
        
        # Sort by score (descending)
        results.sort(key=lambda x: x.score, reverse=True)
        
        # Return top k
        return results[:top_k]
    
    def _find_candidates(
        self,
        query: SearchQuery,
        symbols: Optional[Set[str]] = None,
    ) -> Set[str]:
        """
        Find candidate regions based on query
        """
        candidates = set()
        
        # Search by tags
        if query.tags:
            for tag in query.tags:
                if tag in self._tag_index:
                    candidates.update(self._tag_index[tag])
        
        # Search by symbols
        if symbols:
            for symbol in symbols:
                if symbol in self._symbol_index:
                    candidates.update(self._symbol_index[symbol])
        
        # If no candidates yet, use type/purpose filters
        if not candidates:
            if query.region_types:
                for region_type in query.region_types:
                    if region_type in self._type_index:
                        candidates.update(self._type_index[region_type])
            
            if query.purposes:
                for purpose in query.purposes:
                    if purpose in self._purpose_index:
                        candidates.update(self._purpose_index[purpose])
        
        # If still no candidates, return all
        if not candidates:
            candidates = set(r.region_id for r in self.collection.regions)
        
        return candidates
    
    def _score_region(
        self,
        region: SemanticRegion,
        query: SearchQuery,
        symbols: Optional[Set[str]] = None,
    ) -> Tuple[float, List[str]]:
        """
        Score a region based on query
        
        Returns:
            (score, list of match reasons)
        """
        score = 0.0
        reasons = []
        
        # Tag matching (Jaccard similarity)
        if query.tags:
            tag_score = region.similarity_score(query.tags)
            if tag_score > 0:
                score += tag_score * 10  # Weight: 10
                reasons.append(f"Tag match: {tag_score:.2f}")
        
        # Symbol matching (exact match)
        if symbols:
            matching_symbols = region.symbols & symbols
            if matching_symbols:
                symbol_score = len(matching_symbols) / len(symbols)
                score += symbol_score * 20  # Weight: 20
                reasons.append(f"Symbol match: {len(matching_symbols)}/{len(symbols)}")
        
        # Type matching (exact)
        if query.region_types and region.region_type in query.region_types:
            score += 5
            reasons.append(f"Type: {region.region_type.value}")
        
        # Purpose matching (exact)
        if query.purposes and region.purpose in query.purposes:
            score += 5
            reasons.append(f"Purpose: {region.purpose.value}")
        
        # Keyword matching (in description)
        if query.keywords:
            desc_lower = region.description.lower()
            matching_keywords = [kw for kw in query.keywords if kw.lower() in desc_lower]
            if matching_keywords:
                keyword_score = len(matching_keywords) / len(query.keywords)
                score += keyword_score * 8  # Weight: 8
                reasons.append(f"Keywords: {len(matching_keywords)}/{len(query.keywords)}")
        
        # Boost for primary symbol
        if region.primary_symbol:
            score += 2
        
        # Boost for rich annotations
        if len(region.semantic_tags) > 5:
            score += 1
        
        return score, reasons
    
    def get_related_regions(
        self,
        region_id: str,
        max_results: int = 5,
    ) -> List[SearchResult]:
        """
        Get regions related to given region
        
        Returns regions that:
        - Have similar tags
        - Are dependencies or dependents
        - Have similar purpose
        """
        region = self.collection.get_region(region_id)
        if not region:
            return []
        
        # Build query from region
        query = SearchQuery(
            tags=set(region.semantic_tags),
            purposes={region.purpose},
        )
        
        # Search
        results = self.search(query=query, top_k=max_results + 1)
        
        # Filter out the query region itself
        results = [r for r in results if r.region.region_id != region_id]
        
        return results[:max_results]
    
    def get_by_symbol(self, symbol_id: str) -> List[SemanticRegion]:
        """Get regions containing a symbol"""
        region_ids = self._symbol_index.get(symbol_id, set())
        return [self.collection.get_region(rid) for rid in region_ids if self.collection.get_region(rid)]
    
    def get_by_type(self, region_type: RegionType) -> List[SemanticRegion]:
        """Get regions by type"""
        region_ids = self._type_index.get(region_type, set())
        return [self.collection.get_region(rid) for rid in region_ids if self.collection.get_region(rid)]
    
    def get_by_purpose(self, purpose: RegionPurpose) -> List[SemanticRegion]:
        """Get regions by purpose"""
        region_ids = self._purpose_index.get(purpose, set())
        return [self.collection.get_region(rid) for rid in region_ids if self.collection.get_region(rid)]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get index statistics"""
        return {
            "total_regions": len(self.collection),
            "indexed_tags": len(self._tag_index),
            "indexed_symbols": len(self._symbol_index),
            "region_types": len(self._type_index),
            "purposes": len(self._purpose_index),
            "collection_stats": self.collection.get_statistics(),
        }
    
    def __repr__(self) -> str:
        stats = self.get_statistics()
        return (
            f"RegionIndex("
            f"{stats['total_regions']} regions, "
            f"{stats['indexed_tags']} tags, "
            f"{stats['indexed_symbols']} symbols)"
        )

