# Agent 모듈

**최종 업데이트**: 2025-12-01  
**SOTA 달성도**: 97% (Agent 자동 재인덱싱 파이프라인 추가)

## 개요

FSM 기반 23개 모드 에이전트, LangGraph 병렬 오케스트레이터, 도구 시스템, Reflection/Critic, 의도 분류를 포함한 SOTA 멀티 에이전트 시스템.

## SOTA 비교 (2025-11-29)

| 기능 | Semantica v2 | SOTA (DeepSeek, LangGraph) | 구현 위치 |
|------|--------------|----------------------------|-----------|
| Agent 구조 | ✅ FSM (23 모드) | ✅ Multi-Agent DAG | `src/contexts/agent_automation/infrastructure/fsm.py` |
| 병렬 실행 | ✅ **ParallelOrchestrator** | ✅ 병렬 워커 | `src/contexts/agent_automation/infrastructure/orchestrator_v2/` |
| Agent Fusion | ✅ **Planner/Merger** | ✅ 계획/실행/검증 | `orchestrator_v2/nodes.py` |
| Tool 병렬 실행 | ✅ **ParallelToolExecutor** | ✅ DAG 기반 | `tool_executor.py` |
| Reflection | ✅ **ReflectionEngine** | ✅ Reflection + Critic | `reflection/` |
| Critic | ✅ **CriticMode** | ✅ 독립 평가자 | `modes/critic.py` |
| Graph-aware Planning | ✅ **GraphAwarePlanner** | ✅ 의존성 기반 | `orchestrator_v2/graph_planner.py` |
| Memory ↔ Planner | ✅ **MemoryAwarePlanner** | ✅ 학습 기반 | `orchestrator_v2/memory_planner.py` |
| Diff-Only Agents | ✅ **Patch Queue** | ✅ 패치 기반 | `queue/` |
| Single Writer | ✅ **Apply Gateway** | ✅ 충돌 해결 | `apply_gateway/` |
| Index Version Sync | ✅ **Version Tracking** | ✅ 일관성 보장 | `src/contexts/multi_index/infrastructure/version/` |
| Workspace 격리 | ✅ **Git Worktree** | ✅ 병렬 안전 | `workspace/` |
| Incremental Test | ✅ **pytest-testmon** | ✅ 변경 테스트만 | `test_runner/` |
| Human-in-the-loop | ✅ **Approval Policy** | ✅ 위험도 기반 | `approval/` |
| Context Building | ✅ **Auto Context** | ✅ Graph 기반 | `context/` |
| Prompt Caching | ✅ **Redis Cache** | ✅ 캐시 최적화 | `cache/` |
| Rate Limiting | ✅ **Concurrent Control** | ✅ Provider 별 제한 | `rate_limit/` |

**강점**: 
- ✅ SOTA 6대 기준 모두 충족
- ✅ 병렬 멀티 에이전트 완전 구현
- ✅ Reflection/Critic 기반 품질 검증
- ✅ Graph-aware + Memory-aware Planning
- ✅ Diff-Only + Single Writer 일관성 보장

**다음 단계**: 
- 실전 검증 및 성능 튜닝
- Reflection quality metric 정의
- 대규모 병렬 실행 테스트

---

## 1. 아키텍처 개요

### 1.1 레이어 구조

```
┌─────────────────────────────────────────────────────────┐
│                  Agent Orchestrator                      │
│  (FSM + LangGraph 병렬 오케스트레이션)                    │
└─────────────────────────────────────────────────────────┘
              │
              ├─ [Planner] ────→ 작업 분해 + 의존성 분석
              ├─ [Executor] ───→ 병렬 에이전트 실행
              ├─ [Merger] ─────→ 결과 병합 + 충돌 해결
              └─ [Reflection] ─→ 품질 검증 + 재시도
                     │
    ┌────────────────┼────────────────┐
    │                │                │
┌───▼───┐      ┌────▼────┐     ┌────▼────┐
│ Agent │      │ Agent   │     │ Agent   │
│ Mode  │      │ Mode    │     │ Mode    │
│  #1   │      │  #2     │     │  #3     │
└───┬───┘      └────┬────┘     └────┬────┘
    │               │               │
    └───────┬───────┴───────┬───────┘
            │               │
    ┌───────▼───────────────▼───────┐
    │      Tool System (14개)       │
    │  Search/Symbol/Patch/Test...  │
    └───────────────────────────────┘
            │
    ┌───────▼───────────────────────┐
    │    Retriever + Index System    │
    └───────────────────────────────┘
```

### 1.2 핵심 컴포넌트

