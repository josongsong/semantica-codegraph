# Core Architecture ADR 구현 계획 (ADR-001~004)

**작성일**: 2025-12-05  
**대상**: Core Architecture 4개 ADR (P0)  
**기간**: 8주 (2개월)  
**현재 진행률**: 45% → 100%

---

## 📊 Executive Summary

### 현재 상태

| ADR | 제목 | 진행률 | 상태 |
|-----|------|--------|------|
| ADR-001 | 4-Layer Architecture | 30% | 🟡 Layer 구조만, 통합 없음 |
| ADR-002 | Router vs TaskGraph | 90% | ✅ 분리 완료, 문서화 필요 |
| ADR-003 | Graph Workflow Engine | 40% | 🟡 구조만, Steps Mock |
| ADR-004 | Sandbox Executor | 20% | ⚠️ ShadowFS만, Sandbox 없음 |

### 목표

**8주 후**: 4개 ADR 모두 100% 구현 + Production Ready

```
Week 1-2: ADR-001 Layer 통합 (30% → 60%)
Week 3-4: ADR-001 MetaLayer (60% → 95%)
Week 5:   ADR-003 Workflow 실제 구현 (40% → 85%)
Week 6:   ADR-004 Sandbox 구축 (20% → 90%)
Week 7:   ADR-002 문서화 + E2E (90% → 100%)
Week 8:   통합 테스트 + 성능 최적화 (95% → 100%)
```

---

## ADR-001: 4-Layer Agent Architecture

### 📌 현재 상태: 30%

**완료**:
- ✅ Layer별 디렉토리 구조
- ✅ 기본 데이터 모델
- ✅ Phase 0 Orchestrator (Mock)

**미완료**:
- ❌ Layer 간 실제 데이터 흐름
- ❌ MetaLayer 실제 동작
- ❌ Error propagation

### 🎯 구현 계획

#### **Week 1-2: Layer 통합 기반** (30% → 60%)

**Goal**: Router가 실제 CodeGraph 사용

**Day 1-3: ContextAdapter 구현**
```python
# src/agent/adapters/context_adapter.py

class ContextAdapter:
    """Layer 0 (CodeGraph) Facade"""
    
    def __init__(
        self,
        retrieval_service: RetrievalService,
        chunk_store: ChunkStore,
        graph_store: GraphStore,
    ):
        self.retrieval = retrieval_service
        self.chunks = chunk_store
        self.graph = graph_store
    
    async def search_relevant_code(
        self,
        query: str,
        intent: str,
        top_k: int = 10,
    ) -> SearchResult:
        """Intent 기반 검색 (AutoRRF 사용)"""
        results = await self.retrieval.search(
            query=query,
            intent=intent,
            top_k=top_k,
        )
        
        context = await self._build_context(results)
        
        return SearchResult(
            chunks=results,
            context=context,
            token_count=sum(c.token_count for c in results),
        )
    
    async def get_symbol_graph(
        self,
        symbol_id: str,
        max_depth: int = 2,
    ) -> CallGraph:
        """호출 그래프 (Program Slice용)"""
        return await self.graph.get_subgraph(
            node_id=symbol_id,
            max_depth=max_depth,
        )
```

**Day 4-7: Router → Workflow 연결**
```python
# src/agent/orchestrator/orchestrator.py

async def _route(self, user_request: str, context: Dict):
    """Layer 0 → Layer 1"""
    
    # 1. Strategy 결정
    plan = self.unified_router.route(user_request, budget_ms=5000)
    
    # 2. Context 검색 (실제 CodeGraph 호출)
    search_result = await self.context.search_relevant_code(
        query=user_request,
        intent=plan.intent,
        top_k=plan.adaptive_k,
    )
    
    # 3. Context 업데이트
    context.update({
        "routing_plan": plan,
        "relevant_code": search_result.chunks,
        "token_budget_remaining": plan.token_budget - search_result.token_count,
    })
    
    return IntentResult(...)

async def _execute_workflow(self, intent_result, task_graph):
    """Layer 1 → Layer 2"""
    
    workflow_state = WorkflowState(
        current_step=WorkflowStep.ANALYZE,
        iteration=0,
        context={
            **intent_result.context,
            "task_graph": task_graph,
            "context_adapter": self.context,  # 주입!
            "code_generator": self._build_code_generator(),
            "code_validator": self._build_code_validator(),
        },
    )
    
    return await self.workflow.run(workflow_state)
```

