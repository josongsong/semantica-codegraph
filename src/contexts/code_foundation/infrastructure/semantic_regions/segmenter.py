"""
Region Segmenter

Segments code into semantic regions based on:
- Function/method boundaries
- Control flow blocks
- Logical groupings
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List
from pathlib import Path
import hashlib
import structlog

from .models import (
    SemanticRegion,
    RegionType,
    RegionPurpose,
    TypeFlowInfo,
    ControlFlowInfo,
    RegionCollection,
)

logger = structlog.get_logger(__name__)


@dataclass
class RegionSegmenter:
    """
    Segments code into semantic regions
    
    Strategy:
    1. Function-level segmentation (primary)
    2. Control-flow segmentation (secondary)
    3. Logical-block segmentation (tertiary)
    
    Example:
        def calculate_discount(customer):
            # Region 1: Validation
            if not customer:
                raise ValueError()
            
            # Region 2: Business Logic
            tier = customer.tier
            if tier == "gold":
                return 0.20
            elif tier == "silver":
                return 0.10
            return 0.05
        
        → Segments into 2 regions:
          1. Validation block (lines 2-3)
          2. Business logic (lines 5-10)
    """
    
    # Configuration
    min_region_lines: int = 3  # Minimum lines for a region
    max_region_lines: int = 50  # Maximum lines before splitting
    
    def segment_ir_document(
        self,
        ir_doc: Any,
        file_path: str,
    ) -> RegionCollection:
        """
        Segment IR document into semantic regions
        
        Args:
            ir_doc: IR document to segment
            file_path: Path to source file
        
        Returns:
            RegionCollection with all discovered regions
        """
        logger.info("segmenting_file", file_path=file_path)
        
        collection = RegionCollection()
        
        # Get nodes (symbols) from IR
        nodes = getattr(ir_doc, "nodes", []) if hasattr(ir_doc, "nodes") else []
        
        # Segment by functions/classes
        for node in nodes:
            node_type = getattr(node, "type", "")
            
            # Function-level segmentation
            if node_type in ("function", "method", "class"):
                region = self._segment_function_or_class(node, file_path)
                if region:
                    collection.add_region(region)
        
        logger.info(
            "segmentation_complete",
            file_path=file_path,
            num_regions=len(collection),
        )
        
        return collection
    
    def _segment_function_or_class(
        self,
        node: Any,
        file_path: str,
    ) -> Optional[SemanticRegion]:
        """
        Segment a function or class node into a region
        """
        node_type = getattr(node, "type", "")
        node_id = getattr(node, "id", "")
        node_name = getattr(node, "name", "unknown")
        
        # Get location
        location = getattr(node, "location", None)
        if not location:
            logger.warning("no_location", node_id=node_id)
            return None
        
        start_line = getattr(location, "start_line", 0)
        end_line = getattr(location, "end_line", 0)
        
        # Check size
        line_count = end_line - start_line + 1
        if line_count < self.min_region_lines:
            logger.debug("region_too_small", node_id=node_id, lines=line_count)
            return None
        
        # Determine region type and purpose
        if node_type == "class":
            region_type = RegionType.CLASS_DEF
            purpose = RegionPurpose.BUSINESS_LOGIC
        else:
            region_type = RegionType.FUNCTION_BODY
            purpose = self._infer_purpose(node)
        
        # Create region
        region_id = self._generate_region_id(file_path, start_line, end_line)
        
        region = SemanticRegion(
            region_id=region_id,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            region_type=region_type,
            purpose=purpose,
            description=f"{node_type.capitalize()}: {node_name}",
            responsibility=f"Handles {node_name} logic",
            primary_symbol=node_id,
        )
        
        # Add symbol
        region.add_symbol(node_id)
        
        # Analyze control flow
        region.control_flow = self._analyze_control_flow(node)
        
        # Extract semantic tags from name
        tags = self._extract_tags_from_name(node_name)
        for tag in tags:
            region.add_tag(tag)
        
        logger.debug(
            "region_created",
            region_id=region_id,
            node_name=node_name,
            lines=line_count,
            tags=len(tags),
        )
        
        return region
    
    def _infer_purpose(self, node: Any) -> RegionPurpose:
        """
        Infer purpose from node name and structure
        
        Heuristics:
        - validate_* → VALIDATION_CHECK
        - get_*, fetch_*, load_* → DATA_ACCESS
        - process_*, compute_*, calculate_* → BUSINESS_LOGIC
        - log_*, track_* → LOGGING
        - cache_* → CACHING
        """
        node_name = getattr(node, "name", "").lower()
        
        if any(prefix in node_name for prefix in ["validate", "check", "verify"]):
            return RegionPurpose.VALIDATION_CHECK
        
        if any(prefix in node_name for prefix in ["get", "fetch", "load", "read", "query"]):
            return RegionPurpose.DATA_ACCESS
        
        if any(prefix in node_name for prefix in ["log", "track", "record"]):
            return RegionPurpose.LOGGING
        
        if any(prefix in node_name for prefix in ["cache"]):
            return RegionPurpose.CACHING
        
        if any(prefix in node_name for prefix in ["transform", "convert", "map"]):
            return RegionPurpose.TRANSFORMATION
        
        if any(prefix in node_name for prefix in ["filter", "select"]):
            return RegionPurpose.FILTERING
        
        if any(prefix in node_name for prefix in ["aggregate", "sum", "count"]):
            return RegionPurpose.AGGREGATION
        
        # Default
        return RegionPurpose.BUSINESS_LOGIC
    
    def _analyze_control_flow(self, node: Any) -> ControlFlowInfo:
        """
        Analyze control flow of a node
        
        Looks for:
        - Branching (if/else)
        - Loops (for/while)
        - Early exits (return/break/continue)
        """
        cf_info = ControlFlowInfo()
        
        # Get signature or body (simplified check)
        signature = getattr(node, "signature", "")
        
        # Simple heuristics based on signature/name
        # In a real implementation, would parse AST
        
        # Check for common patterns (simplified)
        node_name = getattr(node, "name", "")
        
        # Assume simple functions have low complexity
        cf_info.complexity_score = 1
        
        # If name suggests complexity, increase
        if "process" in node_name.lower() or "handle" in node_name.lower():
            cf_info.has_branching = True
            cf_info.complexity_score = 3
        
        return cf_info
    
    def _extract_tags_from_name(self, name: str) -> List[str]:
        """
        Extract semantic tags from symbol name
        
        Examples:
        - calculate_discount → ["calculate", "discount"]
        - validateUserInput → ["validate", "user", "input"]
        - get_order_by_id → ["get", "order", "by", "id"]
        """
        tags = []
        
        # Split on underscores
        parts = name.replace("_", " ").split()
        
        # Split on camelCase
        import re
        camel_parts = []
        for part in parts:
            camel_parts.extend(re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', part))
        
        # Add all parts as tags (lowercased)
        for part in camel_parts:
            tag = part.lower()
            if len(tag) > 2:  # Skip very short tags
                tags.append(tag)
        
        return tags
    
    def _generate_region_id(
        self,
        file_path: str,
        start_line: int,
        end_line: int,
    ) -> str:
        """Generate unique region ID"""
        content = f"{file_path}:{start_line}:{end_line}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:12]
        return f"region_{hash_val}"
    
    def segment_multiple_files(
        self,
        ir_docs: Dict[str, Any],
    ) -> RegionCollection:
        """
        Segment multiple IR documents
        
        Returns a single RegionCollection with all regions
        """
        logger.info("segmenting_multiple_files", num_files=len(ir_docs))
        
        combined = RegionCollection()
        
        for file_path, ir_doc in ir_docs.items():
            file_regions = self.segment_ir_document(ir_doc, file_path)
            
            # Merge into combined collection
            for region in file_regions.regions:
                combined.add_region(region)
        
        logger.info(
            "multi_file_segmentation_complete",
            num_files=len(ir_docs),
            total_regions=len(combined),
        )
        
        return combined
    
    def __repr__(self) -> str:
        return (
            f"RegionSegmenter("
            f"min_lines={self.min_region_lines}, "
            f"max_lines={self.max_region_lines})"
        )