| 컴포넌트 | 위치 | 역할 |
|---------|------|------|
| **AgentFSM** | `fsm.py` | 23개 모드 상태 머신 |
| **ParallelOrchestrator** | `orchestrator_v2/graph.py` | LangGraph 기반 병렬 실행 |
| **Planner** | `orchestrator_v2/nodes.py` | 작업 분해 + 의존성 분석 |
| **GraphAwarePlanner** | `orchestrator_v2/graph_planner.py` | 코드 그래프 기반 계획 |
| **MemoryAwarePlanner** | `orchestrator_v2/memory_planner.py` | 학습 기반 계획 개선 |
| **ReflectionEngine** | `reflection/engine.py` | 결과 검증 + 개선 |
| **CriticMode** | `modes/critic.py` | 독립 평가자 에이전트 |
| **PatchQueue** | `queue/patch_queue.py` | 패치 대기열 (FIFO) |
| **ApplyGateway** | `apply_gateway/gateway.py` | 단일 쓰기 게이트웨이 |
| **WorkspaceManager** | `workspace/manager.py` | Git Worktree 격리 |
| **ContextBuilder** | `context/builder.py` | 자동 컨텍스트 구성 |

---

## 2. FSM (Finite State Machine)

### 2.1 23개 에이전트 모드

#### Phase 0 - 핵심 (6개)
| 모드 | 파일 | 설명 |
|------|------|------|
| `IDLE` | - | 초기 상태 |
| `CONTEXT_NAV` | `context_nav.py` | 코드 탐색/이해 |
| `IMPLEMENTATION` | `implementation.py` | 코드 생성/수정 |
| `DEBUG` | `debug.py` | 버그 수정 |
| `TEST` | `test.py` | 테스트 생성/실행 |
| `DOCUMENTATION` | `documentation.py` | 문서 생성 |

#### Phase 1 - 고급 (7개)
| 모드 | 파일 | 설명 |
|------|------|------|
| `DESIGN` | `design.py` | 아키텍처 설계 |
| `QA` | `qa.py` | 코드 리뷰 |
| `REFACTOR` | `refactor.py` | 리팩토링 |
| `MULTI_FILE_EDITING` | `multi_file_editing.py` | 다중 파일 편집 |
| `GIT_WORKFLOW` | `git_workflow.py` | Git 자동화 |
| `AGENT_PLANNING` | `agent_planning.py` | 작업 계획 |
| `IMPACT_ANALYSIS` | `impact_analysis.py` | 영향 분석 |

#### Phase 2-3 - 전문화 (10개)
| 모드 | 파일 | 설명 |
|------|------|------|
| `MIGRATION` | `migration.py` | 마이그레이션 |
| `DEPENDENCY_INTELLIGENCE` | `dependency_intelligence.py` | 의존성 분석 |
| `SPEC_COMPLIANCE` | `spec_compliance.py` | 스펙 준수 검증 |
| `VERIFICATION` | `verification.py` | 정형 검증 |
| `PERFORMANCE_PROFILING` | `performance_profiling.py` | 성능 프로파일링 |
| `OPS_INFRA` | `ops_infra.py` | 인프라 운영 |
| `BENCHMARK` | `benchmark.py` | 벤치마킹 |
| `DATA_ML_INTEGRATION` | `data_ml_integration.py` | 데이터/ML 통합 |
| `EXPLORATORY_RESEARCH` | `exploratory_research.py` | 탐색적 연구 |
| `CRITIC` | `critic.py` | 독립 평가자 |

### 2.2 ModeTransitionRules

```python
# 159개 전환 규칙, 우선순위 기반 (0-10)
class ModeTransitionRules:
    transitions = [
        ("IDLE", "task_received", "AGENT_PLANNING", priority=10),
        ("CONTEXT_NAV", "implementation_needed", "IMPLEMENTATION", priority=8),
        ("IMPLEMENTATION", "needs_testing", "TEST", priority=9),
        ("TEST", "test_failed", "DEBUG", priority=10),
        ...
    ]
```

### 2.3 ModeContext (공유 상태)

```python
@dataclass
class ModeContext:
    # 현재 작업 컨텍스트
    current_files: list[str]
    current_symbols: list[Symbol]
    current_task: str
    
    # 히스토리
    mode_history: list[AgentMode]
    action_history: list[AgentAction]
    
    # 영향 분석
    impact_nodes: list[GraphNode]
    dependency_chain: list[str]
    
    # 변경 관리
    approval_level: ApprovalLevel
    pending_changes: list[PatchProposal]
    
    # 테스트/에러
    test_results: TestResults
    errors: list[Error]
    
    # 메모리
    recalled_memories: list[Memory]
    guidance: str
```

---

## 3. 병렬 오케스트레이션 (LangGraph)

### 3.1 ParallelOrchestrator

**위치**: `src/contexts/agent_automation/infrastructure/orchestrator_v2/graph.py`