**Day 8-10: Analyze Step 실제 구현**
```python
# src/agent/workflow/state_machine.py

async def _analyze(self, state: WorkflowState) -> StepResult:
    """실제 코드 분석 (Mock 제거)"""
    
    context_adapter = state.context["context_adapter"]
    query = state.context.get("user_request", "")
    
    # 실제 검색
    search_result = await context_adapter.search_relevant_code(
        query=query,
        intent=state.context.get("intent", "balanced"),
        top_k=10,
    )
    
    # Symbol 정보 추출
    symbols = []
    for chunk in search_result.chunks[:5]:  # Top 5만
        symbol_info = await context_adapter.get_symbol_info(chunk.symbol_id)
        symbols.append(symbol_info)
    
    analyzed_data = {
        "chunks": search_result.chunks,
        "symbols": symbols,
        "files": list(set(c.file_path for c in search_result.chunks)),
        "token_count": search_result.token_count,
    }
    
    # Token budget 체크
    if search_result.token_count > state.context.get("token_budget_remaining", 100000):
        return StepResult(
            step=WorkflowStep.ANALYZE,
            success=False,
            output=None,
            error="Token budget exceeded",
        )
    
    return StepResult(
        step=WorkflowStep.ANALYZE,
        success=True,
        output=analyzed_data,
        metadata={
            "total_chunks": len(search_result.chunks),
            "total_symbols": len(symbols),
            "token_used": search_result.token_count,
        }
    )
```

**Tests**:
```python
# tests/integration/test_layer0_layer1.py

async def test_router_uses_real_context():
    """Router가 실제 CodeGraph 사용"""
    # Given
    repo_id = "test_repo"
    await index_repository(repo_id, "./fixtures/sample_repo")
    
    # When
    orchestrator = build_orchestrator(repo_id)
    result = await orchestrator.execute(
        user_request="Where is calculate_total defined?",
        context={"repo_id": repo_id},
    )
    
    # Then
    assert result.is_success()
    assert "calculate_total" in str(result.result)
    assert len(result.metadata["relevant_files"]) > 0

async def test_token_budget_enforcement():
    """Token budget 초과 시 실패"""
    result = await orchestrator.execute(
        user_request="Explain entire codebase",
        context={"token_budget": 1000},  # 매우 작은 budget
    )
    
    assert result.status == ExecutionStatus.FAILED
    assert "Token budget exceeded" in result.error
```

#### **Week 3-4: MetaLayer 구축** (60% → 85%)

**Goal**: M0/M1/M2 실제 동작

**Day 11-13: M0 (TaskGraph) 동적 생성**
```python
# src/agent/task_graph/dynamic_planner.py

class DynamicTaskGraphPlanner:
    """LLM 기반 동적 Task 분해"""
    
    def __init__(self, llm, static_planner: TaskGraphPlanner):
        self.llm = llm
        self.static_planner = static_planner
    
    async def plan(
        self,
        user_intent: str,
        context: Dict[str, Any],
        analyzed_data: Optional[Dict] = None,
    ) -> TaskGraph:
        """동적 Task 생성"""
        
        # Complexity 판단
        complexity = self._estimate_complexity(user_intent, analyzed_data)
        
        if complexity == "simple":
            # Rule 기반 (빠름)
            return self.static_planner.plan(user_intent, context)
        
        # LLM 기반 분해
        prompt = f"""# Task Decomposition

User Request: {user_intent}

Context:
- Files: {analyzed_data.get('files', [])}
- Symbols: {[s.name for s in analyzed_data.get('symbols', [])]}

Break down into tasks with dependencies.

Output JSON:
{{
  "tasks": [
    {{
      "id": "task_1",
      "type": "analyze_code",
      "description": "...",
      "depends_on": []
    }}
  ]
}}
"""
        
        response = await self.llm.complete(prompt, temperature=0.2)
        task_graph = self._parse_task_graph(response)
        
        return task_graph
```

**Day 14-17: M1 (Critic) LLM 리뷰**
```python
# src/safety/critic/code_critic.py

class CodeCritic:
    """LLM 기반 코드 리뷰"""
    
    def __init__(self, llm, guardrail: Guardrail):
        self.llm = llm
        self.guardrail = guardrail
    
    async def review(
        self,
        code_change: CodeChange,
        context: Dict[str, Any],
    ) -> CriticResult:
        """코드 리뷰 (2-phase)"""
        
        # Phase 1: Guardrail (빠른 규칙)
        guardrail_result = self.guardrail.check(code_change)
        if not guardrail_result.passed:
            return CriticResult(
                approved=False,
                issues=[
                    Issue(
                        severity="blocker",
                        rule_id=v.rule_id,
                        message=v.description,
                    )
                    for v in guardrail_result.violations
                ],
            )
        
        # Phase 2: LLM (의미론적 리뷰)
        prompt = f"""# Code Review

## Changed Code
```python
{code_change.content}
```

## Context
- File: {code_change.file_path}
- Intent: {context.get('intent')}
- Original: {context.get('original_code', 'N/A')}

Review for:
1. Correctness
2. Security
3. Performance
4. Maintainability

Output JSON:
{{
  "approved": true/false,
  "issues": [
    {{"severity": "blocker", "message": "..."}}
  ],
  "suggestions": [...]
}}
"""
        
        response = await self.llm.complete(prompt, temperature=0.3)
        review = self._parse_review(response)
        
        return CriticResult(
            approved=review.approved and not review.has_blocker(),
            issues=review.issues,
            suggestions=review.suggestions,
        )
```

