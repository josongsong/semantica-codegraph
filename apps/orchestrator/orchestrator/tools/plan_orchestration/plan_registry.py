"""
Plan Registry (RFC-041)

ToolRegistry의 역할 재정의:
- ❌ LLM이 ToolRegistry에서 Tool을 검색
- ✅ Analysis Plan ↔ Tool 바인딩 관리
- ✅ Plan 버전 관리
- ✅ Fallback / Guard 조건 관리
- ✅ 실행 결정의 결정론성 보장

ToolRegistry는 LLM용 검색기가 아니라 시스템용 실행 정의서임.
"""

import logging
from typing import Any

from .models import AnalysisPlan, PlanCategory, PlanStep, StepConfig

logger = logging.getLogger(__name__)


class PlanRegistry:
    """
    Plan Registry - 시스템용 실행 정의서

    역할:
    1. Plan 정의 관리 (버전별)
    2. Plan → Step → Tool 바인딩
    3. LLM 노출용 Plan Tool 목록 제공
    4. Plan 버전 관리 및 deprecation
    """

    def __init__(self):
        # Plan 저장소: {plan_name: {version: AnalysisPlan}}
        self._plans: dict[str, dict[str, AnalysisPlan]] = {}

        # Tool → Step 매핑 (역방향 조회용)
        self._tool_to_steps: dict[str, list[tuple[str, str]]] = {}  # tool -> [(plan, step)]

        # 초기화
        self._register_builtin_plans()

        logger.info(f"PlanRegistry initialized with {len(self._plans)} plans")

    def _register_builtin_plans(self):
        """기본 제공 Plan 등록 (RFC-041 정의)"""

        # ================================================================
        # 1. plan_understand_symbol (심볼 이해)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_understand_symbol",
                version="v1",
                description="심볼(함수, 클래스, 변수)의 정의와 사용 패턴을 분석합니다.",
                category=PlanCategory.UNDERSTAND,
                llm_description=(
                    "주어진 심볼(함수, 클래스, 변수)의 정의 위치, 타입, "
                    "사용 패턴을 분석합니다. '이 함수가 뭐야?', "
                    "'이 클래스 어디서 정의됐어?' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "process_payment 함수가 뭐하는 거야?",
                    "UserService 클래스 설명해줘",
                    "config 변수가 어디서 정의됐어?",
                ],
                steps=[
                    PlanStep(
                        name="resolve_symbol_definition",
                        description="심볼 정의 위치 찾기",
                        tool="get_symbol_definition",
                        config=StepConfig(timeout_ms=5000),
                    ),
                    PlanStep(
                        name="find_symbol_references",
                        description="심볼 사용처 찾기",
                        tool="find_all_references",
                        config=StepConfig(max_results=50),
                        depends_on=["resolve_symbol_definition"],
                    ),
                    PlanStep(
                        name="analyze_usage_pattern",
                        description="사용 패턴 분석",
                        tool="analyze_usage_pattern",
                        config=StepConfig(skip_if_empty_input=True),
                        depends_on=["find_symbol_references"],
                    ),
                ],
                tags=["understand", "symbol", "definition"],
            )
        )

        # ================================================================
        # 2. plan_understand_structure (구조 이해)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_understand_structure",
                version="v1",
                description="코드 구조(파일, 모듈, 패키지)를 분석합니다.",
                category=PlanCategory.UNDERSTAND,
                llm_description=(
                    "파일, 모듈, 패키지의 구조를 분석합니다. "
                    "'이 파일 구조 설명해줘', '이 모듈에 뭐가 있어?' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "src/agent 폴더 구조 설명해줘",
                    "이 파일에 어떤 클래스들이 있어?",
                ],
                steps=[
                    PlanStep(
                        name="analyze_file_structure",
                        description="파일/모듈 구조 분석",
                        tool="analyze_file_structure",
                        config=StepConfig(timeout_ms=10000),
                    ),
                    PlanStep(
                        name="resolve_imports",
                        description="import 관계 분석",
                        tool="resolve_imports",
                        depends_on=["analyze_file_structure"],
                    ),
                    PlanStep(
                        name="build_module_graph",
                        description="모듈 의존성 그래프",
                        tool="build_dependency_graph",
                        depends_on=["resolve_imports"],
                    ),
                ],
                tags=["understand", "structure", "module"],
            )
        )

        # ================================================================
        # 3. plan_trace_execution (실행 추적)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_trace_execution",
                version="v1",
                description="함수 호출 경로와 실행 흐름을 추적합니다.",
                category=PlanCategory.TRACE,
                llm_description=(
                    "함수 A에서 함수 B까지의 호출 경로를 추적합니다. "
                    "'main에서 이 함수까지 어떻게 호출돼?', "
                    "'이 함수가 호출하는 함수들은?' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "main에서 process_payment까지 호출 경로 보여줘",
                    "handle_request가 호출하는 함수들 알려줘",
                ],
                steps=[
                    PlanStep(
                        name="resolve_entry_point",
                        description="진입점 확인",
                        tool="get_symbol_definition",
                        config=StepConfig(timeout_ms=5000),
                    ),
                    PlanStep(
                        name="build_call_graph",
                        description="호출 그래프 구축",
                        tool="build_call_graph",
                        config=StepConfig(depth=5),
                        depends_on=["resolve_entry_point"],
                    ),
                    PlanStep(
                        name="find_call_chain",
                        description="호출 체인 탐색",
                        tool="find_call_chain",
                        config=StepConfig(depth=10),
                        depends_on=["build_call_graph"],
                    ),
                ],
                tags=["trace", "execution", "call-graph"],
            )
        )

        # ================================================================
        # 4. plan_trace_dataflow (데이터 흐름 추적)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_trace_dataflow",
                version="v1",
                description="변수 간 데이터 흐름을 추적합니다.",
                category=PlanCategory.TRACE,
                llm_description=(
                    "데이터가 어디서 어디로 흐르는지 추적합니다. "
                    "'이 변수 값이 어디서 왔어?', "
                    "'user_input이 어디까지 전파돼?' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "password 변수가 어디까지 전파되는지 추적해줘",
                    "result 값이 어디서 오는지 역추적해줘",
                ],
                steps=[
                    PlanStep(
                        name="resolve_variable",
                        description="변수 정의 위치 확인",
                        tool="get_symbol_definition",
                    ),
                    PlanStep(
                        name="find_data_dependency",
                        description="데이터 의존성 분석",
                        tool="find_data_dependency",
                        config=StepConfig(depth=10),
                        depends_on=["resolve_variable"],
                    ),
                    PlanStep(
                        name="trace_alias",
                        description="별칭 추적 (포인터 분석)",
                        tool="trace_alias",
                        config=StepConfig(skip_if_empty_input=True),
                        depends_on=["find_data_dependency"],
                    ),
                ],
                tags=["trace", "dataflow", "taint"],
            )
        )

        # ================================================================
        # 5. plan_analyze_security (보안 분석) - 핵심
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_analyze_security",
                version="v1",
                description="보안 취약점(SQL Injection, XSS 등)을 분석합니다.",
                category=PlanCategory.ANALYZE,
                llm_description=(
                    "코드의 보안 취약점을 분석합니다. SQL Injection, XSS, "
                    "Command Injection 등을 탐지합니다. "
                    "'이 코드 보안 취약점 있어?', '인젝션 가능한 곳 찾아줘' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "이 파일에 SQL Injection 취약점 있어?",
                    "user_input이 안전하게 처리되는지 확인해줘",
                    "보안 취약점 전체 스캔해줘",
                ],
                steps=[
                    PlanStep(
                        name="resolve_entry_points",
                        description="진입점(엔드포인트) 확인",
                        tool="find_entry_points",
                        config=StepConfig(timeout_ms=10000),
                    ),
                    PlanStep(
                        name="resolve_type_hierarchy",
                        description="타입 계층 분석 (정밀 분석용)",
                        tool="find_type_hierarchy",
                        depends_on=["resolve_entry_points"],
                    ),
                    PlanStep(
                        name="build_call_graph_slice",
                        description="관련 호출 그래프 슬라이스",
                        tool="build_call_graph",
                        config=StepConfig(depth=3),
                        depends_on=["resolve_type_hierarchy"],
                    ),
                    PlanStep(
                        name="find_taint_flow",
                        description="테인트 흐름 분석 (Source → Sink)",
                        tool="find_taint_flow",
                        config=StepConfig(depth=10, timeout_ms=30000),
                        depends_on=["build_call_graph_slice"],
                    ),
                    PlanStep(
                        name="analyze_control_flow",
                        description="제어 흐름 분석 (가드 조건 확인)",
                        tool="analyze_control_flow",
                        depends_on=["find_taint_flow"],
                    ),
                    PlanStep(
                        name="validate_security_guard",
                        description="보안 가드(sanitizer) 검증",
                        tool="validate_security_guard",
                        depends_on=["analyze_control_flow"],
                    ),
                    PlanStep(
                        name="detect_vulnerabilities",
                        description="취약점 탐지 및 분류",
                        tool="detect_vulnerabilities",
                        depends_on=["validate_security_guard"],
                    ),
                    PlanStep(
                        name="explain_security_finding",
                        description="보안 결과 설명 (LLM 해석)",
                        tool="explain_finding",
                        config=StepConfig(skip_if_empty_input=True),
                        depends_on=["detect_vulnerabilities"],
                    ),
                ],
                tags=["security", "taint", "vulnerability"],
            )
        )

        # ================================================================
        # 6. plan_assess_change_impact (변경 영향 분석)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_assess_change_impact",
                version="v1",
                description="코드 변경의 영향 범위를 분석합니다.",
                category=PlanCategory.IMPACT,
                llm_description=(
                    "코드를 수정했을 때 영향받는 범위를 분석합니다. "
                    "'이 함수 바꾸면 어디가 영향받아?', "
                    "'이 변경으로 깨질 수 있는 곳은?' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "calculate_price 함수 바꾸면 어디가 영향받아?",
                    "이 리팩토링의 영향 범위 분석해줘",
                ],
                steps=[
                    PlanStep(
                        name="identify_change_target",
                        description="변경 대상 식별",
                        tool="get_symbol_definition",
                    ),
                    PlanStep(
                        name="find_direct_references",
                        description="직접 참조 찾기",
                        tool="find_all_references",
                        depends_on=["identify_change_target"],
                    ),
                    PlanStep(
                        name="compute_transitive_impact",
                        description="전이적 영향 계산",
                        tool="compute_change_impact",
                        config=StepConfig(depth=5),
                        depends_on=["find_direct_references"],
                    ),
                    PlanStep(
                        name="find_affected_tests",
                        description="영향받는 테스트 찾기",
                        tool="find_affected_code",
                        config=StepConfig(max_results=50),
                        depends_on=["compute_transitive_impact"],
                    ),
                ],
                tags=["impact", "change", "refactoring"],
            )
        )

        # ================================================================
        # 7. plan_find_variant (유사 코드/패턴 찾기)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_find_variant",
                version="v1",
                description="유사한 코드 패턴이나 중복을 찾습니다.",
                category=PlanCategory.ANALYZE,
                llm_description=(
                    "비슷한 코드 패턴이나 중복 코드를 찾습니다. "
                    "'이거랑 비슷한 코드 있어?', '중복 코드 찾아줘' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "이 함수랑 비슷한 패턴 찾아줘",
                    "프로젝트에서 중복 코드 찾아줘",
                ],
                steps=[
                    PlanStep(
                        name="extract_code_pattern",
                        description="코드 패턴 추출",
                        tool="extract_code_pattern",
                    ),
                    PlanStep(
                        name="search_similar_code",
                        description="유사 코드 검색",
                        tool="search_similar_code",
                        config=StepConfig(max_results=20),
                        depends_on=["extract_code_pattern"],
                    ),
                    PlanStep(
                        name="rank_similarity",
                        description="유사도 순위 계산",
                        tool="rank_similarity",
                        depends_on=["search_similar_code"],
                    ),
                ],
                tags=["variant", "duplicate", "pattern"],
            )
        )

        # ================================================================
        # 8. plan_explain_finding (결과 설명)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_explain_finding",
                version="v1",
                description="분석 결과를 이해하기 쉽게 설명합니다.",
                category=PlanCategory.UNDERSTAND,
                llm_description=(
                    "이전 분석 결과나 코드 조각을 이해하기 쉽게 설명합니다. "
                    "'이 결과가 무슨 뜻이야?', '이 코드 설명해줘' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "방금 분석 결과 설명해줘",
                    "이 취약점이 왜 위험한 거야?",
                ],
                steps=[
                    PlanStep(
                        name="extract_context",
                        description="설명에 필요한 컨텍스트 추출",
                        tool="extract_context",
                    ),
                    PlanStep(
                        name="generate_explanation",
                        description="LLM 기반 설명 생성",
                        tool="explain_finding",
                        depends_on=["extract_context"],
                    ),
                ],
                tags=["explain", "interpret", "describe"],
            )
        )

        # ================================================================
        # 9. plan_generate_patch (패치 생성)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_generate_patch",
                version="v1",
                description="버그 수정이나 개선을 위한 코드 패치를 생성합니다.",
                category=PlanCategory.GENERATE,
                llm_description=(
                    "버그 수정, 보안 취약점 패치, 코드 개선을 위한 수정안을 생성합니다. "
                    "'이 버그 고쳐줘', '보안 취약점 패치해줘' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "이 SQL Injection 취약점 패치해줘",
                    "null pointer 버그 수정해줘",
                ],
                steps=[
                    PlanStep(
                        name="analyze_issue",
                        description="문제 분석",
                        tool="analyze_issue",
                    ),
                    PlanStep(
                        name="determine_fix_strategy",
                        description="수정 전략 결정",
                        tool="determine_fix_strategy",
                        depends_on=["analyze_issue"],
                    ),
                    PlanStep(
                        name="generate_patch_code",
                        description="패치 코드 생성",
                        tool="generate_patch",
                        depends_on=["determine_fix_strategy"],
                    ),
                    PlanStep(
                        name="validate_patch",
                        description="패치 검증 (구문/타입)",
                        tool="validate_patch",
                        depends_on=["generate_patch_code"],
                    ),
                ],
                tags=["generate", "patch", "fix"],
            )
        )

        # ================================================================
        # 10. plan_verify_patch (패치 검증)
        # ================================================================
        self.register(
            AnalysisPlan(
                name="plan_verify_patch",
                version="v1",
                description="생성된 패치가 올바른지 검증합니다.",
                category=PlanCategory.VERIFY,
                llm_description=(
                    "생성된 패치가 문제를 해결하고 새로운 문제를 만들지 않는지 검증합니다. "
                    "'이 패치 괜찮아?', '패치 적용해도 되나?' 같은 질문에 사용합니다."
                ),
                llm_examples=[
                    "방금 생성한 패치 검증해줘",
                    "이 수정이 다른 곳에 영향 없는지 확인해줘",
                ],
                steps=[
                    PlanStep(
                        name="parse_patch",
                        description="패치 파싱",
                        tool="parse_patch",
                    ),
                    PlanStep(
                        name="verify_syntax",
                        description="구문 검증",
                        tool="verify_syntax",
                        depends_on=["parse_patch"],
                    ),
                    PlanStep(
                        name="verify_type_safety",
                        description="타입 안전성 검증",
                        tool="verify_type_safety",
                        depends_on=["verify_syntax"],
                    ),
                    PlanStep(
                        name="check_regression",
                        description="회귀 영향 검사",
                        tool="check_regression",
                        depends_on=["verify_type_safety"],
                    ),
                    PlanStep(
                        name="run_affected_tests",
                        description="영향받는 테스트 실행",
                        tool="run_tests",
                        config=StepConfig(timeout_ms=60000, skip_if_empty_input=True),
                        depends_on=["check_regression"],
                    ),
                ],
                tags=["verify", "validate", "test"],
            )
        )

    def register(self, plan: AnalysisPlan) -> None:
        """
        Plan 등록

        Args:
            plan: 등록할 Plan

        Raises:
            ValueError: 이미 동일 버전이 존재하는 경우
        """
        if plan.name not in self._plans:
            self._plans[plan.name] = {}

        if plan.version in self._plans[plan.name]:
            raise ValueError(f"Plan {plan.full_name} already registered")

        self._plans[plan.name][plan.version] = plan

        # 역방향 매핑 업데이트
        for step in plan.steps:
            if step.tool not in self._tool_to_steps:
                self._tool_to_steps[step.tool] = []
            self._tool_to_steps[step.tool].append((plan.name, step.name))

        logger.info(f"Registered plan: {plan.full_name} ({len(plan.steps)} steps)")

    def get_plan(self, name: str, version: str | None = None) -> AnalysisPlan | None:
        """
        Plan 가져오기

        Args:
            name: Plan 이름
            version: 버전 (None이면 최신)

        Returns:
            AnalysisPlan or None
        """
        if name not in self._plans:
            return None

        versions = self._plans[name]

        if version:
            return versions.get(version)

        # 최신 버전 반환 (v1, v2, v3... 순서)
        if versions:
            latest_version = sorted(versions.keys())[-1]
            return versions[latest_version]

        return None

    def get_all_plans(self, include_deprecated: bool = False) -> list[AnalysisPlan]:
        """
        모든 Plan 가져오기 (최신 버전만)

        Args:
            include_deprecated: deprecated 포함 여부
        """
        plans = []
        for name in self._plans:
            plan = self.get_plan(name)
            if plan and (include_deprecated or not plan.deprecated):
                plans.append(plan)
        return plans

    def get_llm_tools(self) -> list[dict[str, Any]]:
        """
        LLM에 노출할 Tool 목록 (10개 고정)

        Returns:
            OpenAI/Anthropic 호환 Tool 정의 리스트
        """
        plans = self.get_all_plans(include_deprecated=False)
        return [plan.to_llm_tool() for plan in plans]

    def get_plans_by_category(self, category: PlanCategory) -> list[AnalysisPlan]:
        """카테고리별 Plan 가져오기"""
        return [p for p in self.get_all_plans() if p.category == category]

    def find_plans_for_tool(self, tool_name: str) -> list[tuple[str, str]]:
        """특정 Tool을 사용하는 Plan 찾기"""
        return self._tool_to_steps.get(tool_name, [])

    def get_statistics(self) -> dict[str, Any]:
        """통계 정보"""
        all_plans = self.get_all_plans(include_deprecated=True)
        active_plans = self.get_all_plans(include_deprecated=False)

        total_steps = sum(len(p.steps) for p in active_plans)
        unique_tools = set()
        for plan in active_plans:
            for step in plan.steps:
                unique_tools.add(step.tool)

        return {
            "total_plans": len(all_plans),
            "active_plans": len(active_plans),
            "deprecated_plans": len(all_plans) - len(active_plans),
            "total_steps": total_steps,
            "unique_tools": len(unique_tools),
            "plans_by_category": {cat.value: len(self.get_plans_by_category(cat)) for cat in PlanCategory},
        }
