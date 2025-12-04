"""AutoRRF - Automatic Reciprocal Rank Fusion with Query Intent"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import structlog
from .models import QueryIntent, WeightProfile, QueryResult
from .classifier import QueryClassifier

logger = structlog.get_logger(__name__)

@dataclass
class AutoRRF:
    """
    Automatic RRF with query-intent based weight adjustment
    
    Example:
        rrf = AutoRRF()
        results = rrf.search(
            query="이 API 어디서 호출?",
            graph_results=[...],
            embedding_results=[...],
            symbol_results=[...]
        )
    """
    
    classifier: QueryClassifier = field(default_factory=QueryClassifier)
    k: int = 60  # RRF constant
    
    # Feedback learning
    _feedback_history: List[Dict] = field(default_factory=list)
    _learned_adjustments: Dict[QueryIntent, WeightProfile] = field(default_factory=dict)
    
    def search(
        self,
        query: str,
        graph_results: List[str],
        embedding_results: List[str],
        symbol_results: List[str],
    ) -> List[QueryResult]:
        """
        Perform auto-weighted RRF search
        
        Args:
            query: Search query
            graph_results: Results from graph search (ranked)
            embedding_results: Results from embedding search (ranked)
            symbol_results: Results from symbol search (ranked)
        
        Returns:
            Fused and ranked results
        """
        # Step 1: Classify query intent
        intent = self.classifier.classify(query)
        logger.info("query_classified", query=query, intent=intent.value)
        
        # Step 2: Get optimal weights
        weights = self.classifier.get_weights(intent)
        
        # Apply learned adjustments if available
        if intent in self._learned_adjustments:
            adjustment = self._learned_adjustments[intent]
            weights = self._blend_weights(weights, adjustment, alpha=0.7)
        
        # Step 3: Compute RRF scores
        results = self._compute_rrf_scores(
            graph_results,
            embedding_results,
            symbol_results,
            weights
        )
        
        # Step 4: Rank results
        results.sort(key=lambda x: x.final_score, reverse=True)
        for i, result in enumerate(results):
            result.rank = i + 1
        
        logger.info(
            "search_complete",
            intent=intent.value,
            num_results=len(results),
            weights={"graph": weights.graph_weight, "embedding": weights.embedding_weight, "symbol": weights.symbol_weight}
        )
        
        return results
    
    def _compute_rrf_scores(
        self,
        graph_results: List[str],
        embedding_results: List[str],
        symbol_results: List[str],
        weights: WeightProfile,
    ) -> List[QueryResult]:
        """Compute RRF scores with weighted fusion"""
        # Collect all unique items
        all_items = set(graph_results + embedding_results + symbol_results)
        
        results = []
        for item in all_items:
            # Compute individual RRF scores
            graph_score = self._rrf_score(item, graph_results)
            embedding_score = self._rrf_score(item, embedding_results)
            symbol_score = self._rrf_score(item, symbol_results)
            
            # Weighted fusion
            final_score = (
                weights.graph_weight * graph_score +
                weights.embedding_weight * embedding_score +
                weights.symbol_weight * symbol_score
            )
            
            result = QueryResult(
                item_id=item,
                graph_score=graph_score,
                embedding_score=embedding_score,
                symbol_score=symbol_score,
                final_score=final_score,
            )
            results.append(result)
        
        return results
    
    def _rrf_score(self, item: str, ranked_list: List[str]) -> float:
        """Compute RRF score for item in ranked list"""
        if item not in ranked_list:
            return 0.0
        
        rank = ranked_list.index(item) + 1
        return 1.0 / (self.k + rank)
    
    def add_feedback(
        self,
        query: str,
        clicked_result: str,
        results: List[QueryResult],
    ):
        """
        Add user feedback for learning
        
        Args:
            query: Original query
            clicked_result: Which result user clicked
            results: All results shown
        """
        intent = self.classifier.classify(query)
        
        # Find clicked result
        clicked = None
        for r in results:
            if r.item_id == clicked_result:
                clicked = r
                break
        
        if not clicked:
            return
        
        # Record feedback
        feedback = {
            "query": query,
            "intent": intent,
            "clicked_result": clicked_result,
            "clicked_rank": clicked.rank,
            "clicked_scores": {
                "graph": clicked.graph_score,
                "embedding": clicked.embedding_score,
                "symbol": clicked.symbol_score,
            }
        }
        self._feedback_history.append(feedback)
        
        logger.info(
            "feedback_recorded",
            intent=intent.value,
            rank=clicked.rank,
            num_feedback=len(self._feedback_history)
        )
        
        # Learn from feedback (every 10 feedbacks)
        if len(self._feedback_history) >= 10:
            self._update_weights()
    
    def _update_weights(self):
        """Update weights based on feedback"""
        # Group feedback by intent
        by_intent: Dict[QueryIntent, List] = {}
        for feedback in self._feedback_history[-50:]:  # Last 50
            intent = feedback["intent"]
            if intent not in by_intent:
                by_intent[intent] = []
            by_intent[intent].append(feedback)
        
        # Compute optimal weights for each intent
        for intent, feedbacks in by_intent.items():
            if len(feedbacks) < 5:
                continue
            
            # Analyze which method worked best
            graph_success = sum(1 for f in feedbacks if f["clicked_scores"]["graph"] > 0.01)
            embedding_success = sum(1 for f in feedbacks if f["clicked_scores"]["embedding"] > 0.01)
            symbol_success = sum(1 for f in feedbacks if f["clicked_scores"]["symbol"] > 0.01)
            
            total = len(feedbacks)
            
            # Adjust weights based on success rate
            adjusted = WeightProfile(
                graph_weight=graph_success / total,
                embedding_weight=embedding_success / total,
                symbol_weight=symbol_success / total,
            )
            adjusted.normalize()
            
            self._learned_adjustments[intent] = adjusted
            
            logger.info(
                "weights_updated",
                intent=intent.value,
                new_weights={"graph": adjusted.graph_weight, "embedding": adjusted.embedding_weight, "symbol": adjusted.symbol_weight}
            )
    
    def _blend_weights(
        self,
        base: WeightProfile,
        learned: WeightProfile,
        alpha: float = 0.7,
    ) -> WeightProfile:
        """Blend base weights with learned weights"""
        blended = WeightProfile(
            graph_weight=alpha * base.graph_weight + (1 - alpha) * learned.graph_weight,
            embedding_weight=alpha * base.embedding_weight + (1 - alpha) * learned.embedding_weight,
            symbol_weight=alpha * base.symbol_weight + (1 - alpha) * learned.symbol_weight,
        )
        blended.normalize()
        return blended
    
    def get_statistics(self) -> Dict:
        """Get AutoRRF statistics"""
        return {
            "total_feedback": len(self._feedback_history),
            "learned_intents": list(self._learned_adjustments.keys()),
            "num_learned": len(self._learned_adjustments),
        }

