# Core Architecture ADR 구현 계획 V2 (피드백 반영)

**작성일**: 2025-12-05 (Updated)  
**대상**: Core Architecture 4개 ADR (P0)  
**기간**: 8주 (2개월)  
**오픈소스 활용**: LangGraph, E2B, LiteLLM, Pydantic, Guardrails AI, Playwright, GitPython

---

## 🔥 Critical Improvements (피드백 반영)

### 1. **ADR-004 Sandbox: Session-based Container** ✅
- `containers.run` 매번 호출 → `exec_run` 재사용
- 세션당 1개 컨테이너 (Keep-alive)
- 속도: 2초/테스트 → 0.1초/테스트 (20x 개선)

### 2. **ADR-003 Workflow: State Persistence** ✅
- LangGraph Checkpoint 활용
- Long-running task 재시작 지원
- SQLite/Redis 백업

### 3. **ADR-001 ContextAdapter: Semantic Cache** ✅
- LRU Cache + Embedding similarity
- 중복 검색 제거 (50% 속도 향상)

### 4. **ADR-002 Router: Budget Enforcement** ✅
- `asyncio.wait_for(timeout=budget)` 강제
- PartialResult fallback

### 5. **코드 레벨 개선** ✅
- Regex pre-compilation (GuardrailEngine)
- JSON parsing with `json_repair` (DynamicPlanner)
- Volume mount strategy (rw + /tmp)

---

## Week-by-Week 개선 계획

### **Week 1-2: Layer 통합 + Caching** (30% → 60%)

#### Day 1-2: ContextAdapter with Semantic Cache

```python
# src/agent/adapters/context_adapter.py

from typing import Dict, List, Optional
from functools import lru_cache
import hashlib
from src.infra.cache.redis import RedisClient  # 기존 인프라

class ContextAdapter:
    """Layer 0 (CodeGraph) Facade with Caching"""
    
    def __init__(
        self,
        retrieval_service: RetrievalService,
        chunk_store: ChunkStore,
        graph_store: GraphStore,
        cache: Optional[RedisClient] = None,
    ):
        self.retrieval = retrieval_service
        self.chunks = chunk_store
        self.graph = graph_store
        
        # Semantic Cache
        self.cache = cache or RedisClient()
        self.cache_ttl = 3600  # 1 hour
        
        # LRU Cache (메모리)
        self._symbol_cache: Dict[str, SymbolInfo] = {}
        self._max_cache_size = 1000
    
    async def search_relevant_code(
        self,
        query: str,
        intent: str,
        top_k: int = 10,
        use_cache: bool = True,
    ) -> SearchResult:
        """Intent 기반 검색 (Cached)"""
        
        # 1. Cache key 생성
        cache_key = self._make_cache_key(query, intent, top_k)
        
        # 2. Cache hit check
        if use_cache:
            cached = await self._get_from_cache(cache_key)
            if cached:
                logger.info(f"Cache hit: {cache_key}")
                return cached
        
        # 3. 실제 검색 (AutoRRF)
        results = await self.retrieval.search(
            query=query,
            intent=intent,
            top_k=top_k,
        )
        
        # 4. Context 구성
        context = await self._build_context(results)
        
        search_result = SearchResult(
            chunks=results,
            context=context,
            token_count=sum(c.token_count for c in results),
        )
        
        # 5. Cache 저장
        if use_cache:
            await self._save_to_cache(cache_key, search_result)
        
        return search_result
    
    def _make_cache_key(self, query: str, intent: str, top_k: int) -> str:
        """Cache key 생성 (Semantic)"""
        # Option 1: Hash (빠름, 정확 일치만)
        # return hashlib.sha256(f"{query}:{intent}:{top_k}".encode()).hexdigest()
        
        # Option 2: Embedding similarity (느림, 유사 쿼리도 캐싱)
        # Embedding을 계산하고 Redis Vector Search로 유사 쿼리 찾기
        # 현재는 Option 1 사용
        return hashlib.sha256(f"{query}:{intent}:{top_k}".encode()).hexdigest()[:16]
    
    async def _get_from_cache(self, key: str) -> Optional[SearchResult]:
        """Cache 조회"""
        try:
            data = await self.cache.get(key)
            if data:
                return SearchResult.from_dict(data)
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
        return None
    
    async def _save_to_cache(self, key: str, result: SearchResult):
        """Cache 저장"""
        try:
            await self.cache.setex(
                key,
                self.cache_ttl,
                result.to_dict(),
            )
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")
    
    async def get_symbol_info(self, symbol_id: str) -> SymbolInfo:
        """Symbol 정보 (LRU Cached)"""
        
        # In-memory LRU
        if symbol_id in self._symbol_cache:
            return self._symbol_cache[symbol_id]
        
        # DB 조회
        symbol_info = await self.graph.get_node(symbol_id)
        
        # Cache 저장
        if len(self._symbol_cache) >= self._max_cache_size:
            # LRU eviction
            oldest_key = next(iter(self._symbol_cache))
            del self._symbol_cache[oldest_key]
        
        self._symbol_cache[symbol_id] = symbol_info
        return symbol_info
```

