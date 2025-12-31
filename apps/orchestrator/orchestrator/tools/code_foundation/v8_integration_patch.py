"""
V8 Orchestrator Patch

기존 v8_orchestrator.py에 추가할 코드
"""


# ============================================
# v8_orchestrator.py에 추가할 코드
# ============================================

"""
1. Import 추가 (파일 상단):

from apps.orchestrator.orchestrator.tools.code_foundation import (
    CodeFoundationToolProvider,
    ToolCategory,
    ExecutionMode,
)
from apps.orchestrator.orchestrator.tools.code_foundation.integration import (
    CodeFoundationToolsIntegrator
)


2. V8AgentOrchestrator.__init__에 추가:

def __init__(self, ...):
    # 기존 코드...

    # Code Foundation Tools 초기화
    self.tool_provider: Optional[CodeFoundationToolProvider] = None
    self._init_code_foundation_tools()


3. 메서드 추가:

def _init_code_foundation_tools(self) -> None:
    '''Code Foundation Tools 초기화'''
    try:
        # IR Analyzer 가져오기 (없으면 생성)
        if not hasattr(self, 'ir_analyzer'):
            from codegraph_engine.code_foundation.infrastructure.ir import UnifiedAnalyzer
            self.ir_analyzer = UnifiedAnalyzer()

        # Security Analyzer 가져오기
        if not hasattr(self, 'security_analyzer'):
            from codegraph_engine.code_foundation.infrastructure.analyzers import DeepSecurityAnalyzer
            self.security_analyzer = DeepSecurityAnalyzer(
                ir=self.ir_analyzer,
                call_graph=None,  # Lazy init
                max_depth=3
            )

        # Provider 초기화
        self.tool_provider = CodeFoundationToolsIntegrator.initialize(
            ir_analyzer=self.ir_analyzer,
            security_analyzer=self.security_analyzer,
            embedding_service=self.embedding_service,
            llm_adapter=self.llm_adapter
        )

        logger.info("Code Foundation Tools initialized successfully")

    except Exception as e:
        logger.warning(
            f"Failed to initialize Code Foundation Tools: {e}. "
            "Continuing without tools."
        )
        self.tool_provider = None


4. execute 메서드에서 도구 사용:

async def execute(self, request: V8AgentRequest) -> V8AgentResponse:
    '''V8 실행 (도구 통합)'''

    # ... 기존 코드 ...

    # Code Foundation Tools 사용 여부 판단
    use_tools = (
        self.tool_provider is not None and
        self._should_use_code_tools(request.task)
    )

    if use_tools:
        # 1. 쿼리에 맞는 도구 선택
        tools = self.tool_provider.get_tools_for_query(
            query=request.task.instruction,
            context={
                "task": request.task,
                "workspace": request.task.workspace_path,
                "file_path": request.task.target_file,
                "recent_tools": self._get_recent_tools(),
            },
            k=8,  # Top-8 도구
            mode="auto"
        )

        # 2. LLM 포맷으로 변환
        llm_tools = self._convert_tools_to_llm_format(tools)

        # 3. LLM에 도구 제공
        # (기존 LLM 호출 로직에 tools 파라미터 추가)

        logger.info(
            f"Providing {len(tools)} Code Foundation tools to LLM: "
            f"{[t.metadata.name for t in tools]}"
        )

    # ... 기존 실행 로직 ...


5. 헬퍼 메서드 추가:

def _should_use_code_tools(self, task: AgentTask) -> bool:
    '''Code Foundation Tools 사용 여부 판단'''

    # 코드 관련 작업인지 확인
    keywords = [
        "함수", "클래스", "메서드", "변수",
        "function", "class", "method", "variable",
        "버그", "bug", "error", "에러",
        "보안", "security", "취약점",
        "영향", "impact", "변경", "change",
        "참조", "reference", "호출", "call"
    ]

    instruction_lower = task.instruction.lower()
    return any(kw in instruction_lower for kw in keywords)


def _get_recent_tools(self) -> List[str]:
    '''최근 사용한 도구 이름들'''
    # TODO: 세션에서 가져오기
    return []


def _convert_tools_to_llm_format(
    self,
    tools: List[CodeFoundationTool]
) -> List[Dict[str, Any]]:
    '''Code Foundation Tool을 LLM 포맷으로 변환'''

    llm_tools = []

    for tool in tools:
        metadata = tool.metadata

        # OpenAI function calling 포맷
        if self.llm_adapter.provider == "openai":
            llm_tools.append(metadata.to_openai_function())

        # Anthropic tool use 포맷
        elif self.llm_adapter.provider == "anthropic":
            llm_tools.append(metadata.to_anthropic_tool())

        else:
            # 기본 포맷
            llm_tools.append({
                "name": metadata.name,
                "description": metadata.description,
                "parameters": metadata.input_schema
            })

    return llm_tools
"""