**Day 18-20: M2 (Guardrail) Rule Engine**
```python
# src/safety/guardrail/rule_engine.py

@dataclass
class GuardrailRule:
    """단일 규칙"""
    id: str
    name: str
    description: str
    severity: str  # "blocker" | "warning" | "info"
    check: Callable[[CodeChange, Dict], bool]

class GuardrailEngine:
    """규칙 엔진 (YAML 기반)"""
    
    def __init__(self, rules_path: str = "config/guardrail_rules.yaml"):
        self.rules: List[GuardrailRule] = []
        self._load_rules(rules_path)
    
    def _load_rules(self, path: str):
        """YAML → Rule 객체"""
        config = yaml.safe_load(Path(path).read_text())
        
        for rule_config in config["rules"]:
            self.rules.append(
                self._build_rule(rule_config)
            )
    
    def _build_rule(self, config: Dict) -> GuardrailRule:
        """Rule 생성"""
        
        if config["name"] == "LOC_LIMIT":
            return GuardrailRule(
                id=config["id"],
                name=config["name"],
                description=config["description"],
                severity=config["severity"],
                check=lambda change, ctx: (
                    change.lines_added < config["params"]["max_lines"]
                ),
            )
        
        elif config["name"] == "NO_SECRET":
            patterns = [re.compile(p) for p in config["patterns"]]
            return GuardrailRule(
                id=config["id"],
                name=config["name"],
                description=config["description"],
                severity=config["severity"],
                check=lambda change, ctx: not any(
                    pattern.search(change.content)
                    for pattern in patterns
                ),
            )
        
        # ... 다른 규칙들
    
    def check(
        self,
        code_change: CodeChange,
        context: Optional[Dict] = None
    ) -> GuardrailResult:
        """모든 규칙 체크"""
        violations = []
        context = context or {}
        
        for rule in self.rules:
            try:
                if not rule.check(code_change, context):
                    violations.append(Violation(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        description=rule.description,
                        severity=rule.severity,
                    ))
            except Exception as e:
                logger.error(f"Rule {rule.id} failed: {e}")
        
        has_blocker = any(v.severity == "blocker" for v in violations)
        
        return GuardrailResult(
            passed=not has_blocker,
            violations=violations,
        )
```

**YAML 설정**:
```yaml
# config/guardrail_rules.yaml

rules:
  - id: G001
    name: LOC_LIMIT
    description: Single change < 500 lines
    severity: blocker
    params:
      max_lines: 500
  
  - id: G002
    name: NO_SECRET
    description: No API keys or passwords
    severity: blocker
    patterns:
      - "(?i)api[_-]?key"
      - "(?i)password"
      - "(?i)secret"
      - "sk-[a-zA-Z0-9]{32,}"  # OpenAI key
  
  - id: G003
    name: FILE_LIMIT
    description: Max 10 files per change
    severity: warning
    params:
      max_files: 10
  
  - id: G004
    name: NO_HARDCODED_URL
    description: No production URLs in code
    severity: warning
    patterns:
      - "https://api\\.production\\.com"
      - "https://[^/]*\\.prod\\."

# Org-level overrides
org_overrides:
  org_enterprise:
    G001:
      max_lines: 1000
    G003:
      max_files: 20
```

**Tests**:
```python
# tests/unit/test_guardrail.py

def test_loc_limit():
    engine = GuardrailEngine("config/guardrail_rules.yaml")
    
    # Under limit
    change = CodeChange(
        file_path="test.py",
        content="x = 1\n" * 100,
        lines_added=100,
    )
    result = engine.check(change)
    assert result.passed
    
    # Over limit
    change = CodeChange(
        file_path="test.py",
        content="x = 1\n" * 600,
        lines_added=600,
    )
    result = engine.check(change)
    assert not result.passed
    assert "G001" in [v.rule_id for v in result.violations]

def test_secret_detection():
    engine = GuardrailEngine()
    
    # With secret
    change = CodeChange(
        file_path="test.py",
        content='api_key = "sk-1234567890abcdef1234567890abcdef"',
        lines_added=1,
    )
    result = engine.check(change)
    assert not result.passed
    assert "G002" in [v.rule_id for v in result.violations]
```

---

## ADR-002: Router vs TaskGraph Boundary

### 📌 현재 상태: 90%

**완료**:
- ✅ UnifiedRouter 구현 (Rule 기반)
- ✅ TaskGraphPlanner 구현 (Rule 기반)
- ✅ 책임 분리 (Router=실행결정, TaskGraph=계획)

**미완료**:
- ❌ 경계 문서화
- ❌ Edge case 처리 (충돌 해결)

### 🎯 구현 계획

#### **Week 7: 문서화 + Edge Cases** (90% → 100%)

**Day 46-48: 경계 문서화**