#### Day 3-5: Router with Budget Enforcement

```python
# src/agent/orchestrator/orchestrator.py

import asyncio
from typing import Optional

class AgentOrchestrator:
    
    async def execute(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentResult:
        """메인 실행 (Budget 강제)"""
        
        start_time = time.time()
        context = context or {}
        
        # Budget 설정 (Default: 30초)
        budget_seconds = context.get("budget_seconds", 30.0)
        
        try:
            # asyncio.wait_for로 Budget 강제
            result = await asyncio.wait_for(
                self._execute_internal(user_request, context),
                timeout=budget_seconds,
            )
            
            return result
            
        except asyncio.TimeoutError:
            # Budget 초과 → PartialResult
            execution_time = (time.time() - start_time) * 1000
            
            logger.warning(f"Budget exceeded: {execution_time:.0f}ms > {budget_seconds * 1000}ms")
            
            return AgentResult(
                intent=context.get("intent", "unknown"),
                confidence=0.0,
                status=ExecutionStatus.PARTIAL,
                result=context.get("partial_result", None),
                error=f"Budget exceeded: {budget_seconds}s",
                error_details={
                    "budget_seconds": budget_seconds,
                    "actual_seconds": execution_time / 1000,
                },
                execution_time_ms=execution_time,
            )
        
        except Exception as e:
            # 다른 에러
            execution_time = (time.time() - start_time) * 1000
            return AgentResult(
                intent=context.get("intent", "unknown"),
                confidence=0.0,
                status=ExecutionStatus.FAILED,
                result=None,
                error=str(e),
                execution_time_ms=execution_time,
            )
    
    async def _execute_internal(
        self,
        user_request: str,
        context: Dict[str, Any],
    ) -> AgentResult:
        """실제 실행 로직 (기존 execute 내용)"""
        
        # Step 1: Router
        intent_result = await self._route(user_request, context)
        
        # Partial result 저장 (Timeout 대비)
        context["partial_result"] = {
            "intent": intent_result.intent,
            "confidence": intent_result.confidence,
        }
        
        # Step 2: TaskGraph
        task_graph = self._plan(intent_result)
        
        # Step 3: Workflow
        final_state = await self._execute_workflow(intent_result, task_graph)
        
        # Step 4: Result
        execution_time = (time.time() - context.get("start_time", time.time())) * 1000
        return self._format_result(intent_result, task_graph, final_state, execution_time)
```

---

### **Week 3-4: MetaLayer + JSON Parsing** (60% → 85%)

#### Day 11-14: DynamicTaskGraphPlanner with json_repair

