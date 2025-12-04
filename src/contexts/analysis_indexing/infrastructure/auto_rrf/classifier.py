"""Query Classifier"""
from dataclasses import dataclass
from typing import Dict, List
import structlog
from .models import QueryIntent, WeightProfile

logger = structlog.get_logger(__name__)

@dataclass
class QueryClassifier:
    """Classifies query intent and returns optimal weights"""
    
    # Intent-specific weight profiles
    _profiles: Dict[QueryIntent, WeightProfile] = None
    
    def __post_init__(self):
        """Initialize weight profiles"""
        self._profiles = {
            QueryIntent.API_USAGE: WeightProfile(
                graph_weight=0.6,  # High: call graph important
                embedding_weight=0.2,
                symbol_weight=0.2
            ),
            QueryIntent.EXPLAIN_LOGIC: WeightProfile(
                graph_weight=0.2,
                embedding_weight=0.7,  # High: semantic understanding
                symbol_weight=0.1
            ),
            QueryIntent.REFACTOR_LOCATION: WeightProfile(
                graph_weight=0.3,
                embedding_weight=0.2,
                symbol_weight=0.5  # High: exact match
            ),
            QueryIntent.FIND_DEFINITION: WeightProfile(
                graph_weight=0.2,
                embedding_weight=0.2,
                symbol_weight=0.6  # High: symbol lookup
            ),
            QueryIntent.TRACE_DATAFLOW: WeightProfile(
                graph_weight=0.7,  # High: graph traversal
                embedding_weight=0.2,
                symbol_weight=0.1
            ),
            QueryIntent.GENERAL: WeightProfile(
                graph_weight=0.33,
                embedding_weight=0.34,
                symbol_weight=0.33
            ),
        }
    
    def classify(self, query: str) -> QueryIntent:
        """Classify query intent based on keywords"""
        query_lower = query.lower()
        
        # API usage patterns
        if any(kw in query_lower for kw in ["호출", "call", "usage", "used", "caller"]):
            return QueryIntent.API_USAGE
        
        # Explanation patterns
        if any(kw in query_lower for kw in ["설명", "explain", "what", "how", "why"]):
            return QueryIntent.EXPLAIN_LOGIC
        
        # Refactor patterns
        if any(kw in query_lower for kw in ["리팩토링", "refactor", "move", "extract"]):
            return QueryIntent.REFACTOR_LOCATION
        
        # Definition patterns
        if any(kw in query_lower for kw in ["정의", "definition", "declare", "implement"]):
            return QueryIntent.FIND_DEFINITION
        
        # Dataflow patterns
        if any(kw in query_lower for kw in ["흐름", "flow", "trace", "track"]):
            return QueryIntent.TRACE_DATAFLOW
        
        return QueryIntent.GENERAL
    
    def get_weights(self, intent: QueryIntent) -> WeightProfile:
        """Get weight profile for intent"""
        profile = self._profiles.get(intent, self._profiles[QueryIntent.GENERAL])
        logger.debug("weight_profile_selected", intent=intent.value, profile=profile)
        return profile