```markdown
# docs/adr/ADR-002-BOUNDARY.md

## Router 책임

1. **Intent 분류**
   - User request → Intent (symbol/flow/concept/code)
   - Rule 기반 (5ms 미만)

2. **Strategy 선택**
   - Intent + Budget → Strategy path (symbol/vector/lexical/graph)
   - Top-K 결정 (adaptive)

3. **Advanced Features 결정**
   - HyDE, Multi-Query, Cross-Encoder 활성화 여부
   - Budget 기반 (< 500ms: symbol만, >= 3s: 모든 전략)

## TaskGraph 책임

1. **Task 분해**
   - Intent + Context → Task 목록
   - Dependency 분석

2. **실행 순서**
   - Topological sort
   - Parallel groups 계산

3. **재계획 (Phase 1)**
   - 실행 중 실패 시 Task 재구성
   - Dynamic replanning

## 경계 규칙

### Rule 1: Router는 "What to do", TaskGraph는 "How to do"

```
Router:     "This is a symbol lookup" → strategy=[symbol, lexical]
TaskGraph:  "Search symbols → Validate → Format" → 3 tasks
```

### Rule 2: Router는 한 번, TaskGraph는 여러 번

```
Router: 1회 실행 (user request 받을 때)
TaskGraph: 매 iteration 재계획 가능 (Dynamic replanning)
```

### Rule 3: 충돌 해결 우선순위

```
Router의 Budget/Constraint > TaskGraph의 Task 목록

Example:
- Router: budget_ms=500, strategy=[symbol]
- TaskGraph: 3 tasks (analyze, generate, test)
- 충돌: test는 1초 소요 → Budget 초과
- 해결: test 스킵 or 빠른 모드
```

## Edge Cases

### Case 1: Router는 "simple", 하지만 TaskGraph는 "complex"

```python
# Router
plan = RoutingPlan(
    intent="symbol",
    complexity="simple",  # 단순해 보임
    budget_ms=1000,
)

# TaskGraph (실제로는 complex)
task_graph = planner.plan("symbol", context)
estimated_time = planner.estimate_execution_time(task_graph)

if estimated_time > plan.budget_ms / 1000:
    # Budget 초과 → Task 축소
    task_graph = planner.simplify(task_graph, max_time=1.0)
```

### Case 2: TaskGraph가 Router Strategy 무시

```python
# Router: strategy=[symbol]만 사용
# TaskGraph: vector 검색도 필요하다고 판단

# 해결: Router Strategy를 우선
if task.strategy not in plan.strategy_path:
    logger.warning(f"Task {task.id} uses {task.strategy} not in Router plan")
    # Option 1: Task 스킵
    # Option 2: Router Strategy로 대체
    task.strategy = plan.strategy_path[0]
```
```

**Day 49-50: Edge Case Tests**
```python
# tests/integration/test_router_taskgraph_boundary.py

async def test_budget_enforcement():
    """TaskGraph가 Router budget 준수"""
    
    # Router: 500ms budget
    orchestrator = build_orchestrator()
    orchestrator.unified_router.budget_ms = 500
    
    # TaskGraph: 3초 예상되는 task
    result = await orchestrator.execute("Complex refactoring")
    
    # Then: Budget 초과 → Task 축소 or 실패
    assert result.execution_time_ms <= 600  # 20% 여유

async def test_strategy_mismatch():
    """TaskGraph가 Router strategy 준수"""
    
    # Router: symbol만 사용
    orchestrator.unified_router.force_strategy = ["symbol"]
    
    # Execute
    result = await orchestrator.execute("Find calculate_total")
    
    # Then: vector 검색 사용하지 않음
    assert "vector" not in result.metadata["strategies_used"]
```

---

## ADR-003: Graph Workflow Engine

### 📌 현재 상태: 40%

**완료**:
- ✅ StateMachine 구조
- ✅ 6-step workflow (Analyze → Self-heal)
- ✅ Early exit 조건

**미완료**:
- ❌ Steps는 Mock
- ❌ Dynamic replanning
- ❌ Static Analysis First

### 🎯 구현 계획

#### **Week 5: Workflow 실제 구현** (40% → 85%)

**Day 29-31: Generate Step**
```python
# src/agent/workflow/state_machine.py

async def _generate(self, state: WorkflowState) -> StepResult:
    """실제 코드 생성"""
    
    # Analyze 결과
    analyzed_data = state.context["analyzed_data"]
    intent = state.context.get("intent", "fix_bug")
    
    # CodeGenerator
    generator = state.context.get("code_generator")
    if not generator:
        generator = CodeGenerator(llm=get_llm())
    
    # Intent별 분기
    if intent == "fix_bug":
        code_change = await generator.generate_fix(
            bug_description=state.context["user_request"],
            file_path=analyzed_data["files"][0],
            existing_code=analyzed_data["chunks"][0].content,
            context={
                "symbols": analyzed_data["symbols"],
                "related_files": analyzed_data["files"],
            },
        )
    
    elif intent == "add_feature":
        code_changes = await generator.generate_feature(
            feature_description=state.context["user_request"],
            target_file=analyzed_data["files"][0],
            context=analyzed_data,
        )
        code_change = code_changes[0]
    
    elif intent == "refactor_code":
        code_change = await generator.generate_refactoring(
            refactor_goal=state.context["user_request"],
            file_path=analyzed_data["files"][0],
            existing_code=analyzed_data["chunks"][0].content,
            context=analyzed_data,
        )
    
    else:
        # Generic
        code_change = CodeChange(
            file_path="output.py",
            content="# Generated code\npass",
            explanation="Generic code generation",
        )
    
    return StepResult(
        step=WorkflowStep.GENERATE,
        success=True,
        output=code_change,
        metadata={
            "lines_changed": code_change.lines_added,
            "confidence": code_change.confidence,
        }
    )
```