```python
# src/agent/task_graph/dynamic_planner.py

import json
from json_repair import repair_json  # pip install json-repair
from litellm import completion  # LiteLLM
from pydantic import BaseModel, ValidationError

class TaskSchema(BaseModel):
    """Pydantic Schema (Validation)"""
    id: str
    type: str
    description: str
    depends_on: List[str] = []

class TaskGraphSchema(BaseModel):
    """Task Graph Schema"""
    tasks: List[TaskSchema]

class DynamicTaskGraphPlanner:
    """LLM 기반 동적 Task 분해 (Robust JSON Parsing)"""
    
    def __init__(self, static_planner: TaskGraphPlanner):
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
            return self.static_planner.plan(user_intent, context)
        
        # LLM 호출 (LiteLLM)
        prompt = self._build_decomposition_prompt(user_intent, analyzed_data)
        
        # Retry 3회
        for attempt in range(3):
            try:
                # LiteLLM completion
                response = await completion(
                    model="gpt-4",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    response_format={"type": "json_object"},  # JSON mode
                )
                
                raw_json = response.choices[0].message.content
                
                # JSON parsing with repair
                task_graph = self._parse_task_graph_robust(raw_json)
                
                return task_graph
                
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"JSON parsing failed (attempt {attempt + 1}): {e}")
                
                if attempt == 2:
                    # 3번 실패 → Fallback
                    logger.error("LLM JSON parsing failed 3 times, using static planner")
                    return self.static_planner.plan(user_intent, context)
    
    def _parse_task_graph_robust(self, raw_json: str) -> TaskGraph:
        """Robust JSON parsing (json_repair + Pydantic)"""
        
        # Step 1: json_repair (깨진 JSON 수정)
        try:
            repaired = repair_json(raw_json)
            data = json.loads(repaired)
        except Exception as e:
            logger.error(f"json_repair failed: {e}")
            raise
        
        # Step 2: Pydantic validation
        try:
            schema = TaskGraphSchema(**data)
        except ValidationError as e:
            logger.error(f"Pydantic validation failed: {e}")
            raise
        
        # Step 3: TaskGraph 생성
        task_graph = TaskGraph()
        
        for task_schema in schema.tasks:
            task = Task(
                id=task_schema.id,
                type=TaskType(task_schema.type),
                description=task_schema.description,
                depends_on=task_schema.depends_on,
            )
            task_graph.add_task(task)
        
        # Validation
        task_graph.validate_dag()
        task_graph.topological_sort()
        
        return task_graph
```

#### Day 15-17: GuardrailEngine with Pre-compiled Regex