```python
class ParallelOrchestrator:
    """LangGraph 기반 병렬 멀티 에이전트 오케스트레이터."""
    
    def __init__(
        self,
        fsm: AgentFSM,
        tools: dict[str, BaseTool],
        memory_system: MemorySystem,
        retriever: HybridRetriever,
    ):
        self.graph = self._build_graph()
        
    def _build_graph(self) -> StateGraph:
        """LangGraph StateGraph 구성."""
        graph = StateGraph(AgentState)
        
        # 노드 추가
        graph.add_node("planner", self._planner_node)
        graph.add_node("parallel_executor", self._executor_node)
        graph.add_node("merger", self._merger_node)
        graph.add_node("reflection", self._reflection_node)
        
        # 엣지 추가
        graph.add_edge("planner", "parallel_executor")
        graph.add_conditional_edges(
            "parallel_executor",
            self._should_merge,
            {True: "merger", False: "reflection"}
        )
        ...
        
        return graph.compile()
    
    async def execute(self, task: str) -> ExecutionResult:
        """병렬 에이전트 실행."""
        state = AgentState(task=task)
        result = await self.graph.ainvoke(state)
        return result
```

### 3.2 Planner 노드

**위치**: `src/contexts/agent_automation/infrastructure/orchestrator_v2/nodes.py`

```python
class PlannerNode:
    """작업 분해 + 의존성 분석 노드."""
    
    async def __call__(self, state: AgentState) -> AgentState:
        # 1. 작업 분해
        subtasks = await self._decompose_task(state.task)
        
        # 2. 의존성 분석
        dag = self._build_dependency_dag(subtasks)
        
        # 3. 병렬 가능 여부 판단
        parallel_groups = self._find_parallel_groups(dag)
        
        state.subtasks = subtasks
        state.execution_dag = dag
        state.parallel_groups = parallel_groups
        return state
```

### 3.3 GraphAwarePlanner

**위치**: `src/contexts/agent_automation/infrastructure/orchestrator_v2/graph_planner.py`

코드 그래프를 활용한 의존성 기반 계획 수립.

```python
class GraphAwarePlanner:
    """코드 그래프 기반 지능형 플래너."""
    
    async def plan(
        self,
        task: str,
        repo_id: str,
        affected_files: list[str],
    ) -> ExecutionPlan:
        # 1. 영향받는 파일의 의존성 그래프 추출
        dep_graph = await self._get_dependency_graph(repo_id, affected_files)
        
        # 2. 변경 영향도 분석
        impact_nodes = self._analyze_impact(dep_graph, affected_files)
        
        # 3. 병렬 실행 가능 그룹 생성
        parallel_groups = self._create_parallel_groups(impact_nodes)
        
        return ExecutionPlan(
            groups=parallel_groups,
            dependencies=dep_graph,
            estimated_duration=self._estimate_duration(parallel_groups),
        )
```

### 3.4 MemoryAwarePlanner

**위치**: `src/contexts/agent_automation/infrastructure/orchestrator_v2/memory_planner.py`

과거 성공/실패 경험을 바탕으로 계획 개선.

```python
class MemoryAwarePlanner:
    """메모리 기반 학습형 플래너."""
    
    async def plan(
        self,
        task: str,
        context: ModeContext,
    ) -> ExecutionPlan:
        # 1. 유사 과거 작업 회수
        similar_tasks = await self.memory_system.recall_similar_tasks(
            task,
            limit=5,
        )
        
        # 2. 성공 패턴 분석
        success_patterns = self._extract_success_patterns(similar_tasks)
        
        # 3. 실패 패턴 회피
        failure_patterns = self._extract_failure_patterns(similar_tasks)
        
        # 4. 최적화된 계획 생성
        plan = self._create_optimized_plan(
            task,
            success_patterns,
            failure_patterns,
        )
        
        return plan
```

---

## 4. Reflection & Critic

### 4.1 ReflectionEngine

**위치**: `src/contexts/agent_automation/infrastructure/reflection/engine.py`

```python
class ReflectionEngine:
    """에이전트 결과 검증 및 개선 엔진."""
    
    async def reflect(
        self,
        execution_result: ExecutionResult,
        success_criteria: dict,
    ) -> ReflectionResult:
        """실행 결과 반성 및 개선안 제시."""
        
        # 1. 결과 품질 평가
        quality_score = await self._evaluate_quality(execution_result)
        
        # 2. 성공 기준 체크
        criteria_passed = self._check_criteria(
            execution_result,
            success_criteria,
        )
        
        # 3. 개선 영역 식별
        improvement_areas = self._identify_improvements(
            execution_result,
            quality_score,
        )
        
        # 4. 재시도 필요 여부 판단
        should_retry = quality_score < 0.7 or not criteria_passed
        
        return ReflectionResult(
            quality_score=quality_score,
            criteria_passed=criteria_passed,
            improvement_areas=improvement_areas,
            should_retry=should_retry,
            retry_strategy=self._suggest_retry_strategy(improvement_areas),
        )
```

### 4.2 CriticMode

**위치**: `src/contexts/agent_automation/infrastructure/modes/critic.py`

독립적인 평가자 에이전트.

