"""
RFC-037 Phase 1: Tier Planning Enums

Enums for agent intent, query type, and scope.
"""

from enum import Enum


class AgentIntent(str, Enum):
    """
    AI agent's intended action.

    Used by TierPlanner to determine required semantic tier.
    """

    # Navigation & Understanding (BASE tier)
    UNDERSTAND = "understand"  # "이 함수 이해해줘"
    FIND_CALLERS = "find_callers"  # "어디서 호출됨?"
    FIND_REFERENCES = "find_references"  # "어디서 사용됨?"

    # Refactoring (EXTENDED tier)
    RENAME = "rename"  # "이름 바꿔도 돼?"
    EXTRACT_METHOD = "extract_method"  # "Extract Method 안전?"
    INLINE = "inline"  # "Inline 가능?"
    ADD_PARAMETER = "add_parameter"  # "파라미터 추가"
    MOVE = "move"  # "함수 이동"

    # Analysis (FULL tier)
    SLICE = "slice"  # "이 코드 슬라이싱"
    TAINT = "taint"  # "Taint 분석"
    PATH_ANALYSIS = "path_analysis"  # "경로 분석"
    NULL_CHECK = "null_check"  # "Null 가능성?"

    # Generic
    UNKNOWN = "unknown"  # 의도 불명확


class QueryType(str, Enum):
    """
    Type of query the agent needs to perform.

    Determines minimum required semantic tier.
    """

    # BASE tier queries (Call Graph)
    CALLERS = "callers"  # "누가 이 함수를 호출?"
    CALLEES = "callees"  # "이 함수가 누구를 호출?"
    REFERENCES = "references"  # "이 심볼 참조 찾기"
    DEFINITIONS = "definitions"  # "정의 찾기"

    # EXTENDED tier queries (DFG)
    FLOW = "flow"  # "이 값 어디서 왔어?"
    DEPENDENCIES = "dependencies"  # "이 변수 의존성"
    SIDE_EFFECTS = "side_effects"  # "부작용 분석"
    VALUE_ORIGIN = "value_origin"  # "값의 출처"

    # FULL tier queries (SSA/PDG)
    SLICE = "slice"  # "Program slicing"
    PATH_SENSITIVE = "path_sensitive"  # "경로 민감 분석"
    REACHING_DEFS = "reaching_defs"  # "Reaching definitions"
    DOMINANCE = "dominance"  # "Dominator 분석"

    # Generic
    UNKNOWN = "unknown"  # 쿼리 타입 불명확


class Scope(str, Enum):
    """
    Scope of the operation.

    May influence tier selection (larger scope → higher tier).
    """

    FILE = "file"  # Single file
    FUNCTION = "function"  # Single function
    CLASS = "class"  # Single class
    MODULE = "module"  # Single module
    PACKAGE = "package"  # Package/directory
    REPO = "repo"  # Entire repository

    UNKNOWN = "unknown"  # Scope 불명확