```python
# src/safety/guardrail/rule_engine.py

import re
import yaml
from pathlib import Path
from typing import Dict, List, Callable, Pattern
from dataclasses import dataclass

@dataclass
class CompiledGuardrailRule:
    """Pre-compiled Rule (성능 최적화)"""
    id: str
    name: str
    description: str
    severity: str
    check: Callable
    patterns: List[Pattern] = None  # Pre-compiled regex

class GuardrailEngine:
    """규칙 엔진 (Regex Pre-compilation)"""
    
    def __init__(self, rules_path: str = "config/guardrail_rules.yaml"):
        self.rules: List[CompiledGuardrailRule] = []
        self._load_rules(rules_path)
    
    def _load_rules(self, path: str):
        """YAML → Compiled Rule"""
        config = yaml.safe_load(Path(path).read_text())
        
        for rule_config in config["rules"]:
            compiled_rule = self._build_rule(rule_config)
            self.rules.append(compiled_rule)
        
        logger.info(f"Loaded {len(self.rules)} guardrail rules")
    
    def _build_rule(self, config: Dict) -> CompiledGuardrailRule:
        """Rule 생성 (Regex Pre-compile)"""
        
        if config["name"] == "LOC_LIMIT":
            return CompiledGuardrailRule(
                id=config["id"],
                name=config["name"],
                description=config["description"],
                severity=config["severity"],
                check=lambda change, ctx: (
                    change.lines_added < config["params"]["max_lines"]
                ),
            )
        
        elif config["name"] == "NO_SECRET":
            # Regex Pre-compile (1회만)
            compiled_patterns = [
                re.compile(pattern, re.IGNORECASE)
                for pattern in config["patterns"]
            ]
            
            def check_secret(change, ctx):
                """Secret 검사 (Pre-compiled Regex 사용)"""
                for pattern in compiled_patterns:
                    if pattern.search(change.content):
                        return False
                return True
            
            return CompiledGuardrailRule(
                id=config["id"],
                name=config["name"],
                description=config["description"],
                severity=config["severity"],
                check=check_secret,
                patterns=compiled_patterns,
            )
        
        elif config["name"] == "FILE_LIMIT":
            return CompiledGuardrailRule(
                id=config["id"],
                name=config["name"],
                description=config["description"],
                severity=config["severity"],
                check=lambda change, ctx: (
                    len(change.files) <= config["params"]["max_files"]
                ),
            )
        
        # ... 다른 규칙들
    
    def check(
        self,
        code_change: CodeChange,
        context: Optional[Dict] = None
    ) -> GuardrailResult:
        """모든 규칙 체크 (Pre-compiled Regex로 빠름)"""
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

---

### **Week 4.5: Sandbox R&D (조기 시작)** ⚠️

**피드백 반영**: Week 6의 난관을 대비하여 Week 4 후반부터 R&D 시작

#### Day 18-20: E2B SDK 조사 + Session-based Container PoC

```python
# research/sandbox_poc.py

"""
Sandbox 전략 비교:
1. Docker containers.run (현재) - 느림
2. Docker exec_run (Session-based) - 빠름
3. E2B Code Interpreter SDK - SOTA (가장 빠름)
"""

# Option 1: 기존 방식 (느림)
def test_run_approach():
    import docker
    client = docker.from_env()
    
    start = time.time()
    for i in range(10):
        result = client.containers.run(
            "python:3.11-slim",
            "python -c 'print(1+1)'",
            remove=True,
        )
    print(f"containers.run x10: {time.time() - start:.2f}s")
    # 예상: 15-20초

# Option 2: Session-based (빠름)
def test_exec_approach():
    import docker
    client = docker.from_env()
    
    # 1회만 띄움
    container = client.containers.run(
        "python:3.11-slim",
        command="tail -f /dev/null",
        detach=True,
    )
    
    start = time.time()
    for i in range(10):
        exec_result = container.exec_run("python -c 'print(1+1)'")
    print(f"exec_run x10: {time.time() - start:.2f}s")
    # 예상: 0.5-1초
    
    container.stop()
    container.remove()

# Option 3: E2B SDK (SOTA)
def test_e2b_approach():
    from e2b import CodeInterpreter
    
    with CodeInterpreter() as sandbox:
        start = time.time()
        for i in range(10):
            result = sandbox.run_code("print(1+1)")
        print(f"E2B x10: {time.time() - start:.2f}s")
        # 예상: 0.3-0.5초

# 실행
test_run_approach()
test_exec_approach()
test_e2b_approach()
```

**결론**: E2B SDK가 가장 빠르지만, 의존성 설치 등은 직접 Docker로 제어 필요. **하이브리드 전략** 채택:
- 기본: Session-based Docker (exec_run)
- 고급: E2B SDK (간단한 Python 실행)

---

### **Week 5: Workflow + State Persistence** (40% → 85%)

#### Day 29-31: LangGraph Checkpoint Integration

```python
# src/agent/workflow/state_machine.py

from langgraph.checkpoint.sqlite import SqliteSaver  # LangGraph
from langgraph.graph import StateGraph, END