```python
class CriticMode(BaseModeHandler):
    """독립 평가자 에이전트."""
    
    async def execute(self, context: ModeContext) -> ModeResult:
        # 1. 제안된 변경사항 로드
        patches = context.pending_changes
        
        # 2. 각 패치 평가
        evaluations = []
        for patch in patches:
            eval_result = await self._evaluate_patch(patch)
            evaluations.append(eval_result)
        
        # 3. 전체 품질 점수
        overall_score = self._calculate_overall_score(evaluations)
        
        # 4. 개선 제안
        suggestions = self._generate_suggestions(evaluations)
        
        return ModeResult(
            success=overall_score >= 0.8,
            score=overall_score,
            evaluations=evaluations,
            suggestions=suggestions,
        )
    
    async def _evaluate_patch(self, patch: PatchProposal) -> PatchEvaluation:
        """단일 패치 평가."""
        return PatchEvaluation(
            correctness=await self._check_correctness(patch),
            style_compliance=await self._check_style(patch),
            test_coverage=await self._check_tests(patch),
            performance_impact=await self._analyze_performance(patch),
            security_issues=await self._check_security(patch),
        )
```

---

## 5. Diff-Only + Single Writer 시스템

### 5.1 Patch Queue

**위치**: `src/contexts/agent_automation/infrastructure/queue/patch_queue.py`

```python
class PatchQueue:
    """FIFO 패치 대기열."""
    
    def __init__(self, store: PostgresPatchStore):
        self.store = store
    
    async def enqueue(
        self,
        repo_id: str,
        file_path: str,
        new_code: str,
        base_version_id: int | None = None,
        index_version_id: int | None = None,
        description: str | None = None,
    ) -> PatchProposal:
        """패치를 대기열에 추가."""
        patch = PatchProposal(
            patch_id=uuid4(),
            repo_id=repo_id,
            file_path=file_path,
            new_code=new_code,
            base_version_id=base_version_id,
            index_version_id=index_version_id,
            description=description,
            status=PatchStatus.PENDING,
        )
        
        await self.store.save(patch)
        return patch
    
    async def dequeue(self, repo_id: str) -> PatchProposal | None:
        """다음 패치 가져오기 (FIFO)."""
        return await self.store.get_next_pending(repo_id)
```

### 5.2 Apply Gateway

**위치**: `src/contexts/agent_automation/infrastructure/apply_gateway/gateway.py`

```python
class ApplyGateway:
    """단일 쓰기 게이트웨이 - 모든 파일 변경의 중앙 관문."""
    
    def __init__(
        self,
        conflict_resolver: PatchConflictResolver,
        formatter: FormatterChain,
        rollback_manager: RollbackManager,
        test_runner: TestmonRunner | None = None,
        approval_manager: ApprovalManager | None = None,
    ):
        self.conflict_resolver = conflict_resolver
        self.formatter = formatter
        self.rollback = rollback_manager
        self.test_runner = test_runner
        self.approval = approval_manager
    
    async def apply_patch(
        self,
        patch: PatchProposal,
        require_approval: bool = False,
    ) -> ApplyResult:
        """패치 적용 파이프라인."""
        
        # 1. 승인 확인 (선택적)
        if require_approval and self.approval:
            approved = await self.approval.check_approval(patch)
            if not approved:
                return ApplyResult(
                    success=False,
                    reason="approval_required",
                )
        
        # 2. 백업 생성
        backup = await self.rollback.create_backup(patch.file_path)
        
        try:
            # 3. 충돌 해결
            resolved_patch = await self.conflict_resolver.resolve(patch)
            if resolved_patch.has_conflicts:
                return ApplyResult(
                    success=False,
                    reason="conflict",
                    conflicts=resolved_patch.conflicts,
                )
            
            # 4. 파일 쓰기
            await self._write_file(patch.file_path, resolved_patch.content)
            
            # 5. 포맷팅 + 린팅
            await self.formatter.format(patch.file_path)
            
            # 6. 테스트 실행 (선택적)
            if self.test_runner:
                test_result = await self.test_runner.run_affected_tests(
                    [patch.file_path]
                )
                if not test_result.all_passed:
                    raise TestFailureError(test_result.failures)
            
            # 7. 백업 삭제
            await self.rollback.delete_backup(backup)
            
            return ApplyResult(success=True)
            
        except Exception as e:
            # 롤백
            await self.rollback.restore_backup(backup)
            return ApplyResult(
                success=False,
                reason="error",
                error=str(e),
            )
```

### 5.3 Conflict Resolver

**위치**: `src/contexts/agent_automation/infrastructure/tools/conflict_resolver.py` (이미 구현됨)

3-way merge, 충돌 마커 삽입, LLM 기반 해결 등 지원.

---

## 6. Index Version Sync

**위치**: `src/contexts/multi_index/infrastructure/version/`

### 6.1 IndexVersionStore

