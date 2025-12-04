"""
Semantic Change Detector

Main entry point for semantic change detection.
"""

from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any, List
import structlog

from .models import SemanticDiff, DiffContext
from .ast_differ import ASTDiffer
from .graph_differ import GraphDiffer

logger = structlog.get_logger(__name__)


@dataclass
class SemanticChangeDetector:
    """
    Detects semantic changes between code versions
    
    Integrates:
    - ASTDiffer (structural changes)
    - GraphDiffer (behavioral changes)
    
    Example:
        detector = SemanticChangeDetector()
        
        context = DiffContext(
            old_ir=old_ir_docs,
            new_ir=new_ir_docs,
            old_call_graph=old_cg,
            new_call_graph=new_cg,
        )
        
        diff = detector.detect(context)
        
        print(f"Changes: {len(diff)}")
        print(f"Breaking: {len(diff.get_breaking_changes())}")
    """
    
    def detect(self, context: DiffContext) -> SemanticDiff:
        """
        Detect all semantic changes
        
        Args:
            context: DiffContext with old and new versions
        
        Returns:
            SemanticDiff with all detected changes
        """
        logger.info(
            "detecting_semantic_changes",
            old_files=len(context.old_ir),
            new_files=len(context.new_ir),
        )
        
        combined_diff = SemanticDiff()
        
        # Step 1: AST-level changes
        ast_diff = self._detect_ast_changes(context)
        for change in ast_diff.changes:
            combined_diff.add_change(change)
        
        # Step 2: Graph-level changes
        graph_diff = self._detect_graph_changes(context)
        for change in graph_diff.changes:
            combined_diff.add_change(change)
        
        stats = combined_diff.get_statistics()
        logger.info(
            "semantic_detection_complete",
            total_changes=stats["total_changes"],
            breaking_changes=stats["breaking_changes"],
        )
        
        return combined_diff
    
    def _detect_ast_changes(self, context: DiffContext) -> SemanticDiff:
        """Detect AST-level changes"""
        differ = ASTDiffer(context)
        combined = SemanticDiff()
        
        # Find common symbols
        old_symbols = self._get_all_symbols(context.old_ir)
        new_symbols = self._get_all_symbols(context.new_ir)
        
        common_symbols = set(old_symbols.keys()) & set(new_symbols.keys())
        
        for symbol_id in common_symbols:
            old_node = old_symbols[symbol_id]
            new_node = new_symbols[symbol_id]
            
            diff = differ.compare_symbols(symbol_id, old_node, new_node)
            for change in diff.changes:
                combined.add_change(change)
        
        return combined
    
    def _detect_graph_changes(self, context: DiffContext) -> SemanticDiff:
        """Detect graph-level changes"""
        differ = GraphDiffer(context)
        combined = SemanticDiff()
        
        # Call graph changes
        cg_diff = differ.compare_call_graphs()
        for change in cg_diff.changes:
            combined.add_change(change)
        
        # Side effects (if enabled)
        if context.detect_side_effects:
            symbols = self._get_all_symbols(context.new_ir)
            for symbol_id in list(symbols.keys())[:5]:  # Sample
                se_diff = differ.detect_side_effects(symbol_id)
                for change in se_diff.changes:
                    combined.add_change(change)
        
        return combined
    
    def _get_all_symbols(self, ir: Dict[str, Any]) -> Dict[str, Any]:
        """Get all symbols from IR"""
        symbols = {}
        
        for ir_doc in ir.values():
            nodes = getattr(ir_doc, "nodes", [])
            for node in nodes:
                node_id = getattr(node, "id", "")
                if node_id:
                    symbols[node_id] = node
        
        return symbols
    
    def predict_breaking_changes(
        self,
        diff: SemanticDiff,
        context: DiffContext,
    ) -> List[Dict[str, Any]]:
        """
        Predict which changes are breaking
        
        Args:
            diff: SemanticDiff to analyze
            context: DiffContext for additional info
        
        Returns:
            List of predictions with confidence scores
        """
        predictions = []
        
        for change in diff.changes:
            if change.is_breaking():
                # High confidence breaking change
                prediction = {
                    "change": change.to_dict(),
                    "is_breaking": True,
                    "confidence": 0.9,
                    "reason": f"{change.change_type.value} is typically breaking",
                }
                predictions.append(prediction)
            
            elif change.severity.value >= 3:  # MODERATE or higher
                # Potential breaking change
                # Check if has callers
                if context.old_call_graph:
                    callers = self._find_callers(
                        change.symbol_id,
                        context.old_call_graph
                    )
                    
                    if callers:
                        prediction = {
                            "change": change.to_dict(),
                            "is_breaking": True,
                            "confidence": 0.6,
                            "reason": f"Has {len(callers)} callers, may break",
                            "affected_callers": list(callers),
                        }
                        predictions.append(prediction)
        
        return predictions
    
    def _find_callers(self, symbol_id: str, call_graph: Any) -> Set[str]:
        """Find callers of a symbol"""
        callers = set()
        
        if not call_graph or not hasattr(call_graph, "edges"):
            return callers
        
        edges = call_graph.edges
        if isinstance(edges, dict):
            for (caller, callee), _ in edges.items():
                if callee == symbol_id:
                    callers.add(caller)
        
        return callers
    
    def __repr__(self) -> str:
        return "SemanticChangeDetector()"