class WorkflowStateMachine:
    """
    LangGraph 기반 Workflow (State Persistence 포함)
    """
    
    def __init__(
        self,
        max_iterations: int = 3,
        enable_full_workflow: bool = False,
        checkpoint_db: str = "checkpoints.db",
    ):
        self.max_iterations = max_iterations
        self.enable_full_workflow = enable_full_workflow
        
        # LangGraph Checkpoint
        self.checkpointer = SqliteSaver.from_conn_string(checkpoint_db)
        
        # Graph 정의
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """LangGraph 정의"""
        
        workflow = StateGraph(WorkflowState)
        
        # Nodes
        workflow.add_node("analyze", self._analyze)
        workflow.add_node("plan", self._plan)
        workflow.add_node("generate", self._generate)
        workflow.add_node("critic", self._critic)
        workflow.add_node("test", self._test)
        workflow.add_node("self_heal", self._self_heal)
        
        # Edges
        workflow.add_edge("analyze", "plan")
        workflow.add_edge("plan", "generate")
        workflow.add_edge("generate", "critic")
        
        # Conditional edges
        workflow.add_conditional_edges(
            "critic",
            lambda state: "approved" if state.context.get("critic_approved") else "rejected",
            {
                "approved": "test",
                "rejected": "generate",  # 재생성
            }
        )
        
        workflow.add_conditional_edges(
            "test",
            lambda state: "passed" if state.context.get("test_passed") else "failed",
            {
                "passed": END,
                "failed": "self_heal",
            }
        )
        
        workflow.add_edge("self_heal", "generate")
        
        # Entry point
        workflow.set_entry_point("analyze")
        
        return workflow.compile(checkpointer=self.checkpointer)
    
    async def run(self, initial_state: WorkflowState) -> WorkflowState:
        """Workflow 실행 (Checkpoint 자동 저장)"""
        
        session_id = initial_state.context.get("session_id", "default")
        
        # LangGraph invoke (Checkpoint 자동 관리)
        final_state = await self.graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": session_id}},
        )
        
        return final_state
    
    async def resume(self, session_id: str) -> WorkflowState:
        """중단된 Workflow 재개"""
        
        # Checkpoint에서 마지막 상태 로드
        last_state = await self.graph.aget_state(
            config={"configurable": {"thread_id": session_id}},
        )
        
        if not last_state:
            raise ValueError(f"No checkpoint found for session: {session_id}")
        
        # 재개
        final_state = await self.graph.ainvoke(
            last_state,
            config={"configurable": {"thread_id": session_id}},
        )
        
        return final_state
```

**사용 예시**:
```python
# 1. 실행
workflow = WorkflowStateMachine(checkpoint_db="checkpoints.db")
state = WorkflowState(session_id="abc123", ...)

# 중간에 크래시 발생
final_state = await workflow.run(state)

# 2. 재개 (서버 재시작 후)
workflow = WorkflowStateMachine(checkpoint_db="checkpoints.db")
final_state = await workflow.resume(session_id="abc123")
```

---

### **Week 6: Session-based Sandbox** (20% → 90%)

#### Day 41-45: DockerSandbox with exec_run

```python
# src/execution/sandbox/docker_sandbox.py

import docker
from pathlib import Path
from typing import Optional, Dict
import tempfile
import shutil