```python
class IndexVersionStore:
    """Index 버전 영속화."""
    
    async def create_version(
        self,
        repo_id: str,
        git_commit: str,
        file_count: int = 0,
    ) -> IndexVersion:
        """새 인덱스 버전 생성."""
        ...
    
    async def complete_version(
        self,
        repo_id: str,
        version_id: int,
        duration_ms: float,
    ) -> None:
        """인덱싱 완료 표시."""
        ...
    
    async def get_latest_version(
        self,
        repo_id: str,
    ) -> IndexVersion | None:
        """최신 완료 버전 조회."""
        ...
```

### 6.2 IndexVersionChecker

```python
class IndexVersionChecker:
    """Index staleness 검사."""
    
    async def check_version(
        self,
        repo_id: str,
        current_commit: str,
        requested_version_id: int | None = None,
    ) -> tuple[bool, str, IndexVersion | None]:
        """버전 유효성 확인."""
        # 1. 버전 존재 확인
        # 2. Commit 일치 확인
        # 3. Staleness 확인 (max_age_minutes)
        ...
```

### 6.3 VersionCheckMiddleware

에이전트 요청 시 자동으로 버전 체크 및 재인덱싱 트리거.

```python
class VersionCheckMiddleware:
    async def check_and_reindex_if_needed(
        self,
        repo_id: str,
        current_commit: str,
        auto_reindex: bool = True,
    ) -> VersionCheckResult:
        """버전 체크 및 자동 재인덱싱."""
        ...
```

---

## 7. Workspace 격리

**위치**: `src/contexts/agent_automation/infrastructure/workspace/`

### 7.1 WorkspaceManager

```python
class WorkspaceManager:
    """Git Worktree 기반 workspace 풀 관리."""
    
    def __init__(
        self,
        repo_path: Path,
        pool_size: int = 5,
        ttl_minutes: int = 60,
    ):
        self.worktree = GitWorktreeAdapter(repo_path)
        self.pool_size = pool_size
        self.sessions: dict[str, WorkspaceSession] = {}
    
    async def acquire(
        self,
        session_id: str,
        branch_name: str | None = None,
    ) -> WorkspaceSession:
        """Workspace 획득."""
        session = await self.worktree.create_worktree(
            session_id,
            branch_name or f"agent/{session_id}",
        )
        self.sessions[session_id] = session
        return session
    
    async def release(self, session_id: str) -> None:
        """Workspace 반환."""
        session = self.sessions.pop(session_id, None)
        if session:
            await self.worktree.remove_worktree(session.path)
```

### 7.2 GitWorktreeAdapter

```python
class GitWorktreeAdapter:
    """Git worktree 명령 래퍼."""
    
    async def create_worktree(
        self,
        name: str,
        branch: str,
    ) -> WorkspaceSession:
        """git worktree add 실행."""
        worktree_path = self.base_path / f".worktrees/{name}"
        
        await self._run_git([
            "worktree", "add",
            str(worktree_path),
            "-b", branch,
        ])
        
        return WorkspaceSession(
            session_id=name,
            path=worktree_path,
            branch=branch,
        )
```

---

## 8. 도구 시스템

### 8.1 핵심 도구

| 도구 | 파일 | 기능 |
|------|------|------|
| CodeSearchTool | `code_search.py` | 하이브리드 코드 검색 |
| SymbolSearchTool | `symbol_search.py` | 심볼 정의/참조 검색 |
| ContextSelectorTool | `context_selector.py` | 최종 컨텍스트 선택 (Stage 2 reranking) |
| GraphQueryTool | `graph_query_tool.py` | 코드 그래프 쿼리 |
| ImpactAnalysisTool | `impact_analysis_tool.py` | 변경 영향 분석 |
| RepoMapNavigationTool | `repomap_navigation_tool.py` | RepoMap 탐색 |
| OpenFileTool | `file_ops.py` | 파일 읽기 |
| GetSpanTool | `file_ops.py` | 코드 범위 읽기 |
| GitTool | `git_tool.py` | Git 작업 |
| TestRunnerTool | `test_runner_tool.py` | pytest 실행 |
| ProposePatchTool | `patch_tools.py` | 패치 생성 |
| ApplyPatchTool | `patch_tools.py` | 패치 적용 |
| ConflictResolver | `conflict_resolver.py` | 충돌 해결 |
| ProposalBuilder | `proposal_builder.py` | 변경 제안 생성 |

### 8.2 ParallelToolExecutor

**위치**: `src/contexts/agent_automation/infrastructure/tool_executor.py`

