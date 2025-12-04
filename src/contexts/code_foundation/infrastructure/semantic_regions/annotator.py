"""
Semantic Annotator

Adds semantic annotations to regions:
- Type flow analysis
- Control flow analysis
- Dependency tracking
- LLM-friendly descriptions
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List
import structlog

from .models import (
    SemanticRegion,
    RegionCollection,
    TypeFlowInfo,
    ControlFlowInfo,
)

logger = structlog.get_logger(__name__)


@dataclass
class SemanticAnnotator:
    """
    Annotates semantic regions with additional information
    
    Responsibilities:
    1. Type flow analysis
    2. Control flow analysis
    3. Dependency tracking
    4. LLM-friendly descriptions
    
    Example:
        Before annotation:
        Region: calculate_discount (lines 10-20)
        
        After annotation:
        Region: calculate_discount
          - Type Flow: Customer → float
          - Control Flow: branching (3 branches)
          - Depends on: [validate_customer, get_tier]
          - Description: "Calculates discount percentage based on customer tier"
          - Tags: ["discount", "pricing", "customer", "tier"]
    """
    
    # IR docs for cross-reference
    _ir_docs: Dict[str, Any] = field(default_factory=dict)
    
    def annotate_collection(
        self,
        collection: RegionCollection,
        ir_docs: Dict[str, Any],
    ) -> RegionCollection:
        """
        Annotate all regions in collection
        
        Args:
            collection: RegionCollection to annotate
            ir_docs: IR documents for cross-reference
        
        Returns:
            Annotated RegionCollection (same object, modified in-place)
        """
        logger.info("annotating_collection", num_regions=len(collection))
        
        self._ir_docs = ir_docs
        
        # Annotate each region
        for region in collection.regions:
            self._annotate_region(region)
        
        # Build dependencies between regions
        self._build_dependencies(collection)
        
        logger.info("annotation_complete", num_regions=len(collection))
        
        return collection
    
    def _annotate_region(self, region: SemanticRegion):
        """
        Annotate a single region
        """
        # Get IR for this file
        ir_doc = self._ir_docs.get(region.file_path)
        if not ir_doc:
            logger.warning("no_ir_for_file", file_path=region.file_path)
            return
        
        # Enhance type flow
        self._annotate_type_flow(region, ir_doc)
        
        # Enhance control flow
        self._annotate_control_flow(region, ir_doc)
        
        # Generate LLM-friendly description
        self._generate_description(region)
        
        logger.debug(
            "region_annotated",
            region_id=region.region_id,
            type_flow=str(region.type_flow),
            control_flow=str(region.control_flow),
        )
    
    def _annotate_type_flow(self, region: SemanticRegion, ir_doc: Any):
        """
        Annotate type flow information
        
        Extracts:
        - Input types (parameters)
        - Output types (return values)
        - Type transformations
        """
        # Get the primary symbol
        if not region.primary_symbol:
            return
        
        # Find symbol in IR
        nodes = getattr(ir_doc, "nodes", [])
        target_node = None
        for node in nodes:
            if getattr(node, "id", "") == region.primary_symbol:
                target_node = node
                break
        
        if not target_node:
            return
        
        # Extract type info from signature
        signature = getattr(target_node, "signature", "")
        
        # Simple extraction (in real impl, parse signature properly)
        # For now, use heuristics
        
        # Extract parameter types (simplified)
        if "(" in signature and ")" in signature:
            params_part = signature[signature.find("(") + 1:signature.find(")")]
            
            # Look for type hints
            for param in params_part.split(","):
                param = param.strip()
                if ":" in param:
                    # Has type hint
                    _, type_hint = param.split(":", 1)
                    type_hint = type_hint.strip().split("=")[0].strip()  # Remove default
                    region.type_flow.input_types.add(type_hint)
        
        # Extract return type (simplified)
        if "->" in signature:
            return_part = signature.split("->")[-1].strip()
            region.type_flow.output_types.add(return_part)
    
    def _annotate_control_flow(self, region: SemanticRegion, ir_doc: Any):
        """
        Annotate control flow information
        
        Analyzes:
        - Branching
        - Loops
        - Early exits
        - Cyclomatic complexity
        """
        # Get edges from region symbols
        edges = getattr(ir_doc, "edges", [])
        
        # Count control flow edges involving region symbols
        branch_count = 0
        loop_count = 0
        
        for edge in edges:
            edge_type = getattr(edge, "type", "")
            source = getattr(edge, "source", "")
            
            if source not in region.symbols:
                continue
            
            # Check for control flow patterns
            if edge_type in ("CALLS", "FLOWS_TO"):
                # Simple heuristic: more edges = more branching
                branch_count += 1
        
        # Update control flow info
        if branch_count > 2:
            region.control_flow.has_branching = True
            region.control_flow.complexity_score = min(branch_count, 10)
    
    def _generate_description(self, region: SemanticRegion):
        """
        Generate LLM-friendly description
        
        Creates a natural language description based on:
        - Region type
        - Purpose
        - Semantic tags
        """
        # Build description parts
        parts = []
        
        # Start with purpose
        purpose_str = region.purpose.value.replace("_", " ").title()
        parts.append(purpose_str)
        
        # Add region type context
        if region.region_type.value == "function_body":
            parts.append("function")
        elif region.region_type.value == "class_def":
            parts.append("class")
        
        # Add main tags
        if len(region.semantic_tags) > 0:
            top_tags = region.semantic_tags[:3]  # Top 3 tags
            parts.append(f"related to {', '.join(top_tags)}")
        
        # Construct description
        description = f"{parts[0]}"
        if len(parts) > 1:
            description += f" - {' '.join(parts[1:])}"
        
        region.description = description
        
        # Construct responsibility
        if region.primary_symbol:
            symbol_name = region.primary_symbol.split("/")[-1]  # Get last part
            region.responsibility = f"Implements {symbol_name} logic"
    
    def _build_dependencies(self, collection: RegionCollection):
        """
        Build dependency graph between regions
        
        A region depends on another if:
        - It calls symbols in that region
        - It references symbols in that region
        """
        # For each region, find dependencies
        for region in collection.regions:
            # Get IR for this file
            ir_doc = self._ir_docs.get(region.file_path)
            if not ir_doc:
                continue
            
            # Get edges from region symbols
            edges = getattr(ir_doc, "edges", [])
            
            for edge in edges:
                edge_type = getattr(edge, "type", "")
                source = getattr(edge, "source", "")
                target = getattr(edge, "target", "")
                
                # If source is in this region
                if source in region.symbols:
                    # Find which region contains target
                    for other_region in collection.regions:
                        if other_region.region_id == region.region_id:
                            continue
                        
                        if target in other_region.symbols:
                            # Add dependency
                            region.add_dependency(other_region.region_id)
                            other_region.depended_by.add(region.region_id)
                            
                            logger.debug(
                                "dependency_found",
                                from_region=region.region_id,
                                to_region=other_region.region_id,
                            )
        
        # Log dependency statistics
        total_deps = sum(len(r.depends_on) for r in collection.regions)
        logger.info(
            "dependencies_built",
            total_dependencies=total_deps,
            avg_per_region=total_deps / len(collection) if collection else 0,
        )
    
    def __repr__(self) -> str:
        return f"SemanticAnnotator(cached_irs={len(self._ir_docs)})"