**Day 32-34: Critic Step (M1 연동)**
```python
async def _critic(self, state: WorkflowState) -> StepResult:
    """실제 Critic (M1 MetaLayer)"""
    
    # 생성된 코드
    code_change = state.result
    if not code_change:
        return StepResult(
            step=WorkflowStep.CRITIC,
            success=False,
            output=None,
            error="No code to review",
        )
    
    # CodeCritic 실행
    critic = state.context.get("code_critic")
    if not critic:
        critic = CodeCritic(
            llm=get_llm(),
            guardrail=GuardrailEngine(),
        )
    
    review = await critic.review(code_change, state.context)
    
    # 결과 처리
    if not review.approved:
        # Critic 피드백 저장 → 재생성
        state.context["critic_feedback"] = review.issues
        state.context["should_regenerate"] = True
        
        # Blocker면 실패
        if review.has_blocker():
            return StepResult(
                step=WorkflowStep.CRITIC,
                success=False,
                output=review,
                error=f"Blocked: {review.blocker_issues()}",
            )
    
    return StepResult(
        step=WorkflowStep.CRITIC,
        success=True,
        output=review,
        metadata={
            "approved": review.approved,
            "issue_count": len(review.issues),
        }
    )
```

**Day 35-37: Dynamic Replanning**
```python
# src/agent/workflow/state_machine.py

def run(self, initial_state: WorkflowState) -> WorkflowState:
    """Workflow 실행 (Dynamic Replanning 추가)"""
    state = initial_state
    
    while state.iteration < self.max_iterations:
        # 각 단계 실행
        for step in self.steps:
            state.current_step = step
            
            # Step 실행
            step_result = await self._execute_step(state, step)
            state.add_step_result(step_result)
            
            # 실패 처리
            if not step_result.success:
                # Error 유형 판단
                error_type = self._classify_error(step_result, state)
                
                if error_type == "code_error":
                    # Code Error → Self-heal 시도
                    state.current_step = WorkflowStep.SELF_HEAL
                    continue
                
                elif error_type == "plan_error":
                    # Plan Error → TaskGraph 재생성
                    state.context["replan_reason"] = step_result.error
                    new_task_graph = await self._replan(state)
                    state.context["task_graph"] = new_task_graph
                    state.iteration = 0  # 재시작
                    break
                
                else:
                    # 복구 불가 → 실패
                    state.error = step_result.error
                    state.current_step = WorkflowStep.FAILED
                    state.exit_reason = WorkflowExitReason.ERROR
                    return state
            
            # 결과 반영
            if step_result.output:
                self._update_state_from_result(state, step, step_result)
            
            # Critic 피드백 → 재생성
            if state.context.get("should_regenerate"):
                state.current_step = WorkflowStep.GENERATE
                state.context["should_regenerate"] = False
                break  # 현재 iteration 중단, 재시작
        
        # Iteration 증가
        state.iteration += 1
        
        # Early exit
        if self._should_exit_early(state):
            break
    
    # 완료
    state.current_step = WorkflowStep.COMPLETED
    state.exit_reason = WorkflowExitReason.SUCCESS
    return state

def _classify_error(
    self,
    step_result: StepResult,
    state: WorkflowState
) -> str:
    """Error 유형 분류"""
    
    error = step_result.error or ""
    
    # Code Error: Syntax, Import, Lint
    if any(x in error.lower() for x in ["syntax", "import", "lint"]):
        return "code_error"
    
    # Plan Error: Budget 초과, Task 실패
    if any(x in error.lower() for x in ["budget", "timeout", "task"]):
        return "plan_error"
    
    # Unknown
    return "unknown"

async def _replan(self, state: WorkflowState) -> TaskGraph:
    """TaskGraph 재생성"""
    
    planner = state.context.get("task_planner")
    reason = state.context.get("replan_reason", "Unknown")
    
    logger.info(f"Replanning due to: {reason}")
    
    # LLM 기반 동적 계획
    new_graph = await planner.plan(
        user_intent=state.context.get("intent", "unknown"),
        context={
            **state.context,
            "replan_reason": reason,
            "previous_failures": [
                r.error for r in state.step_history if not r.success
            ],
        },
        analyzed_data=state.context.get("analyzed_data"),
    )
    
    return new_graph
```