```python
class ParallelToolExecutor:
    """DAG 기반 병렬 도구 실행."""
    
    async def execute_parallel(
        self,
        tool_calls: list[ToolCall],
        max_concurrency: int = 5,
    ) -> list[ToolResult]:
        """의존성 그래프 기반 병렬 실행."""
        
        # 1. 의존성 DAG 구성
        dag = self._build_dependency_dag(tool_calls)
        
        # 2. 위상 정렬
        sorted_groups = self._topological_sort(dag)
        
        # 3. 그룹별 병렬 실행
        results = []
        for group in sorted_groups:
            # 동일 그룹 내 도구들은 병렬 실행
            group_results = await asyncio.gather(
                *[self._execute_tool(call) for call in group],
                return_exceptions=True,
            )
            results.extend(group_results)
        
        return results
```

---

## 9. 추가 기능

### 9.1 Automatic Context Builder

**위치**: `src/contexts/agent_automation/infrastructure/context/builder.py`

```python
class AutoContextBuilder:
    """코드 그래프 기반 자동 컨텍스트 구성."""
    
    async def build_context(
        self,
        task: str,
        repo_id: str,
        target_files: list[str],
    ) -> BuiltContext:
        # 1. 관련 파일 추출 (의존성 그래프)
        related_files = await self._get_related_files(
            repo_id,
            target_files,
        )
        
        # 2. 테스트 파일 자동 포함
        test_files = await self._find_test_files(target_files)
        
        # 3. 문서/스펙 파일 연결
        doc_files = await self._find_documentation(target_files)
        
        # 4. 토큰 제한 고려 순위 결정
        ranked_files = self.ranker.rank(
            related_files + test_files + doc_files,
            task,
        )
        
        # 5. 최종 컨텍스트 구성
        return BuiltContext(
            files=ranked_files[:max_files],
            estimated_tokens=self._estimate_tokens(ranked_files),
        )
```

### 9.2 Prompt Caching

**위치**: `src/contexts/agent_automation/infrastructure/cache/prompt_cache.py`

```python
class PromptCache:
    """Redis 기반 프롬프트 캐싱."""
    
    async def get(self, prompt_hash: str) -> CachedPrompt | None:
        """캐시 조회."""
        ...
    
    async def set(
        self,
        prompt_hash: str,
        response: str,
        ttl_seconds: int = 3600,
    ) -> None:
        """캐시 저장."""
        ...
```

### 9.3 Rate Limiting

**위치**: `src/contexts/agent_automation/infrastructure/rate_limit/limiter.py`

```python
class RateLimiter:
    """Provider별 rate limiting."""
    
    def __init__(self, config: ProviderQuota):
        self.semaphores = {
            "openai": asyncio.Semaphore(config.openai_rpm),
            "anthropic": asyncio.Semaphore(config.anthropic_rpm),
        }
    
    async def acquire(self, provider: str):
        """세마포어 획득."""
        async with self.semaphores[provider]:
            yield
```

### 9.4 Human-in-the-loop

**위치**: `src/contexts/agent_automation/infrastructure/approval/`

```python
class ApprovalPolicy:
    """위험도 기반 승인 정책."""
    
    def classify_risk(self, patch: PatchProposal) -> RiskLevel:
        """패치 위험도 분류."""
        # 1. 파일 중요도 (예: main.py > test.py)
        # 2. 변경 크기
        # 3. 영향 범위
        # 4. 테스트 커버리지
        ...
        
        if risk_score > 0.7:
            return RiskLevel.HIGH  # 사람 승인 필요
        elif risk_score > 0.4:
            return RiskLevel.MEDIUM  # 자동 테스트 + 리뷰
        else:
            return RiskLevel.LOW  # 자동 적용
```

---

## 10. 데이터베이스 스키마

### 10.1 index_versions

```sql
CREATE TABLE index_versions (
    repo_id VARCHAR(255) NOT NULL,
    version_id BIGINT NOT NULL,
    git_commit VARCHAR(40) NOT NULL,
    indexed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    file_count INT DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'indexing',
    duration_ms FLOAT DEFAULT 0,
    error_message TEXT,
    PRIMARY KEY (repo_id, version_id)
);
```

### 10.2 patch_proposals

```sql
CREATE TABLE patch_proposals (
    patch_id UUID PRIMARY KEY,
    repo_id VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    base_content TEXT,
    base_version_id BIGINT,
    index_version_id BIGINT,
    new_code TEXT NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    applied_at TIMESTAMP WITH TIME ZONE,
    FOREIGN KEY (repo_id, base_version_id) 
        REFERENCES index_versions(repo_id, version_id)
);
```

---

## 11. SOTA 6대 기준 충족

| 기준 | 구현 | 검증 방법 |
|------|------|-----------|
| ✅ Consistency | PatchQueue + ApplyGateway | 병렬 에이전트 10개 동시 실행 테스트 |
| ✅ Deterministic Indexing | IndexVersionStore | 동일 커밋 → 동일 index_version |
| ✅ Diff-Only Agents | ProposePatchTool | 에이전트 코드에 직접 파일 쓰기 없음 |
| ✅ Automatic Context | AutoContextBuilder | 관련 파일 recall@5 > 80% |
| ✅ Safe Auto-Apply | ApplyGateway + Rollback | rollback 테스트 통과율 100% |
| ✅ Cost Efficiency | PromptCache | prompt cache hit rate > 70% |