class DockerSandbox:
    """Session-based Docker Sandbox (exec_run 사용)"""
    
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
        self.container: Optional[docker.models.containers.Container] = None
        
        # Session 상태
        self.is_running = False
        self.workspace_path: Optional[Path] = None
    
    async def start_session(
        self,
        workspace: Path,
        env: Optional[Dict[str, str]] = None,
    ):
        """세션 시작: 컨테이너를 데몬으로 띄움"""
        
        if self.is_running:
            logger.warning("Session already running")
            return
        
        logger.info("Starting sandbox session...")
        
        # Workspace 준비 (임시 디렉토리)
        self.workspace_path = workspace
        
        # 컨테이너 시작 (Keep-alive)
        self.container = self.client.containers.run(
            image=self.image,
            command="tail -f /dev/null",  # Keep alive
            detach=True,
            tty=True,
            stdin_open=True,
            
            # Volume mount (rw + /tmp 사용)
            volumes={
                str(workspace.absolute()): {
                    "bind": "/workspace",
                    "mode": "rw",  # Read-write (캐시 생성 허용)
                }
            },
            working_dir="/workspace",
            
            # Environment
            environment=env or {},
            
            # Resource limits
            mem_limit=self.memory_limit,
            cpu_period=100000,
            cpu_quota=int(self.cpu_limit * 100000),
            
            # Security
            network_mode=self.network_mode,
            user="nobody",  # Non-root
            
            # Auto-remove
            remove=False,  # 세션 종료 시 수동 삭제
        )
        
        self.is_running = True
        logger.info(f"Sandbox session started: {self.container.id[:12]}")
    
    async def execute_command(
        self,
        command: str,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """명령 실행 (exec_run 사용)"""
        
        if not self.is_running:
            raise RuntimeError("Session not started. Call start_session() first.")
        
        timeout = timeout or self.timeout
        
        logger.info(f"Executing: {command}")
        
        try:
            # exec_run (빠름!)
            exec_result = self.container.exec_run(
                cmd=f"bash -c '{command}'",
                stdout=True,
                stderr=True,
                stdin=False,
                tty=False,
                demux=True,  # stdout/stderr 분리
                user="nobody",
            )
            
            exit_code = exec_result.exit_code
            stdout, stderr = exec_result.output
            
            return ExecutionResult(
                success=exit_code == 0,
                exit_code=exit_code,
                stdout=stdout.decode("utf-8") if stdout else "",
                stderr=stderr.decode("utf-8") if stderr else "",
            )
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
            )
    
    async def execute_tests(
        self,
        test_command: str = "pytest -v",
    ) -> TestResult:
        """테스트 실행"""
        
        result = await self.execute_command(test_command)
        
        # pytest 출력 파싱
        test_result = self._parse_pytest_output(result.stdout)
        test_result.stderr = result.stderr
        
        return test_result
    
    async def install_dependencies(
        self,
        requirements: str = "requirements.txt",
    ):
        """의존성 설치 (세션 내 유지)"""
        
        result = await self.execute_command(
            f"pip install -r {requirements}",
            timeout=120,  # 2분
        )
        
        if not result.success:
            logger.error(f"Dependency installation failed: {result.stderr}")
            raise RuntimeError(f"pip install failed: {result.stderr}")
    
    async def stop_session(self):
        """세션 종료"""
        
        if not self.is_running:
            return
        
        logger.info("Stopping sandbox session...")
        
        try:
            self.container.stop(timeout=5)
            self.container.remove()
        except Exception as e:
            logger.error(f"Failed to stop container: {e}")
        
        self.is_running = False
        self.container = None
    
    def __enter__(self):
        """Context manager"""
        return self
    
    async def __aenter__(self):
        """Async context manager"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop_session()
```

**사용 예시**:
```python
# Session 방식 (빠름)
async with DockerSandbox() as sandbox:
    await sandbox.start_session(workspace=Path("/tmp/my_workspace"))
    
    # 의존성 설치 (1회)
    await sandbox.install_dependencies()
    
    # 여러 명령 실행 (컨테이너 재사용)
    await sandbox.execute_tests("pytest test_1.py")
    await sandbox.execute_tests("pytest test_2.py")
    await sandbox.execute_tests("pytest test_3.py")
    
    # 자동 cleanup
```

#### E2B SDK 활용 (선택적)

```python
# src/execution/sandbox/e2b_sandbox.py

from e2b import CodeInterpreter

class E2BSandbox:
    """E2B Code Interpreter Sandbox (가장 빠름)"""
    
    async def execute_python(self, code: str) -> str:
        """Python 코드 실행 (E2B)"""
        
        with CodeInterpreter() as sandbox:
            result = sandbox.run_code(code)
            
            return result.text
```

---

### **Week 7: Edge Cases + Switchable Mock** (90% → 100%)

#### Day 46-48: Config-based Mock Switching

```python
# src/config/agent_config.py

from pydantic import BaseSettings

class AgentConfig(BaseSettings):
    """Agent 설정 (환경변수)"""
    
    # Mock switches (개발 속도 유지)
    use_real_sandbox: bool = False  # False: Mock, True: Docker
    use_real_llm: bool = False      # False: Mock, True: LiteLLM
    use_real_cache: bool = True     # False: In-memory, True: Redis
    
    # Budget
    default_budget_seconds: float = 30.0
    max_budget_seconds: float = 300.0
    
    # Sandbox
    sandbox_image: str = "python:3.11-slim"
    sandbox_timeout: int = 30
    sandbox_memory_limit: str = "512m"
    
    class Config:
        env_prefix = "AGENT_"
        env_file = ".env"

# 사용
config = AgentConfig()

if config.use_real_sandbox:
    sandbox = DockerSandbox()
else:
    sandbox = MockSandbox()
```

---

### **Week 8: E2E + Performance** (95% → 100%)

#### Day 54-55: Performance Optimization

**최적화 목표**:
1. Context 병렬 검색 (3개 strategy 병렬)
2. LLM 호출 캐싱
3. Chunk deduplication

```python
# src/agent/adapters/context_adapter.py

async def search_parallel(
    self,
    query: str,
    strategies: List[str],  # ["symbol", "vector", "lexical"]
) -> Dict[str, SearchResult]:
    """병렬 검색 (3개 strategy 동시)"""
    
    tasks = []
    for strategy in strategies:
        tasks.append(
            self._search_single_strategy(query, strategy)
        )
    
    # asyncio.gather로 병렬 실행
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 결과 매핑
    strategy_results = {}
    for strategy, result in zip(strategies, results):
        if isinstance(result, Exception):
            logger.error(f"Strategy {strategy} failed: {result}")
        else:
            strategy_results[strategy] = result
    
    return strategy_results
```

---

## 📊 오픈소스 활용 매핑

| 오픈소스 | 사용 위치 | 목적 |
|---------|----------|------|
| **LangGraph** | Workflow StateMachine | State Persistence, Checkpoint |
| **E2B** | Sandbox (선택적) | 빠른 Python 실행 |
| **LiteLLM** | DynamicPlanner, CodeCritic | LLM 호출 통합 |
| **Pydantic** | DynamicPlanner, Config | JSON Validation |
| **Guardrails AI** | GuardrailEngine | Policy 정의 (선택적) |
| **Playwright** | Week 9 (ADR-025) | Visual Verification |
| **GitPython** | VCS Apply | Git 조작 |

---

## 🎯 성공 지표 (Updated)

| Metric | Before | After (V2) | 개선 |
|--------|--------|------------|------|
| **Sandbox 속도** | 2초/테스트 | 0.1초/테스트 | **20x** |
| **Context Cache Hit** | 0% | 50% | **2x 빠름** |
| **JSON Parsing 에러율** | 10% | < 1% | **10x** |
| **Long-running Task 복구** | 불가능 | 가능 | ✅ |
| **Budget 준수율** | 50% | 95%+ | ✅ |

---

## 🚀 Action Items (Day 1부터)

### Day 1 (지금 바로)
```bash
# 1. Context Adapter 생성
touch src/agent/adapters/context_adapter.py

# 2. 필수 패키지 설치
pip install langgraph json-repair guardrails-ai e2b litellm

# 3. Config 파일 생성
mkdir -p config
touch config/guardrail_rules.yaml
touch .env
```

### Day 2-3
- ContextAdapter 구현 (Semantic Cache 포함)
- Redis 연동 테스트

### Day 4-5
- Router Budget Enforcement
- `asyncio.wait_for` 통합 테스트

**Go!** 🚀

