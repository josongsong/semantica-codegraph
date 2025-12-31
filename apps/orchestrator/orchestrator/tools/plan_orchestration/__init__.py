"""
Plan-Based Tool Orchestration (RFC-041)

LLM은 Tool을 선택하지 않음.
LLM은 Plan(분석 모드)만 선택함.
실제 Tool 호출·순서·파라미터는 시스템이 결정.

Architecture:
    User Query
     → LLM: Plan 선택 (≤10)
     → System: Plan → Step → Tool Chain 실행
     → LLM: 결과 해석 및 설명

Key Components:
    - AnalysisPlan: 분석 계획 정의 (Step 시퀀스)
    - PlanStep: 단일 분석 단계 (Tool 바인딩)
    - PlanRegistry: Plan 정의서 관리 (버전 관리)
    - PlanExecutor: Step Chain 실행
    - PlanToolProvider: LLM 인터페이스 (기존 ToolProvider 대체)

Usage:
    # 1. Provider 생성
    provider = PlanToolProviderFactory.create(tool_registry)

    # 2. LLM에 Tool 목록 제공 (10개 고정)
    tools = provider.get_tools_for_llm("openai")

    # 3. LLM Tool Call 처리
    result = provider.handle_tool_call(
        tool_name="plan_analyze_security",
        arguments={"target": "src/api/login.py"}
    )
"""

from .models import (
    AnalysisPlan,
    PlanCategory,
    PlanResult,
    PlanStep,
    StepConfig,
    StepResult,
    StepStatus,
)
from .plan_executor import AutoTool, PlanExecutor
from .plan_registry import PlanRegistry
from .plan_tool_provider import PlanToolProvider, PlanToolProviderFactory
from .plan_tools import (
    PLAN_TOOLS,
    PlanToolDefinition,
    get_llm_tools_anthropic,
    get_llm_tools_openai,
    get_plan_tool_by_name,
    get_plan_tool_names,
)
from .step_tool_binding import (
    EXISTING_TOOLS,
    REQUIRED_NEW_TOOLS,
    STEP_TOOL_BINDING,
    get_binding_statistics,
    get_missing_tools,
    get_tool_for_step,
)

__all__ = [
    # Models
    "AnalysisPlan",
    "PlanStep",
    "PlanResult",
    "StepResult",
    "StepConfig",
    "StepStatus",
    "PlanCategory",
    # Core
    "PlanRegistry",
    "PlanExecutor",
    "PlanToolProvider",
    "PlanToolProviderFactory",
    "AutoTool",
    # Plan Tools (LLM 노출)
    "PLAN_TOOLS",
    "PlanToolDefinition",
    "get_llm_tools_openai",
    "get_llm_tools_anthropic",
    "get_plan_tool_names",
    "get_plan_tool_by_name",
    # Step-Tool Binding
    "STEP_TOOL_BINDING",
    "EXISTING_TOOLS",
    "REQUIRED_NEW_TOOLS",
    "get_tool_for_step",
    "get_missing_tools",
    "get_binding_statistics",
]