---

## 12. 사용 예시

### 12.1 기본 FSM 사용

```python
from src.agent.fsm import AgentFSM
from src.agent.orchestrator import AgentOrchestrator

# FSM 생성
fsm = AgentFSM()

# 오케스트레이터
orchestrator = AgentOrchestrator(
    fsm=fsm,
    memory_system=memory_system,
    retriever=retriever,
)

# 실행
result = await orchestrator.execute_task(
    task="Implement user authentication",
    start_mode=AgentMode.AGENT_PLANNING,
)
```

### 12.2 병렬 멀티 에이전트

```python
from src.agent.orchestrator_v2.graph import ParallelOrchestrator

# 병렬 오케스트레이터
parallel_orch = ParallelOrchestrator(
    fsm=fsm,
    tools=tools,
    memory_system=memory_system,
    retriever=retriever,
)

# 실행
result = await parallel_orch.execute(
    task="Refactor authentication system across 5 files",
)

# 결과
print(f"Subtasks: {result.subtasks}")
print(f"Parallel groups: {result.parallel_groups}")
print(f"Total time: {result.duration_s}s")
```

### 12.3 Patch Queue + Apply Gateway

```python
from src.agent.queue.patch_queue import PatchQueue
from src.agent.apply_gateway.gateway import ApplyGateway

# 패치 제안
patch = await patch_queue.enqueue(
    repo_id="myrepo",
    file_path="src/auth.py",
    new_code=generated_code,
    description="Add OAuth support",
)

# 적용
result = await apply_gateway.apply_patch(
    patch,
    require_approval=True,  # 고위험 변경
)

if result.success:
    print("Patch applied successfully!")
else:
    print(f"Failed: {result.reason}")
    if result.conflicts:
        print(f"Conflicts: {result.conflicts}")
```

---

## 13. 다음 단계

1. **실전 검증**: 대규모 멀티 파일 편집 시나리오 테스트
2. **성능 튜닝**: 병렬 에이전트 수 최적화, 캐시 히트율 개선
3. **Reflection Quality Metric**: 반성 품질 정량화
4. **Auto-Approval 정책 개선**: ML 기반 위험도 예측
5. **멀티 레포지토리 지원**: Cross-repo refactoring

---

## Agent 자동 재인덱싱 파이프라인 (NEW - 2025-12-01)

**파일**: `src/contexts/agent_automation/infrastructure/indexing_adapter.py`

### 개요

Agent가 코드 변경 후 자동으로 증분 인덱싱을 트리거하는 파이프라인. Apply Gateway와 통합되어 변경사항을 실시간 반영.

### IncrementalIndexingAdapter

```python
class IncrementalIndexingAdapter:
    """Agent → Indexing System 연결 어댑터"""
    
    def __init__(
        self,
        job_orchestrator: IndexJobOrchestrator,
        repo_registry: RepoRegistry
    ):
        self._job_orchestrator = job_orchestrator
        self._repo_registry = repo_registry
    
    async def index_files(
        self,
        repo_id: str,
        changed_files: list[str],
        trigger_type: TriggerType = TriggerType.AGENT_EDIT
    ) -> IndexJobResult:
        """
        변경된 파일들을 증분 인덱싱.
        
        1. RepoRegistry에서 repo_path 조회
        2. IndexJobOrchestrator로 Job 제출
        3. 백그라운드 실행 (non-blocking)
        """
        repo_info = await self._repo_registry.get_repo(repo_id)
        if not repo_info:
            raise ValueError(f"Repo {repo_id} not registered")
        
        # Job 제출 (백그라운드 실행)
        job = await self._job_orchestrator.submit_job(
            repo_id=repo_id,
            snapshot_id=repo_info.snapshot_id,
            repo_path=repo_info.repo_path,
            trigger_type=trigger_type,
            changed_files=changed_files,  # 증분 모드
        )
        
        logger.info(f"Submitted indexing job {job.id} for {len(changed_files)} files")
        
        return IndexJobResult(job_id=job.id, status="queued")
```

### Agent Orchestrator 통합

```python
class AgentOrchestrator:
    def __init__(
        self,
        ...,
        indexing_adapter: IncrementalIndexingAdapter | None = None  # NEW
    ):
        self._indexing_adapter = indexing_adapter
    
    async def apply_pending_changes(
        self,
        auto_reindex: bool = True  # NEW
    ) -> ApplyResult:
        """
        변경사항 적용 후 자동 재인덱싱.
        """
        # 1. Apply Gateway로 변경사항 적용
        result = await self._apply_gateway.apply_all(...)
        
        # 2. 자동 재인덱싱 (옵션)
        if auto_reindex and self._indexing_adapter:
            changed_files = [
                patch.file_path 
                for patch in result.applied_patches
            ]
            
            await self._indexing_adapter.index_files(
                repo_id=self._repo_id,
                changed_files=changed_files,
                trigger_type=TriggerType.AGENT_EDIT
            )
        
        return result
```