**Day 38-40: Static Analysis First**
```python
async def _analyze(self, state: WorkflowState) -> StepResult:
    """Static Analysis First"""
    
    context_adapter = state.context["context_adapter"]
    query = state.context.get("user_request", "")
    intent = state.context.get("intent", "balanced")
    
    # Phase 1: Static Analysis (빠름, 정확)
    static_result = await self._static_analysis(query, context_adapter)
    
    if static_result.confidence > 0.9 and len(static_result.symbols) > 0:
        # Static으로 충분
        logger.info("Static analysis sufficient")
        return StepResult(
            step=WorkflowStep.ANALYZE,
            success=True,
            output={
                "chunks": static_result.chunks,
                "symbols": static_result.symbols,
                "files": static_result.files,
                "analysis_type": "static",
            },
        )
    
    # Phase 2: Semantic Search (느림, 유연)
    logger.info("Falling back to semantic search")
    semantic_result = await context_adapter.search_relevant_code(
        query=query,
        intent=intent,
        top_k=10,
    )
    
    return StepResult(
        step=WorkflowStep.ANALYZE,
        success=True,
        output={
            "chunks": semantic_result.chunks,
            "symbols": await self._extract_symbols(semantic_result),
            "files": list(set(c.file_path for c in semantic_result.chunks)),
            "analysis_type": "semantic",
        },
    )

async def _static_analysis(
    self,
    query: str,
    context_adapter: ContextAdapter
) -> StaticAnalysisResult:
    """Static analysis (Symbol name 기반)"""
    
    # Query에서 Symbol name 추출
    # Example: "Where is calculate_total defined?"
    #          → symbol_name = "calculate_total"
    
    symbol_names = self._extract_symbol_names(query)
    
    if not symbol_names:
        return StaticAnalysisResult(
            confidence=0.0,
            symbols=[],
            chunks=[],
        )
    
    # Symbol Graph에서 직접 검색
    symbols = []
    for name in symbol_names:
        results = await context_adapter.find_symbols_by_name(name)
        symbols.extend(results)
    
    if not symbols:
        return StaticAnalysisResult(confidence=0.0, symbols=[])
    
    # Chunks 가져오기
    chunks = []
    for symbol in symbols:
        chunk = await context_adapter.get_chunk_for_symbol(symbol.id)
        chunks.append(chunk)
    
    return StaticAnalysisResult(
        confidence=0.95,  # Static은 정확
        symbols=symbols,
        chunks=chunks,
        files=list(set(s.file_path for s in symbols)),
    )
```

---

## ADR-004: Sandbox Executor

### 📌 현재 상태: 20%

**완료**:
- ✅ ShadowFS (In-memory overlay)
- ✅ commit/rollback

**미완료**:
- ❌ Sandbox (Docker/containerd)
- ❌ Resource limits
- ❌ Network isolation

### 🎯 구현 계획

#### **Week 6: Sandbox 구축** (20% → 90%)

**Day 41-43: Docker Sandbox**
```python
# src/execution/sandbox/docker_sandbox.py

import docker
from pathlib import Path
from typing import Optional

class DockerSandbox:
    """Docker 기반 격리 실행"""
    
    def __init__(
        self,
        image: str = "python:3.11-slim",
        timeout: int = 30,
        memory_limit: str = "512m",
        cpu_limit: float = 1.0,
        network_mode: str = "none",
    ):
        self.image = image
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.network_mode = network_mode
        
        self.client = docker.from_env()
        
        # Image pull (없으면)
        try:
            self.client.images.get(self.image)
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling image {self.image}...")
            self.client.images.pull(self.image)
    
    async def execute_tests(
        self,
        workspace: Path,
        test_command: str = "pytest -v",
        env: Optional[Dict[str, str]] = None,
    ) -> TestResult:
        """테스트 실행 (격리 환경)"""
        
        logger.info(f"Running tests in sandbox: {test_command}")
        
        try:
            # Container 실행
            container = self.client.containers.run(
                image=self.image,
                command=f"bash -c 'cd /workspace && {test_command}'",
                volumes={
                    str(workspace.absolute()): {
                        "bind": "/workspace",
                        "mode": "ro",  # Read-only!
                    }
                },
                environment=env or {},
                mem_limit=self.memory_limit,
                cpu_period=100000,
                cpu_quota=int(self.cpu_limit * 100000),
                network_mode=self.network_mode,  # No network
                remove=True,  # Auto cleanup
                detach=False,
                timeout=self.timeout,
            )
            
            # stdout 파싱
            stdout = container.decode("utf-8")
            test_result = self._parse_pytest_output(stdout)
            
            logger.info(f"Tests completed: {test_result}")
            return test_result
            
        except docker.errors.ContainerError as e:
            # Container 실행 실패
            logger.error(f"Container error: {e}")
            return TestResult(
                passed=False,
                total=0,
                failed=0,
                error=f"Container error: {e.stderr.decode('utf-8')}",
            )
        
        except docker.errors.APIError as e:
            # Docker API 오류
            logger.error(f"Docker API error: {e}")
            return TestResult(
                passed=False,
                total=0,
                failed=0,
                error=f"Docker error: {e}",
            )
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return TestResult(
                passed=False,
                total=0,
                failed=0,
                error=str(e),
            )
    
    def _parse_pytest_output(self, stdout: str) -> TestResult:
        """pytest 출력 파싱"""
        
        # Example: "3 passed, 1 failed in 0.23s"
        passed = 0
        failed = 0
        
        if "passed" in stdout:
            match = re.search(r"(\d+) passed", stdout)
            if match:
                passed = int(match.group(1))
        
        if "failed" in stdout:
            match = re.search(r"(\d+) failed", stdout)
            if match:
                failed = int(match.group(1))
        
        return TestResult(
            passed=failed == 0,
            total=passed + failed,
            failed=failed,
            output=stdout,
        )
    
    async def execute_lint(
        self,
        workspace: Path,
        lint_command: str = "ruff check .",
    ) -> LintResult:
        """Lint 실행"""
        # 동일한 패턴
        pass
    
    def cleanup(self):
        """정리"""
        self.client.close()
```

