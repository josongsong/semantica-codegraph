"""
Plan Tools - LLM에 노출되는 10개 Tool (RFC-041)

LLM은 이 10개 Plan Tool만 선택할 수 있음.
실제 Tool 호출은 시스템이 Plan → Step → Tool로 실행.

핵심 원칙:
- LLM은 Tool을 선택하지 않음
- LLM은 Plan(분석 모드)만 선택함
- 세부 Tool, 순서, 조건에는 관여 불가
"""

from dataclasses import dataclass
from typing import Any

from ..code_foundation.base import ToolMetadata, ToolResult


@dataclass
class PlanToolDefinition:
    """Plan Tool 정의 (LLM 노출용)"""

    name: str
    description: str
    category: str
    examples: list[str]

    def to_openai_function(self) -> dict[str, Any]:
        """OpenAI function calling 포맷"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "분석 대상 (파일 경로, 함수명, 심볼 등)",
                        },
                        "context": {
                            "type": "string",
                            "description": "추가 컨텍스트 정보 (선택)",
                        },
                    },
                    "required": ["target"],
                },
            },
        }

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Anthropic tool use 포맷"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "분석 대상 (파일 경로, 함수명, 심볼 등)",
                    },
                    "context": {
                        "type": "string",
                        "description": "추가 컨텍스트 정보 (선택)",
                    },
                },
                "required": ["target"],
            },
        }


# ================================================================
# RFC-041 정의: LLM에 노출되는 10개 Plan Tool
# ================================================================

PLAN_TOOLS: list[PlanToolDefinition] = [
    # 1. 심볼 이해
    PlanToolDefinition(
        name="plan_understand_symbol",
        description=(
            "심볼(함수, 클래스, 변수)의 정의와 사용 패턴을 분석합니다. "
            "'이 함수가 뭐야?', '이 클래스 어디서 정의됐어?' 같은 질문에 사용합니다."
        ),
        category="understand",
        examples=[
            "process_payment 함수가 뭐하는 거야?",
            "UserService 클래스 설명해줘",
            "config 변수가 어디서 정의됐어?",
        ],
    ),
    # 2. 구조 이해
    PlanToolDefinition(
        name="plan_understand_structure",
        description=(
            "파일, 모듈, 패키지의 구조를 분석합니다. "
            "'이 파일 구조 설명해줘', '이 모듈에 뭐가 있어?' 같은 질문에 사용합니다."
        ),
        category="understand",
        examples=[
            "src/agent 폴더 구조 설명해줘",
            "이 파일에 어떤 클래스들이 있어?",
            "모듈 의존성 보여줘",
        ],
    ),
    # 3. 실행 추적
    PlanToolDefinition(
        name="plan_trace_execution",
        description=(
            "함수 호출 경로와 실행 흐름을 추적합니다. "
            "'main에서 이 함수까지 어떻게 호출돼?', "
            "'이 함수가 호출하는 함수들은?' 같은 질문에 사용합니다."
        ),
        category="trace",
        examples=[
            "main에서 process_payment까지 호출 경로 보여줘",
            "handle_request가 호출하는 함수들 알려줘",
            "이 함수 누가 호출해?",
        ],
    ),
    # 4. 데이터 흐름 추적
    PlanToolDefinition(
        name="plan_trace_dataflow",
        description=(
            "변수 간 데이터 흐름을 추적합니다. "
            "'이 변수 값이 어디서 왔어?', "
            "'user_input이 어디까지 전파돼?' 같은 질문에 사용합니다."
        ),
        category="trace",
        examples=[
            "password 변수가 어디까지 전파되는지 추적해줘",
            "result 값이 어디서 오는지 역추적해줘",
            "이 데이터가 어디로 가?",
        ],
    ),
    # 5. 보안 분석 (핵심)
    PlanToolDefinition(
        name="plan_analyze_security",
        description=(
            "코드의 보안 취약점을 분석합니다. SQL Injection, XSS, "
            "Command Injection 등을 탐지합니다. "
            "'이 코드 보안 취약점 있어?', '인젝션 가능한 곳 찾아줘' 같은 질문에 사용합니다."
        ),
        category="analyze",
        examples=[
            "이 파일에 SQL Injection 취약점 있어?",
            "user_input이 안전하게 처리되는지 확인해줘",
            "보안 취약점 전체 스캔해줘",
        ],
    ),
    # 6. 변경 영향 분석
    PlanToolDefinition(
        name="plan_assess_change_impact",
        description=(
            "코드를 수정했을 때 영향받는 범위를 분석합니다. "
            "'이 함수 바꾸면 어디가 영향받아?', "
            "'이 변경으로 깨질 수 있는 곳은?' 같은 질문에 사용합니다."
        ),
        category="impact",
        examples=[
            "calculate_price 함수 바꾸면 어디가 영향받아?",
            "이 리팩토링의 영향 범위 분석해줘",
            "이거 수정하면 테스트 깨져?",
        ],
    ),
    # 7. 유사 패턴 찾기
    PlanToolDefinition(
        name="plan_find_variant",
        description=(
            "유사한 코드 패턴이나 중복 코드를 찾습니다. "
            "'이거랑 비슷한 코드 있어?', '중복 코드 찾아줘' 같은 질문에 사용합니다."
        ),
        category="analyze",
        examples=[
            "이 함수랑 비슷한 패턴 찾아줘",
            "프로젝트에서 중복 코드 찾아줘",
            "이 버그랑 같은 패턴 있어?",
        ],
    ),
    # 8. 결과 설명
    PlanToolDefinition(
        name="plan_explain_finding",
        description=(
            "분석 결과를 이해하기 쉽게 설명합니다. '이 결과가 무슨 뜻이야?', '이 코드 설명해줘' 같은 질문에 사용합니다."
        ),
        category="explain",
        examples=[
            "방금 분석 결과 설명해줘",
            "이 취약점이 왜 위험한 거야?",
            "이 코드가 뭘 하는 건지 설명해줘",
        ],
    ),
    # 9. 패치 생성
    PlanToolDefinition(
        name="plan_generate_patch",
        description=(
            "버그 수정, 보안 취약점 패치, 코드 개선을 위한 수정안을 생성합니다. "
            "'이 버그 고쳐줘', '보안 취약점 패치해줘' 같은 질문에 사용합니다."
        ),
        category="generate",
        examples=[
            "이 SQL Injection 취약점 패치해줘",
            "null pointer 버그 수정해줘",
            "이 코드 리팩토링해줘",
        ],
    ),
    # 10. 패치 검증
    PlanToolDefinition(
        name="plan_verify_patch",
        description=(
            "생성된 패치가 문제를 해결하고 새로운 문제를 만들지 않는지 검증합니다. "
            "'이 패치 괜찮아?', '패치 적용해도 되나?' 같은 질문에 사용합니다."
        ),
        category="verify",
        examples=[
            "방금 생성한 패치 검증해줘",
            "이 수정이 다른 곳에 영향 없는지 확인해줘",
            "패치 적용하면 테스트 통과해?",
        ],
    ),
]


def get_llm_tools_openai() -> list[dict[str, Any]]:
    """
    OpenAI function calling 포맷으로 Tool 목록 반환

    Returns:
        OpenAI tools 배열
    """
    return [tool.to_openai_function() for tool in PLAN_TOOLS]


def get_llm_tools_anthropic() -> list[dict[str, Any]]:
    """
    Anthropic tool use 포맷으로 Tool 목록 반환

    Returns:
        Anthropic tools 배열
    """
    return [tool.to_anthropic_tool() for tool in PLAN_TOOLS]


def get_plan_tool_names() -> list[str]:
    """Plan Tool 이름 목록"""
    return [tool.name for tool in PLAN_TOOLS]


def get_plan_tool_by_name(name: str) -> PlanToolDefinition | None:
    """이름으로 Plan Tool 찾기"""
    for tool in PLAN_TOOLS:
        if tool.name == name:
            return tool
    return None


# ================================================================
# Plan Tool → AnalysisPlan 매핑 (실행 시 사용)
# ================================================================

PLAN_NAME_MAPPING: dict[str, str] = {
    "plan_understand_symbol": "plan_understand_symbol",
    "plan_understand_structure": "plan_understand_structure",
    "plan_trace_execution": "plan_trace_execution",
    "plan_trace_dataflow": "plan_trace_dataflow",
    "plan_analyze_security": "plan_analyze_security",
    "plan_assess_change_impact": "plan_assess_change_impact",
    "plan_find_variant": "plan_find_variant",
    "plan_explain_finding": "plan_explain_finding",
    "plan_generate_patch": "plan_generate_patch",
    "plan_verify_patch": "plan_verify_patch",
}
