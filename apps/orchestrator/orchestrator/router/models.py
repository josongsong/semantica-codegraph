"""Router 데이터 모델

Intent 분류 및 Router 관련 데이터 구조 정의
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Intent(Enum):
    """사용자 의도 분류"""

    FIX_BUG = "fix_bug"
    ADD_FEATURE = "add_feature"
    REFACTOR = "refactor"
    EXPLAIN_CODE = "explain_code"
    REVIEW_CODE = "review_code"
    UNKNOWN = "unknown"


@dataclass
class IntentResult:
    """Intent 분류 결과"""

    intent: Intent
    confidence: float  # 0.0 ~ 1.0
    reasoning: str
    context: dict[str, Any]