**Day 44-45: Workflow 통합**
```python
# src/agent/workflow/state_machine.py

async def _test(self, state: WorkflowState) -> StepResult:
    """실제 테스트 실행 (Sandbox)"""
    
    # ShadowFS → 임시 workspace
    shadow_fs = state.context["shadow_fs"]
    session_id = state.context["session_id"]
    workspace = Path("/tmp/agent_workspace") / session_id
    
    # 실제 파일 생성
    workspace.mkdir(parents=True, exist_ok=True)
    for file_path, content in shadow_fs.overlay.items():
        full_path = workspace / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)
    
    # Sandbox 실행
    sandbox = DockerSandbox(
        timeout=30,
        memory_limit="512m",
    )
    
    try:
        test_result = await sandbox.execute_tests(
            workspace=workspace,
            test_command="pytest -v --tb=short",
        )
        
        return StepResult(
            step=WorkflowStep.TEST,
            success=test_result.passed,
            output=test_result,
            error=test_result.error if not test_result.passed else None,
            metadata={
                "total": test_result.total,
                "failed": test_result.failed,
            }
        )
    
    finally:
        # 정리
        shutil.rmtree(workspace, ignore_errors=True)
        sandbox.cleanup()
```

**Tests**:
```python
# tests/integration/test_sandbox.py

async def test_sandbox_isolation():
    """Network 격리"""
    
    # Network 접근 시도
    workspace = Path("./fixtures/network_test")
    sandbox = DockerSandbox(network_mode="none")
    
    result = await sandbox.execute_tests(
        workspace=workspace,
        test_command="python -c 'import urllib.request; urllib.request.urlopen(\"http://google.com\")'",
    )
    
    # Network 차단 → 실패
    assert not result.passed
    assert "Network" in result.error or "connection" in result.error.lower()

async def test_resource_limits():
    """Memory limit"""
    
    # 1GB 할당 시도
    workspace = Path("./fixtures/memory_test")
    sandbox = DockerSandbox(memory_limit="256m")
    
    result = await sandbox.execute_tests(
        workspace=workspace,
        test_command="python -c 'x = [0] * (1024 ** 3)'",  # 1GB
    )
    
    # Memory limit → 실패
    assert not result.passed

async def test_timeout():
    """Timeout"""
    
    workspace = Path("./fixtures/timeout_test")
    sandbox = DockerSandbox(timeout=5)
    
    result = await sandbox.execute_tests(
        workspace=workspace,
        test_command="python -c 'import time; time.sleep(10)'",  # 10초
    )
    
    # 5초 timeout → 실패
    assert not result.passed
    assert "timeout" in result.error.lower()
```

---

## Week 8: 통합 테스트 + 성능 최적화 (95% → 100%)

### Day 51-53: E2E 통합 테스트