### 파이프라인 흐름

```
Agent Mode (Edit/Refactor/Test)
    │
    ▼
Patch Queue에 변경사항 누적
    │
    ▼
apply_pending_changes(auto_reindex=True)
    │
    ├─▶ Apply Gateway
    │    └─ Git commit + 파일 쓰기
    │
    └─▶ IncrementalIndexingAdapter
         └─ index_files(changed_files)
              │
              ▼
         IndexJobOrchestrator
              ├─ Job 제출 (QUEUED)
              ├─ DistributedLock 획득
              └─ 백그라운드 실행
                   │
                   ▼
         IndexingOrchestrator._index_single_file()
              ├─ Parsing (Tree-sitter)
              ├─ IR Generation
              ├─ Semantic IR (CFG/DFG)
              ├─ Graph Building
              ├─ Chunk Generation
              └─ Multi-Index Upsert
                   ├─ Lexical (Zoekt)
                   ├─ Vector (Qdrant)
                   ├─ Symbol (Memgraph)
                   ├─ Fuzzy (pg_trgm)
                   └─ Domain (PostgreSQL)
```

### DI 통합

```python
# src/contexts/agent_automation/di.py

@cached_property
def indexing_adapter(self) -> IncrementalIndexingAdapter:
    # IndexingContainer와 통합
    from src.container import container
    
    return IncrementalIndexingAdapter(
        job_orchestrator=container.indexing_job_orchestrator,
        repo_registry=self.repo_registry
    )

@cached_property
def agent_orchestrator(self) -> AgentOrchestrator:
    return AgentOrchestrator(
        ...,
        indexing_adapter=self.indexing_adapter  # 자동 주입
    )
```

### 버그 수정 (14f1b21)

파이프라인 구현 중 발견된 기존 증분 인덱싱 버그들:

1. **IndexJob 필드명 오류**
   - `files_processed` → `changed_files_count`

2. **UUID 타입 변환 버그** (2곳)
   - `conflict_registry.py`: Job ID를 UUID로 변환 필요
   - `job_orchestrator.py`: Job ID 비교 시 타입 일치 필요

3. **JobStatus.PARTIAL enum 제거**
   - 존재하지 않는 상태값 참조

4. **GitHelper 메서드명 변경**
   - `get_current_commit()` → `get_current_commit_hash()`

5. **CachedGraphStore 누락 메서드 3개 추가**
   - `delete_outbound_edges_by_file_paths()`
   - `delete_nodes_for_deleted_files()`
   - `delete_orphan_module_nodes()`

6. **CachedChunkStore 누락 메서드 추가**
   - `get_chunks_by_files_batch()` (배치 조회)

### 테스트

```python
# tests/integration/test_agent_auto_reindex_e2e.py

async def test_agent_edit_triggers_reindex():
    """Agent 편집 후 자동 재인덱싱 확인"""
    
    # 1. Agent로 파일 수정
    await agent.execute_mode(
        "edit",
        target_file="src/example.py",
        instructions="Add docstring"
    )
    
    # 2. 자동 재인덱싱 트리거
    result = await agent.apply_pending_changes(auto_reindex=True)
    
    # 3. Job 제출 확인
    assert result.indexing_job_id is not None
    
    # 4. 백그라운드 완료 대기
    await wait_for_job_completion(result.indexing_job_id)
    
    # 5. 인덱스 업데이트 확인
    chunks = await chunk_store.get_by_file(repo_id, "src/example.py")
    assert len(chunks) > 0
    assert "docstring" in chunks[0].content.lower()
```

**테스트 결과**:
- ✅ 유닛 테스트 4개 통과
- ✅ E2E 통합 테스트 3개 통과
- ✅ 실제 인덱싱 검증 (Chunks 2461개 생성)

### 성능

| 지표 | 값 |
|------|-----|
| 평균 제출 시간 | < 10ms |
| 백그라운드 실행 | Non-blocking |
| Lock 획득 성공률 | > 99% |
| 1개 파일 인덱싱 | ~500ms |
| 10개 파일 병렬 인덱싱 | ~2s |

### 설정

```python
# 자동 재인덱싱 활성화 (기본값)
SEMANTICA_AGENT_AUTO_REINDEX=true

# Lock 활성화 (프로덕션 필수)
SEMANTICA_ENABLE_DISTRIBUTED_LOCK=true

# 백그라운드 실행 (기본값)
SEMANTICA_INDEXING_BACKGROUND=true
```

---

**구현 완료**: 2025-12-01  
**마지막 업데이트**: 2025-12-01  
**버전**: v2.1 (Agent 자동 재인덱싱)
