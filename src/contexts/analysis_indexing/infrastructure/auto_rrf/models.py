"""AutoRRF Models"""

from dataclasses import dataclass
from enum import Enum


class QueryIntent(Enum):
    """Query intent types"""

    API_USAGE = "api_usage"  # "어디서 호출?"
    EXPLAIN_LOGIC = "explain_logic"  # "설명해줘"
    REFACTOR_LOCATION = "refactor_location"  # "리팩토링 위치"
    FIND_DEFINITION = "find_definition"  # "정의 찾기"
    TRACE_DATAFLOW = "trace_dataflow"  # "데이터 흐름"
    GENERAL = "general"  # 일반 검색


@dataclass
class WeightProfile:
    """Weight profile for different search methods"""

    graph_weight: float = 0.33
    embedding_weight: float = 0.33
    symbol_weight: float = 0.34

    def normalize(self):
        """Normalize weights to sum to 1.0"""
        total = self.graph_weight + self.embedding_weight + self.symbol_weight
        if total > 0:
            self.graph_weight /= total
            self.embedding_weight /= total
            self.symbol_weight /= total


@dataclass
class QueryResult:
    """Search result with scores"""

    item_id: str
    graph_score: float = 0.0
    embedding_score: float = 0.0
    symbol_score: float = 0.0
    final_score: float = 0.0
    rank: int = 0