```python
# tests/e2e/test_full_pipeline.py

async def test_bug_fix_e2e():
    """버그 수정 전체 파이프라인"""
    
    # Given: 실제 buggy repo
    repo_path = "./fixtures/buggy_calculator"
    await index_repository("bug_repo", repo_path)
    
    orchestrator = build_production_orchestrator("bug_repo")
    
    # When
    result = await orchestrator.execute(
        user_request="Fix the division by zero bug in calculate()",
        context={
            "repo_id": "bug_repo",
            "enable_full_workflow": True,
        },
    )
    
    # Then
    assert result.is_success()
    assert result.status == ExecutionStatus.COMPLETED
    
    # Layer 0: Context 검색
    assert len(result.metadata["relevant_files"]) > 0
    
    # Layer 1: Router
    assert result.metadata["intent"] in ["fix_bug", "code"]
    
    # Layer 2: Workflow
    assert "task_analyze_bug" in result.tasks_completed
    assert "task_generate_fix" in result.tasks_completed
    
    # MetaLayer: Critic
    assert result.metadata["critic_approved"] == True
    
    # Layer 3: Sandbox
    assert result.metadata["test_result"]["passed"] == True

async def test_feature_add_e2e():
    """기능 추가"""
    
    result = await orchestrator.execute(
        user_request="Add a subtract() function to calculator",
    )
    
    assert result.is_success()
    assert "subtract" in result.result.content

async def test_guardrail_blocks():
    """Guardrail 차단"""
    
    result = await orchestrator.execute(
        user_request="Add 1000 lines of logging to every file",
    )
    
    # Guardrail 차단
    assert result.status == ExecutionStatus.FAILED
    assert "G001" in result.error  # LOC_LIMIT
```

### Day 54-55: 성능 최적화

**Benchmark**:
```python
# tests/performance/test_latency.py

async def test_simple_query_latency():
    """Simple query < 3초"""
    
    start = time.time()
    result = await orchestrator.execute("Find calculate_total")
    latency = time.time() - start
    
    assert latency < 3.0
    assert result.is_success()

async def test_complex_query_latency():
    """Complex query < 10초"""
    
    start = time.time()
    result = await orchestrator.execute(
        "Refactor the entire authentication module",
        context={"enable_full_workflow": True},
    )
    latency = time.time() - start
    
    assert latency < 10.0

async def test_token_efficiency():
    """Token < 10K"""
    
    result = await orchestrator.execute("Explain how user login works")
    
    assert result.tokens_used < 10000
    assert len(result.metadata["relevant_files"]) <= 5
```

**최적화**:
1. Context 병렬 검색 (3개 strategy 병렬)
2. LLM 호출 캐싱 (identical prompts)
3. Chunk deduplication

---

## 📊 성공 지표

| Metric | Target | 현재 | Week 8 목표 |
|--------|--------|------|-------------|
| **ADR-001 진행률** | 100% | 30% | 100% |
| **ADR-002 진행률** | 100% | 90% | 100% |
| **ADR-003 진행률** | 100% | 40% | 100% |
| **ADR-004 진행률** | 100% | 20% | 100% |
| **E2E 테스트** | 10+ | 0 | 15+ |
| **Simple Query Latency** | < 3초 | N/A | 2.5초 |
| **Complex Query Latency** | < 10초 | N/A | 8초 |
| **Token 효율** | < 10K | N/A | 8K |
| **Guardrail 정확도** | 95%+ | N/A | 97% |
| **Test 성공률** | 90%+ | N/A | 95% |

---

## 📁 최종 파일 구조

```
src/
├── agent/
│   ├── orchestrator/
│   │   ├── orchestrator.py          # ✅ Layer 통합
│   │   └── models.py
│   ├── router/
│   │   ├── unified_router.py        # ✅ 실제 Context 사용
│   │   └── models.py
│   ├── workflow/
│   │   ├── state_machine.py         # ✅ Steps 실제 구현
│   │   └── models.py
│   ├── task_graph/
│   │   ├── planner.py               # Rule 기반
│   │   └── dynamic_planner.py       # ✅ LLM 기반
│   └── adapters/
│       └── context_adapter.py       # ✅ Layer 0 Facade
│
├── execution/
│   ├── sandbox/
│   │   ├── docker_sandbox.py        # ✅ Docker 격리
│   │   └── models.py
│   ├── shadowfs/
│   │   └── core.py                  # ✅ 기존
│   ├── code_generation/
│   │   └── generator.py             # ✅ 기존
│   └── validation/
│       └── validator.py             # ✅ 기존
│
├── safety/
│   ├── critic/
│   │   └── code_critic.py           # ✅ M1 LLM 리뷰
│   └── guardrail/
│       ├── rule_engine.py           # ✅ M2 Rule 엔진
│       └── rules.yaml               # ✅ YAML 설정
│
└── contexts/                        # ✅ 기존 (Layer 0)
    ├── retrieval_search/
    ├── code_foundation/
    └── ...

config/
└── guardrail_rules.yaml             # ✅ Guardrail 설정

tests/
├── unit/                            # ✅ 100+ tests
├── integration/                     # ✅ 50+ tests
├── e2e/                             # ✅ 15+ tests
└── performance/                     # ✅ 10+ benchmarks
```

---

## 🚀 다음 단계 (After Week 8)

Core 4개 ADR 완료 후:

1. **ADR-005 (Context Manager)** - Token budget 최적화
2. **ADR-020 (Tool Taxonomy)** - Tools Layer 구축
3. **ADR-011 (Guardrail)** - Org-level overrides
4. **ADR-021 (LLM Routing)** - 모델별 routing

**Milestone**: Core Architecture 100% → Agent MVP 출시 (3개월 차)

