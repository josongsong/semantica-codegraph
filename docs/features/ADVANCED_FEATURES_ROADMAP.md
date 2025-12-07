# 🚀 Advanced Features Implementation Roadmap

**목표**: 업계 SOTA를 넘어서는 차세대 Code Intelligence Engine 구축  
**현재 상태**: SOTA IR 완성 (17/18, 94%)  
**다음 단계**: P0 기본 SOTA → P1 차세대 기능

---

## 📊 현재 상태 요약

### ✅ 완성된 기능 (SOTA급)
- Symbol Resolution: 100%
- Call Graph: Inter-procedural, 828 edges
- Dataflow: READS/WRITES tracking
- Incremental Update: 192x faster
- Module/Import Graph: Canonical signatures
- Inheritance Graph: 9/9 tracking
- Exception Tracking: raises/catches
- Graph Query: BFS/DFS, Pattern matching

### 🚧 부분 구현 (확장 필요)
- Type Narrowing: 기본 구조만 있음 → Full implementation 필요
- Context-Insensitive Call Graph → Context-Sensitive로 업그레이드

### 📝 미구현 (신규 기능)
- Local Overlay (Uncommitted Changes Layer)
- Semantic Region Index (SRI)
- Impact-Based Partial Rebuild
- Speculative Graph Execution
- Semantic Change Detection
- AutoRRF Query Fusion

---

## 🎯 P0: 기본 SOTA 기능 (업계 표준을 확실히 넘김)

### 1.1 Local Overlay (Uncommitted Changes Layer)
**Impact**: ⭐⭐⭐⭐⭐ (Critical - 정확도 30-50% 향상)  
**Difficulty**: ⭐⭐⭐⭐ (Hard)  
**Priority**: P0 - 최우선  
**Status**: 🚧 TODO (Must-Have 18/18 달성)

#### 핵심 가치
- IDE/Agent 정확도를 **즉시 30-50% 향상**
- 사용자가 편집 중인 코드를 IR/Graph에 **실시간 반영**
- Sourcegraph: 매우 제한적
- CodeQL: 거의 지원 안 함
- **구현하면 업계 SOTA 확정**

#### 아키텍처

```
┌─────────────────────────────────────────────────┐
│  Query Layer (LSP, Agent, Retrieval)            │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│  Overlay Merge Layer (NEW!)                     │
│  - Base Snapshot (committed code)               │
│  - Overlay Graph (uncommitted changes)          │
│  - Smart Merge Strategy                         │
└────────────────┬────────────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────┐  ┌──────────────────┐
│ Base IR/Graph│  │ Overlay IR/Graph │
│ (Committed)  │  │ (Uncommitted)    │
└──────────────┘  └──────────────────┘
```

#### 구현 전략

**Phase 1: Overlay IR Builder** (1주)
```python
# src/contexts/analysis_indexing/infrastructure/overlay/overlay_builder.py

class OverlayIRBuilder:
    """Uncommitted changes를 IR로 변환"""
    
    def build_overlay(
        self,
        base_snapshot_id: str,
        uncommitted_files: Dict[str, str]  # path -> content
    ) -> OverlaySnapshot:
        """
        1. Uncommitted files만 파싱
        2. Base IR과의 delta 계산
        3. Overlay IR document 생성
        """
        pass
    
    def invalidate_affected(
        self,
        changed_file: str,
        base_graph: KuzuGraph
    ) -> Set[str]:
        """
        변경 파일에 영향받는 symbols 계산
        - Callers of changed functions
        - Importers of changed modules
        - Subtypes of changed classes
        """
        pass
```

**Phase 2: Graph Merge Strategy** (1주)
```python
# src/contexts/analysis_indexing/infrastructure/overlay/graph_merger.py

class GraphMerger:
    """Base + Overlay graph를 병합"""
    
    def merge_graphs(
        self,
        base: KuzuGraph,
        overlay: OverlayGraph
    ) -> MergedSnapshot:
        """
        Merge 전략:
        1. Symbol 충돌 해결 (overlay 우선)
        2. Edge 업데이트 (call graph, import graph)
        3. Dead symbol 제거 (base에만 있는 deleted symbols)
        """
        pass
    
    def resolve_symbol_conflict(
        self,
        base_symbol: Symbol,
        overlay_symbol: Symbol
    ) -> Symbol:
        """
        Overlay가 항상 우선:
        - Signature 변경 → overlay 사용
        - Body 변경 → overlay 사용
        - 삭제 → base에서 제거
        """
        pass
```

**Phase 3: Query Layer Integration** (3일)
```python
# src/contexts/retrieval_search/infrastructure/overlay_aware_retriever.py

class OverlayAwareRetriever:
    """Overlay를 고려한 검색"""
    
    async def search(
        self,
        query: str,
        repo_id: str,
        include_overlay: bool = True  # NEW!
    ) -> List[SearchResult]:
        """
        1. Base snapshot에서 검색
        2. Overlay snapshot 고려
        3. 결과 merge (overlay 우선)
        """
        if include_overlay:
            merged_snapshot = self.get_merged_snapshot(repo_id)
            return self.search_in_snapshot(query, merged_snapshot)
        else:
            return self.search_in_snapshot(query, base_snapshot)
```

**Phase 4: LSP Integration** (3일)
```python
# server/mcp_server/overlay_lsp_handler.py

class OverlayLSPHandler:
    """LSP 요청 시 overlay 반영"""
    
    def handle_definition(
        self,
        file: str,
        position: Position,
        uncommitted_content: str
    ) -> List[Location]:
        """
        1. File의 uncommitted content로 overlay 생성
        2. Merged snapshot에서 정의 찾기
        3. Overlay symbol 우선 반환
        """
        pass
    
    def handle_references(
        self,
        symbol: str,
        uncommitted_files: Dict[str, str]
    ) -> List[Location]:
        """
        참조 검색:
        1. Base references
        2. Overlay에서 추가된 references
        3. Merge 후 반환
        """
        pass
```

#### 구현 위치
```
src/contexts/analysis_indexing/infrastructure/overlay/
├── __init__.py
├── overlay_builder.py          # Uncommitted IR builder
├── graph_merger.py             # Base + Overlay merge
├── overlay_snapshot.py         # Overlay snapshot model
└── conflict_resolver.py        # Symbol conflict resolution

src/contexts/retrieval_search/infrastructure/
└── overlay_aware_retriever.py  # Overlay 고려한 검색

server/mcp_server/
└── overlay_lsp_handler.py      # LSP overlay support
```

#### 성능 목표
- Overlay IR 생성: < 10ms (single file)
- Graph merge: < 50ms (typical overlay size)
- Query overhead: < 5% (overlay 포함 시)

#### 검증 기준
```python
# tests/test_overlay_integration.py

def test_overlay_definition():
    """Uncommitted 변경이 정의 검색에 반영됨"""
    base = index_repo("test_repo")
    
    # 파일 수정 (미커밋)
    uncommitted = {
        "src/main.py": "def foo(): return 42"  # 시그니처 변경
    }
    
    # Overlay 반영된 결과
    result = find_definition("foo", overlay=uncommitted)
    assert result.signature == "() -> int"  # 새 시그니처
    
def test_overlay_call_graph():
    """Uncommitted 변경이 call graph에 반영됨"""
    # foo()를 bar()로 rename (미커밋)
    uncommitted = {
        "src/main.py": "def bar(): pass\n\ndef caller(): bar()"
    }
    
    cg = get_call_graph(overlay=uncommitted)
    assert ("caller", "bar") in cg.edges
    assert ("caller", "foo") not in cg.edges  # 삭제됨
```

---

### 1.2 Full Type Narrowing (TS/Python)
**Impact**: ⭐⭐⭐⭐ (Call Graph precision +30%)  
**Difficulty**: ⭐⭐⭐⭐ (Hard)  
**Priority**: P0  
**Status**: 🚧 부분 구현 (기본 구조만 있음)

#### 핵심 가치
- Call Graph precision **30% 향상**
- TS 언어 서버 수준의 narrowing
- Sourcegraph: 없음
- CodeQL: 일부만 있고 정확도 부족

#### 현재 상태
```python
# src/contexts/code_foundation/infrastructure/analyzers/type_narrowing_full.py
# 기본 구조만 있음 (enum, dataclass 정의)
# 실제 분석 로직은 미완성
```

#### 구현 범위

**Python:**
1. **isinstance narrowing**
```python
def process(x: Union[str, int]):
    if isinstance(x, str):
        # x는 str로 narrowing
        print(x.upper())
    else:
        # x는 int로 narrowing
        print(x + 1)
```

2. **None narrowing**
```python
def process(x: Optional[str]):
    if x is not None:
        # x는 str로 narrowing
        print(x.upper())
    
    if x is None:
        return
    # x는 str로 narrowing (early return)
    print(x.lower())
```

3. **Truthiness narrowing**
```python
def process(x: Optional[List[str]]):
    if x:
        # x는 List[str]로 narrowing (not None, not empty)
        for item in x:
            print(item)
```

4. **Type guard functions**
```python
def is_admin(user: User) -> TypeGuard[AdminUser]:
    return user.role == "admin"

def process(user: User):
    if is_admin(user):
        # user는 AdminUser로 narrowing
        user.admin_action()
```

**TypeScript:**
1. **typeof narrowing**
```typescript
function process(x: string | number) {
    if (typeof x === "string") {
        // x는 string으로 narrowing
        console.log(x.toUpperCase());
    } else {
        // x는 number로 narrowing
        console.log(x.toFixed(2));
    }
}
```

2. **Discriminated unions**
```typescript
type Result = 
    | { status: "success"; data: string }
    | { status: "error"; error: Error };

function handle(result: Result) {
    if (result.status === "success") {
        // result는 { status: "success"; data: string }로 narrowing
        console.log(result.data);
    } else {
        // result는 { status: "error"; error: Error }로 narrowing
        console.error(result.error);
    }
}
```

3. **instanceof narrowing**
```typescript
function process(x: Error | CustomError) {
    if (x instanceof CustomError) {
        // x는 CustomError로 narrowing
        x.customMethod();
    }
}
```

4. **Custom type guards**
```typescript
function isString(x: unknown): x is string {
    return typeof x === "string";
}

function process(x: unknown) {
    if (isString(x)) {
        // x는 string으로 narrowing
        console.log(x.toUpperCase());
    }
}
```

#### 구현 전략

**Phase 1: CFG-based Type State Tracking** (1주)
```python
# src/contexts/code_foundation/infrastructure/analyzers/type_state_tracker.py

class TypeStateTracker:
    """Control Flow 기반 타입 상태 추적"""
    
    def analyze_function(self, func_ir: FunctionIR) -> TypeStateMap:
        """
        1. CFG 생성
        2. 각 basic block의 entry/exit type state 계산
        3. Join points에서 type state merge
        """
        cfg = self.build_cfg(func_ir)
        type_states = {}
        
        for block in cfg.blocks:
            entry_state = self.compute_entry_state(block, type_states)
            exit_state = self.analyze_block(block, entry_state)
            type_states[block.id] = exit_state
        
        return type_states
    
    def narrow_type(
        self,
        var: str,
        condition: ast.expr,
        current_state: TypeState
    ) -> TypeState:
        """
        조건식에서 타입 narrowing:
        - isinstance(x, T) → x: T
        - x is None → x: None
        - typeof x === "string" → x: string
        """
        pass
```

**Phase 2: Call Graph Precision Enhancement** (1주)
```python
# src/contexts/code_foundation/infrastructure/graphs/precise_call_graph.py

class PreciseCallGraphBuilder:
    """Type narrowing 기반 정밀 call graph"""
    
    def resolve_call(
        self,
        call: CallIR,
        type_state: TypeState
    ) -> Set[str]:
        """
        타입 정보 기반 call target 해석:
        
        예:
        def process(handler: Handler):
            if isinstance(handler, FastHandler):
                handler.fast_process()  # FastHandler.fast_process만
            else:
                handler.slow_process()  # Handler.slow_process (not FastHandler)
        """
        receiver_type = type_state.get_type(call.receiver)
        
        if receiver_type.is_narrowed:
            # Narrowed type으로만 resolve
            return self.resolve_method(receiver_type, call.method_name)
        else:
            # 모든 가능한 타입으로 resolve (기존 방식)
            return self.resolve_method_union(receiver_type, call.method_name)
```

**Phase 3: Integration with IR** (3일)
```python
# src/contexts/code_foundation/infrastructure/ir/enhanced_ir_builder.py

class EnhancedIRBuilder:
    """Type narrowing 정보를 IR에 포함"""
    
    def build_function_ir(self, func_node: ast.FunctionDef) -> FunctionIR:
        """
        기존 IR에 type narrowing 정보 추가:
        - 각 statement마다 type state 저장
        - Call site마다 receiver type 저장
        """
        base_ir = self.build_base_ir(func_node)
        
        # Type narrowing 분석
        type_states = self.type_state_tracker.analyze_function(base_ir)
        
        # IR에 type 정보 추가
        for stmt in base_ir.statements:
            stmt.type_state = type_states.get(stmt.id)
        
        return base_ir
```

#### 구현 위치
```
src/contexts/code_foundation/infrastructure/analyzers/
├── type_narrowing_full.py      # ✅ 기존 (확장 필요)
├── type_state_tracker.py       # NEW: CFG 기반 type state
├── type_guard_detector.py      # NEW: Type guard 함수 인식
└── union_resolver.py           # NEW: Union type 해석

src/contexts/code_foundation/infrastructure/graphs/
└── precise_call_graph.py       # NEW: Type 기반 정밀 call graph
```

#### 성능 목표
- Type narrowing overhead: < 15% (IR generation 대비)
- Call graph precision: +30%
- False positives: -40%

#### 검증 기준
```python
def test_isinstance_narrowing():
    code = """
    def process(x: Union[str, int]):
        if isinstance(x, str):
            x.upper()  # str method
        else:
            x + 1      # int operation
    """
    
    ir = build_ir(code)
    cg = build_call_graph(ir)
    
    # str.upper 호출만 있어야 함 (int.upper는 없음)
    assert ("process", "str.upper") in cg.edges
    assert ("process", "int.upper") not in cg.edges

def test_discriminated_union():
    code = """
    type Result = { status: 'ok'; data: string } | { status: 'error'; msg: string }
    
    function handle(r: Result) {
        if (r.status === 'ok') {
            console.log(r.data);  // data field만
        } else {
            console.log(r.msg);   // msg field만
        }
    }
    """
    
    ir = build_ir(code)
    # r.data, r.msg 모두 정확히 인식되어야 함
```

---

### 1.3 Context-Sensitive Call Graph
**Impact**: ⭐⭐⭐⭐⭐ (정확도 대폭 향상)  
**Difficulty**: ⭐⭐⭐⭐⭐ (Very Hard)  
**Priority**: P0  
**Status**: 🚧 현재 context-insensitive

#### 핵심 가치
- Impact Analysis 정확도 증가
- Dataflow/Controlflow 정확도 증가
- Refactoring 제안 정확도 증가
- Sourcegraph: 없음
- CodeQL: 제한적
- **구현하면 세계 최고급**

#### 현재 vs 목표

**현재 (Context-Insensitive):**
```javascript
function run(flag) {
    if (flag) a(); 
    else b();
}

run(true);   // Case 1
run(false);  // Case 2

// 현재 call graph (부정확):
run → a
run → b
```

**목표 (Context-Sensitive):**
```javascript
// 정확한 call graph:
run(flag=true)  → a    (Case 1만)
run(flag=false) → b    (Case 2만)

// Context로 구분:
Call Site 1: run(true) → a
Call Site 2: run(false) → b
```

#### 구현 전략

**Phase 1: Call Context Modeling** (1주)
```python
# src/contexts/code_foundation/infrastructure/graphs/call_context.py

@dataclass
class CallContext:
    """호출 컨텍스트"""
    call_site: str           # "main.py:15:4"
    caller_context: Optional['CallContext']  # Recursive
    argument_values: Dict[str, Any]  # 인자 값 (상수만)
    
    def context_id(self) -> str:
        """컨텍스트 고유 ID"""
        return f"{self.call_site}#{hash(self.argument_values)}"

class ContextSensitiveCallGraph:
    """Context-sensitive call graph"""
    
    def __init__(self):
        # (caller_context, callee) → Set[CallContext]
        self.edges: Dict[Tuple[str, str], Set[CallContext]] = {}
    
    def add_edge(
        self,
        caller: str,
        callee: str,
        context: CallContext
    ):
        """컨텍스트 기반 edge 추가"""
        key = (caller, callee)
        if key not in self.edges:
            self.edges[key] = set()
        self.edges[key].add(context)
    
    def get_reachable(
        self,
        start: str,
        context: CallContext
    ) -> Set[Tuple[str, CallContext]]:
        """컨텍스트 기반 reachability"""
        visited = set()
        queue = [(start, context)]
        
        while queue:
            current, ctx = queue.pop(0)
            if (current, ctx) in visited:
                continue
            visited.add((current, ctx))
            
            # 현재 context에서 호출 가능한 함수들
            for callee, call_contexts in self.get_callees(current):
                for call_ctx in call_contexts:
                    if call_ctx.matches(ctx):
                        queue.append((callee, call_ctx))
        
        return visited
```

**Phase 2: Argument Value Tracking** (1주)
```python
# src/contexts/code_foundation/infrastructure/analyzers/value_tracker.py

class ArgumentValueTracker:
    """인자 값 추적 (상수 전파)"""
    
    def track_call(
        self,
        call_site: CallIR,
        caller_context: CallContext
    ) -> Dict[str, Any]:
        """
        호출 시점의 인자 값 추적:
        - 상수: 그대로 추적
        - 변수: 값 전파 (가능하면)
        - 복잡한 식: Unknown
        """
        arg_values = {}
        
        for param_name, arg_expr in call_site.arguments.items():
            if isinstance(arg_expr, ast.Constant):
                # 상수 → 직접 사용
                arg_values[param_name] = arg_expr.value
            elif isinstance(arg_expr, ast.Name):
                # 변수 → 값 전파
                value = self.resolve_variable(arg_expr.id, caller_context)
                if value is not Unknown:
                    arg_values[param_name] = value
            # else: 복잡한 식 → 추적 안 함
        
        return arg_values
```

**Phase 3: Context-Sensitive Analysis** (2주)
```python
# src/contexts/code_foundation/infrastructure/analyzers/context_sensitive_analyzer.py

class ContextSensitiveAnalyzer:
    """Context-sensitive 분석"""
    
    def analyze_repository(
        self,
        repo_ir: RepositoryIR,
        max_depth: int = 5  # Call depth 제한
    ) -> ContextSensitiveCallGraph:
        """
        전체 repository를 context-sensitive하게 분석
        
        알고리즘:
        1. Entry points (main, public APIs) 찾기
        2. 각 entry point에서 BFS/DFS
        3. 각 call site마다 context 생성
        4. Context별로 callee 분석 (재귀)
        """
        cscg = ContextSensitiveCallGraph()
        
        entry_points = self.find_entry_points(repo_ir)
        
        for entry in entry_points:
            root_context = CallContext(
                call_site="<entry>",
                caller_context=None,
                argument_values={}
            )
            self.analyze_function(entry, root_context, cscg, depth=0, max_depth=max_depth)
        
        return cscg
    
    def analyze_function(
        self,
        func: FunctionIR,
        context: CallContext,
        cscg: ContextSensitiveCallGraph,
        depth: int,
        max_depth: int
    ):
        """함수를 특정 context에서 분석"""
        if depth > max_depth:
            return  # Depth 제한
        
        # 인자 값으로 type narrowing
        type_state = self.narrow_by_arguments(func, context.argument_values)
        
        for call in func.calls:
            # Call target 해석 (type state 기반)
            targets = self.resolve_call(call, type_state)
            
            for target in targets:
                # Call context 생성
                call_context = CallContext(
                    call_site=call.location,
                    caller_context=context,
                    argument_values=self.value_tracker.track_call(call, context)
                )
                
                # Edge 추가
                cscg.add_edge(func.symbol, target.symbol, call_context)
                
                # Recursive analysis
                self.analyze_function(target, call_context, cscg, depth + 1, max_depth)
```

**Phase 4: Impact Analysis Enhancement** (3일)
```python
# src/contexts/analysis_indexing/infrastructure/impact_analyzer.py

class ContextAwareImpactAnalyzer:
    """Context-aware impact analysis"""
    
    def analyze_impact(
        self,
        changed_symbol: str,
        change_type: ChangeType,
        cscg: ContextSensitiveCallGraph
    ) -> ImpactReport:
        """
        Context를 고려한 영향 분석:
        
        예:
        def calc(mode):
            if mode == "fast":
                return fast_calc()
            else:
                return slow_calc()
        
        fast_calc() 변경 시:
        - calc(mode="fast")만 영향받음
        - calc(mode="slow")는 영향받지 않음
        """
        impact = ImpactReport()
        
        # 모든 caller 찾기
        for (caller, callee), contexts in cscg.edges.items():
            if callee == changed_symbol:
                for ctx in contexts:
                    # Context별로 영향 평가
                    if self.is_affected(change_type, ctx):
                        impact.add_affected_call(caller, ctx)
        
        return impact
```

#### 구현 위치
```
src/contexts/code_foundation/infrastructure/graphs/
├── call_context.py             # NEW: Call context model
└── context_sensitive_cg.py     # NEW: Context-sensitive call graph

src/contexts/code_foundation/infrastructure/analyzers/
├── value_tracker.py            # NEW: Argument value tracking
└── context_sensitive_analyzer.py  # NEW: Main analyzer

src/contexts/analysis_indexing/infrastructure/
└── context_aware_impact.py     # NEW: Context-aware impact analysis
```

#### 성능 목표
- Analysis time: < 2x of context-insensitive (acceptable tradeoff)
- Max call depth: 5 (configurable)
- Precision improvement: +40% (vs context-insensitive)
- False positives: -50%

#### 검증 기준
```python
def test_context_sensitive_call():
    code = """
    def process(flag):
        if flag:
            fast()
        else:
            slow()
    
    process(True)   # Call site 1
    process(False)  # Call site 2
    """
    
    cscg = build_context_sensitive_cg(code)
    
    # Call site 1: process(True) → fast()만
    ctx1 = CallContext(call_site="line:8", argument_values={"flag": True})
    reachable1 = cscg.get_reachable("process", ctx1)
    assert ("fast", ctx1) in reachable1
    assert ("slow", ctx1) not in reachable1
    
    # Call site 2: process(False) → slow()만
    ctx2 = CallContext(call_site="line:9", argument_values={"flag": False})
    reachable2 = cscg.get_reachable("process", ctx2)
    assert ("slow", ctx2) in reachable2
    assert ("fast", ctx2) not in reachable2
```

---

### 1.4 Semantic Region Index (SRI)
**Impact**: ⭐⭐⭐⭐⭐ (LLM Augmentation에서 압도적)  
**Difficulty**: ⭐⭐⭐⭐ (Hard)  
**Priority**: P0  
**Status**: 🚧 TODO (신규 기능)

#### 핵심 가치
- LLM 기반 IDE에서 **매우 중요**한 기능
- File-level/Symbol-level을 넘어 **Region-level 인덱싱**
- Sourcegraph, CodeQL: 모두 지원 안 함
- **구현하면 LLM Augmentation 차별화**

#### Region이란?

파일을 의미적으로 잘게 나눈 단위:
```python
# Region 1: Authentication Setup (lines 10-25)
def setup_auth(config):
    """인증 설정 초기화"""
    auth = AuthProvider(config)
    auth.configure()
    return auth

# Region 2: User Validation (lines 27-45)
def validate_user(user):
    """사용자 검증 로직"""
    if not user.email:
        raise ValidationError()
    if not check_permission(user):
        raise PermissionError()
    return True

# Region 3: Main Handler (lines 47-80)
def handle_request(request):
    """요청 처리 메인 흐름"""
    user = extract_user(request)
    if validate_user(user):
        return process_request(request)
    return error_response()
```

각 Region은:
- **Functionality**: 무엇을 하는가?
- **Type Flow**: 어떤 타입들이 흐르는가?
- **Responsibility**: 누구의 책임인가?
- **Control Flow**: 어떤 흐름인가?
- **Semantic Tags**: 어떤 개념과 연관되는가?

#### 구현 전략

**Phase 1: Region Segmentation** (1주)
```python
# src/contexts/code_foundation/infrastructure/region/segmenter.py

@dataclass
class CodeRegion:
    """코드 region"""
    id: str
    file_path: str
    start_line: int
    end_line: int
    
    # Semantic info
    functionality: str         # "Authentication setup"
    responsibility: str        # "Initialize auth provider"
    control_flow_type: str     # "setup", "validation", "handler"
    
    # Symbols in region
    symbols: Set[str]          # Functions, classes defined
    references: Set[str]       # External symbols referenced
    
    # Type flow
    input_types: Set[str]      # Types flowing in
    output_types: Set[str]     # Types flowing out
    
    # Semantic tags
    tags: Set[str]             # ["auth", "validation", "security"]

class RegionSegmenter:
    """파일을 의미적 region으로 분할"""
    
    def segment_file(self, file_ir: FileIR) -> List[CodeRegion]:
        """
        파일을 region으로 분할:
        
        전략:
        1. Top-level symbols (함수, 클래스) 기준 분할
        2. 연관된 helpers는 같은 region으로 묶음
        3. Comments, docstrings로 region 경계 힌트
        """
        regions = []
        
        # AST 순회하며 region 후보 찾기
        for node in file_ir.ast.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                region = self.create_region_for_symbol(node, file_ir)
                regions.append(region)
        
        # Region 병합 (관련된 것들끼리)
        regions = self.merge_related_regions(regions, file_ir)
        
        return regions
```

**Phase 2: LLM-based Region Annotation** (1주)
```python
# src/contexts/code_foundation/infrastructure/region/annotator.py

class RegionAnnotator:
    """LLM으로 region 의미 추출"""
    
    async def annotate_region(
        self,
        region: CodeRegion,
        code: str
    ) -> AnnotatedRegion:
        """
        LLM에게 region 분석 요청:
        
        Prompt:
        "다음 코드 region을 분석하세요:
        1. Functionality (한 문장)
        2. Responsibility (한 문장)
        3. Semantic tags (5개 이하 키워드)
        4. Control flow type (setup/validation/handler/...)"
        """
        prompt = self.build_prompt(region, code)
        response = await self.llm_client.complete(prompt)
        
        return AnnotatedRegion(
            **region.__dict__,
            functionality=response.functionality,
            responsibility=response.responsibility,
            tags=response.tags,
            control_flow_type=response.control_flow_type
        )
```

**Phase 3: Region Index** (1주)
```python
# src/contexts/multi_index/infrastructure/region_index.py

class RegionIndex:
    """Region semantic index"""
    
    def __init__(self, vector_store, tantivy):
        self.vector_store = vector_store  # Qdrant
        self.keyword_index = tantivy
    
    async def index_region(self, region: AnnotatedRegion):
        """
        Region 인덱싱:
        1. Vector embedding (functionality + tags)
        2. Keyword index (symbols + tags)
        3. Graph index (region dependencies)
        """
        # Vector embedding
        embedding_text = f"{region.functionality} {' '.join(region.tags)}"
        embedding = await self.embed(embedding_text)
        
        await self.vector_store.upsert(
            collection="regions",
            points=[{
                "id": region.id,
                "vector": embedding,
                "payload": {
                    "file": region.file_path,
                    "lines": (region.start_line, region.end_line),
                    "functionality": region.functionality,
                    "tags": list(region.tags),
                    "symbols": list(region.symbols)
                }
            }]
        )
        
        # Keyword index
        self.keyword_index.add_document(
            doc_id=region.id,
            fields={
                "functionality": region.functionality,
                "tags": " ".join(region.tags),
                "symbols": " ".join(region.symbols)
            }
        )
    
    async def search_regions(
        self,
        query: str,
        tags: Optional[Set[str]] = None
    ) -> List[CodeRegion]:
        """
        Region 검색:
        - Semantic search (vector)
        - Tag filter
        - Symbol filter
        """
        # Vector search
        query_embedding = await self.embed(query)
        vector_results = await self.vector_store.search(
            collection="regions",
            query_vector=query_embedding,
            limit=20
        )
        
        # Tag filter (if provided)
        if tags:
            vector_results = [
                r for r in vector_results
                if tags & set(r.payload["tags"])
            ]
        
        return vector_results
```

**Phase 4: Retrieval Integration** (3일)
```python
# src/contexts/retrieval_search/infrastructure/region_aware_retriever.py

class RegionAwareRetriever:
    """Region을 고려한 retrieval"""
    
    async def retrieve(
        self,
        query: str,
        repo_id: str,
        retrieval_mode: str = "auto"
    ) -> List[RetrievalResult]:
        """
        Query 의도에 따라 retrieval strategy 선택:
        
        1. "이 API 어디서 호출?" → Symbol-level (call graph)
        2. "인증 로직 설명해줘" → Region-level (SRI)
        3. "할인 계산 어떻게 동작?" → Region-level + Dataflow
        """
        # Query 의도 분류
        intent = await self.classify_intent(query)
        
        if intent == "call_reference":
            # Symbol-level 검색
            return await self.symbol_retriever.search(query)
        
        elif intent == "explanation":
            # Region-level 검색
            return await self.region_index.search_regions(query)
        
        elif intent == "dataflow":
            # Region + Dataflow 결합
            regions = await self.region_index.search_regions(query)
            dataflow = await self.dataflow_analyzer.analyze_regions(regions)
            return self.merge_results(regions, dataflow)
```

#### 구현 위치
```
src/contexts/code_foundation/infrastructure/region/
├── __init__.py
├── segmenter.py               # NEW: Region 분할
├── annotator.py               # NEW: LLM 기반 annotation
└── models.py                  # NEW: Region models

src/contexts/multi_index/infrastructure/
└── region_index.py            # NEW: Region indexing

src/contexts/retrieval_search/infrastructure/
└── region_aware_retriever.py  # NEW: Region 기반 retrieval
```

#### 성능 목표
- Region segmentation: < 100ms per file
- LLM annotation: < 2s per region (async batch)
- Region search: < 100ms
- Index size: ~10KB per region

#### 검증 기준
```python
def test_region_segmentation():
    code = """
    def setup_auth(config):
        '''인증 설정'''
        pass
    
    def validate_user(user):
        '''사용자 검증'''
        pass
    """
    
    regions = segment_file(code)
    assert len(regions) == 2
    assert regions[0].functionality.lower() == "authentication setup"
    assert "auth" in regions[0].tags
    assert "validation" in regions[1].tags

def test_region_search():
    # "인증 관련 코드 찾아줘"
    results = search_regions(query="authentication logic", tags={"auth"})
    assert len(results) > 0
    assert "auth" in results[0].tags
    assert "setup_auth" in results[0].symbols
```

---

## 🚀 P1: 차세대 기능 (업계가 아직 못함)

### 2.1 Impact-Based Partial Graph Rebuild
**Impact**: ⭐⭐⭐⭐ (성능 최적화)  
**Difficulty**: ⭐⭐⭐⭐ (Hard)  
**Priority**: P1  
**Status**: 🚧 TODO (Incremental Update 확장)

#### 핵심 가치
- Incremental Update를 **더욱 지능적으로**
- **Impact level에 따라 rebuild depth 자동 최적화**
- 현재 incremental보다 **2-5x 더 빠름**

#### 현재 vs 목표

**현재 (Incremental):**
```python
# 파일 변경 → 해당 파일 + 의존 파일 전체 rebuild
def incremental_update(changed_file):
    affected = get_affected_files(changed_file)  # 의존 파일 모두
    for file in affected:
        rebuild_ir(file)        # 전체 rebuild
        rebuild_graph(file)     # 전체 rebuild
```

**목표 (Impact-Based Partial):**
```python
# 변경 타입에 따라 최소한만 rebuild
def impact_based_update(changed_file, change_type):
    if change_type == "signature_change":
        # Signature 변경 → callers만 rebuild
        callers = get_direct_callers(changed_file)
        for caller in callers:
            rebuild_call_edges(caller)  # Call edges만
    
    elif change_type == "body_change":
        # Body 변경 → CFG/DFG만 update
        rebuild_cfg_dfg(changed_file)  # 해당 파일만
    
    elif change_type == "comment_change":
        # Comment 변경 → Nothing (skip)
        pass
```

#### 구현 전략

**Phase 1: Change Impact Classifier** (1주)
```python
# src/contexts/analysis_indexing/infrastructure/impact/change_classifier.py

class ChangeImpactLevel(Enum):
    """변경 영향도"""
    NONE = 0           # Comment, whitespace
    LOCAL = 1          # Function body 내부
    SIGNATURE = 2      # Function signature
    INTERFACE = 3      # Class interface
    GLOBAL = 4         # Module exports

class ChangeImpactClassifier:
    """변경의 영향도 분류"""
    
    def classify_change(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> ChangeImpactLevel:
        """
        변경 분석:
        1. AST diff
        2. Signature diff
        3. Export diff
        4. Impact level 결정
        """
        old_ast = parse(old_content)
        new_ast = parse(new_content)
        
        ast_diff = self.compute_ast_diff(old_ast, new_ast)
        
        if ast_diff.is_comment_only:
            return ChangeImpactLevel.NONE
        
        if ast_diff.has_signature_change:
            return ChangeImpactLevel.SIGNATURE
        
        if ast_diff.has_export_change:
            return ChangeImpactLevel.GLOBAL
        
        if ast_diff.has_body_change_only:
            return ChangeImpactLevel.LOCAL
        
        return ChangeImpactLevel.INTERFACE
```

**Phase 2: Partial Rebuild Strategies** (2주)
```python
# src/contexts/analysis_indexing/infrastructure/impact/partial_rebuilder.py

class PartialRebuilder:
    """영향도 기반 부분 rebuild"""
    
    def rebuild_by_impact(
        self,
        changed_file: str,
        impact_level: ChangeImpactLevel,
        old_ir: FileIR,
        new_ir: FileIR
    ):
        """영향도에 맞는 rebuild 전략"""
        
        if impact_level == ChangeImpactLevel.NONE:
            # Nothing to do
            logger.info("skip_rebuild", reason="comment_only")
            return
        
        elif impact_level == ChangeImpactLevel.LOCAL:
            # CFG/DFG만 rebuild
            self.rebuild_local_graphs(changed_file, new_ir)
        
        elif impact_level == ChangeImpactLevel.SIGNATURE:
            # Callers의 call edges만 update
            callers = self.find_direct_callers(changed_file, old_ir)
            for caller in callers:
                self.update_call_edges(caller, old_ir, new_ir)
        
        elif impact_level == ChangeImpactLevel.GLOBAL:
            # Full rebuild (current incremental과 동일)
            self.rebuild_full(changed_file, new_ir)
    
    def rebuild_local_graphs(self, file: str, ir: FileIR):
        """Local graphs만 rebuild (CFG, DFG)"""
        for func in ir.functions:
            # CFG
            cfg = self.cfg_builder.build(func)
            self.graph_store.update_cfg(func.symbol, cfg)
            
            # DFG
            dfg = self.dfg_builder.build(func)
            self.graph_store.update_dfg(func.symbol, dfg)
    
    def update_call_edges(
        self,
        caller_file: str,
        old_callee_ir: FileIR,
        new_callee_ir: FileIR
    ):
        """Call edges만 update"""
        # Old signature → new signature mapping
        signature_changes = self.compute_signature_changes(old_callee_ir, new_callee_ir)
        
        # Caller의 call sites update
        caller_ir = self.load_ir(caller_file)
        for call in caller_ir.calls:
            if call.target in signature_changes:
                new_signature = signature_changes[call.target]
                self.graph_store.update_call_edge(call.id, new_signature)
```

**Phase 3: Integration** (3일)
```python
# src/contexts/analysis_indexing/infrastructure/orchestrator_v2/impact_based_orchestrator.py

class ImpactBasedOrchestrator:
    """Impact-based incremental orchestrator"""
    
    async def handle_file_change(
        self,
        repo_id: str,
        changed_file: str
    ):
        """
        1. 변경 감지
        2. Impact level 분류
        3. Partial rebuild 실행
        """
        # Old content 로드
        old_content = await self.load_old_content(repo_id, changed_file)
        new_content = await self.load_file(changed_file)
        
        # Impact classification
        impact_level = self.classifier.classify_change(
            changed_file,
            old_content,
            new_content
        )
        
        logger.info(
            "change_detected",
            file=changed_file,
            impact_level=impact_level.name
        )
        
        # Partial rebuild
        old_ir = await self.load_ir(repo_id, changed_file)
        new_ir = await self.ir_builder.build(new_content)
        
        await self.partial_rebuilder.rebuild_by_impact(
            changed_file,
            impact_level,
            old_ir,
            new_ir
        )
```

#### 구현 위치
```
src/contexts/analysis_indexing/infrastructure/impact/
├── __init__.py
├── change_classifier.py       # NEW: 변경 영향도 분류
├── partial_rebuilder.py       # NEW: 부분 rebuild 전략
└── ast_diff.py                # NEW: AST diff 계산
```

#### 성능 목표
- Comment change: 0ms (skip)
- Local change: < 5ms (vs 50ms full rebuild)
- Signature change: < 20ms (vs 200ms affected files rebuild)
- Overall speedup: 2-5x over current incremental

---

### 2.2 Speculative Graph Execution
**Impact**: ⭐⭐⭐⭐⭐ (AI Agent 차별화)  
**Difficulty**: ⭐⭐⭐⭐⭐ (Very Hard)  
**Priority**: P1  
**Status**: 🚧 TODO (신규 기능)

#### 핵심 가치
- AI Agent가 **코드 변경을 제안하기 전에**
- **변경 후 그래프를 미리 계산**
- "What-if" 분석 가능
- **진짜 차세대 IDE 기능**

#### 사용 시나리오

**Scenario 1: Rename Impact Preview**
```python
# Agent: "이 함수 이름을 변경하면 어떻게 될까?"
preview = speculate_rename("old_func", "new_func")

print(preview.affected_files)      # 영향받는 파일 목록
print(preview.call_graph_changes)  # Call graph 변화
print(preview.breaking_changes)    # Breaking changes 목록
print(preview.test_impact)         # 영향받는 테스트

# Agent가 preview를 보고 안전성 판단 후 실행
```

**Scenario 2: Refactoring Simulation**
```python
# Agent: "이 코드를 다른 파일로 옮기면?"
patch = generate_move_patch("src/utils.py", "src/core/utils.py")

preview = speculate_apply(patch)

print(preview.import_changes)      # Import 구조 변화
print(preview.dependency_graph)    # 의존성 그래프 변화
print(preview.circular_deps)       # 순환 의존성 발생 여부
```

**Scenario 3: Parameter Addition**
```python
# Agent: "함수에 파라미터를 추가하면?"
preview = speculate_add_parameter(
    func="process_user",
    param="role: str",
    default_value="'guest'"
)

print(preview.all_call_sites)      # 모든 호출 지점
print(preview.need_update)         # 업데이트 필요한 호출들
print(preview.safe_with_default)   # Default로 안전한지
```

#### 구현 전략

**Phase 1: Virtual IR Layer** (2주)
```python
# src/contexts/code_foundation/infrastructure/speculative/virtual_ir.py

class VirtualIR:
    """가상 IR (실제 적용 안 됨)"""
    
    def __init__(self, base_ir: RepositoryIR):
        self.base = base_ir
        self.overlays: List[IRPatch] = []
    
    def apply_patch(self, patch: IRPatch) -> 'VirtualIR':
        """
        Patch를 가상으로 적용 (immutable):
        - Rename
        - Move
        - Add/Remove parameter
        - Change signature
        """
        new_virtual = VirtualIR(self.base)
        new_virtual.overlays = self.overlays + [patch]
        return new_virtual
    
    def get_symbol(self, symbol_id: str) -> Optional[Symbol]:
        """
        Symbol 조회 (overlay 우선):
        1. Overlay에서 찾기
        2. 없으면 base에서 찾기
        """
        for patch in reversed(self.overlays):
            if symbol_id in patch.changes:
                return patch.changes[symbol_id]
        
        return self.base.get_symbol(symbol_id)
    
    def compute_call_graph(self) -> CallGraph:
        """가상 IR에서 call graph 계산"""
        cg = CallGraph()
        
        # 모든 symbols (base + overlays)
        all_symbols = self.get_all_symbols()
        
        for symbol in all_symbols:
            for call in symbol.calls:
                target = self.resolve_call(call)  # Virtual resolution
                cg.add_edge(symbol.id, target)
        
        return cg

@dataclass
class IRPatch:
    """IR 변경 patch"""
    patch_type: str  # "rename", "move", "add_param", ...
    changes: Dict[str, Symbol]  # symbol_id -> new symbol
    metadata: Dict[str, Any]
```

**Phase 2: Speculative Analyzer** (2주)
```python
# src/contexts/analysis_indexing/infrastructure/speculative/speculative_analyzer.py

class SpeculativeAnalyzer:
    """Speculative 분석"""
    
    def speculate_rename(
        self,
        repo_id: str,
        old_name: str,
        new_name: str
    ) -> SpeculativeResult:
        """
        Rename 시뮬레이션:
        1. Base IR 로드
        2. Rename patch 생성
        3. Virtual IR 생성
        4. Virtual graph 계산
        5. Diff 계산
        """
        base_ir = self.load_ir(repo_id)
        
        # Rename patch
        patch = self.create_rename_patch(old_name, new_name, base_ir)
        
        # Virtual IR
        virtual_ir = VirtualIR(base_ir).apply_patch(patch)
        
        # Compute graphs
        base_cg = base_ir.call_graph
        virtual_cg = virtual_ir.compute_call_graph()
        
        # Compute diff
        cg_diff = self.compute_graph_diff(base_cg, virtual_cg)
        
        return SpeculativeResult(
            patch=patch,
            affected_files=patch.affected_files,
            call_graph_diff=cg_diff,
            breaking_changes=self.detect_breaking_changes(cg_diff),
            test_impact=self.compute_test_impact(cg_diff)
        )
    
    def speculate_apply_patch(
        self,
        repo_id: str,
        code_patch: str  # Git diff format
    ) -> SpeculativeResult:
        """
        임의의 code patch 시뮬레이션:
        1. Patch 파싱
        2. Affected files 파싱
        3. Virtual IR 생성
        4. Graphs 계산
        5. Impact 분석
        """
        base_ir = self.load_ir(repo_id)
        
        # Parse patch
        parsed_patch = self.parse_git_patch(code_patch)
        
        # Build virtual IR
        virtual_ir = VirtualIR(base_ir)
        for file_change in parsed_patch.changes:
            file_patch = self.build_file_patch(file_change)
            virtual_ir = virtual_ir.apply_patch(file_patch)
        
        # Compute all graphs
        virtual_cg = virtual_ir.compute_call_graph()
        virtual_imports = virtual_ir.compute_import_graph()
        virtual_deps = virtual_ir.compute_dependency_graph()
        
        # Detect issues
        circular_deps = self.detect_circular_dependencies(virtual_deps)
        breaking_changes = self.detect_breaking_changes(virtual_cg)
        
        return SpeculativeResult(
            call_graph=virtual_cg,
            import_graph=virtual_imports,
            dependency_graph=virtual_deps,
            circular_dependencies=circular_deps,
            breaking_changes=breaking_changes
        )
```

**Phase 3: Agent Integration** (1주)
```python
# src/contexts/agent_automation/infrastructure/tools/speculative_tool.py

class SpeculativeTool:
    """Agent에서 사용하는 speculative tool"""
    
    async def preview_refactor(
        self,
        refactor_type: str,  # "rename", "move", "extract", ...
        **kwargs
    ) -> Dict[str, Any]:
        """
        Agent가 refactor를 실행하기 전에 preview:
        
        예:
        preview = await tool.preview_refactor(
            refactor_type="rename",
            old_name="process",
            new_name="process_user"
        )
        
        if preview["risk_level"] == "low":
            # 안전 → 실행
            await tool.apply_refactor(...)
        else:
            # 위험 → 사용자에게 확인
            await ask_user_confirmation(preview)
        """
        result = await self.speculative_analyzer.speculate(
            refactor_type,
            **kwargs
        )
        
        return {
            "affected_files": result.affected_files,
            "call_graph_changes": result.call_graph_diff.summary(),
            "breaking_changes": result.breaking_changes,
            "risk_level": self.assess_risk(result),
            "recommendations": self.generate_recommendations(result)
        }
```

#### 구현 위치
```
src/contexts/code_foundation/infrastructure/speculative/
├── __init__.py
├── virtual_ir.py              # NEW: Virtual IR layer
├── ir_patch.py                # NEW: IR patch model
└── patch_builder.py           # NEW: Patch 생성

src/contexts/analysis_indexing/infrastructure/speculative/
├── speculative_analyzer.py    # NEW: Speculative 분석
├── graph_diff.py              # NEW: Graph diff 계산
└── risk_assessor.py           # NEW: Risk 평가

src/contexts/agent_automation/infrastructure/tools/
└── speculative_tool.py        # NEW: Agent tool
```

#### 성능 목표
- Virtual IR creation: < 100ms
- Speculative analysis: < 500ms (small refactor)
- Memory overhead: < 2x base IR size

---

### 2.3 Semantic Change Detection
**Impact**: ⭐⭐⭐⭐ (PR 리뷰 품질 +40%)  
**Difficulty**: ⭐⭐⭐⭐ (Hard)  
**Priority**: P1  
**Status**: 🚧 TODO

#### 핵심 가치
- Git diff: 단순 text diff
- Graph diff: 구조 diff
- **Semantic diff: 의미 변화 추적**
- PR 리뷰 품질 40% 증가
- Breaking changes 자동 예측

#### Semantic Change 종류

```python
# 1. Parameter removed (breaking!)
- def process(x, y, z):
+ def process(x, y):

# 2. Return type changed (breaking!)
- def get_user() -> User:
+ def get_user() -> Optional[User]:

# 3. Side-effect added (semantic change!)
def calculate(x):
-   return x * 2
+   log_metric("calc", x)  # Side-effect!
+   return x * 2

# 4. Error propagation changed
- def load(): return data
+ def load(): raise FileNotFoundError()  # NEW exception!

# 5. Reachable-set changed
def main():
-   safe_operation()
+   dangerous_operation()  # Different call target!
```

#### 구현 전략

**Phase 1: Semantic Diff Engine** (2주)
```python
# src/contexts/analysis_indexing/infrastructure/semantic_diff/diff_engine.py

class SemanticChange(Enum):
    """Semantic change 종류"""
    PARAM_ADDED = "param_added"
    PARAM_REMOVED = "param_removed"
    RETURN_TYPE_CHANGED = "return_type_changed"
    SIDE_EFFECT_ADDED = "side_effect_added"
    EXCEPTION_ADDED = "exception_added"
    CALL_TARGET_CHANGED = "call_target_changed"
    REACHABLE_SET_CHANGED = "reachable_set_changed"

@dataclass
class SemanticChangeRecord:
    """Semantic change 기록"""
    change_type: SemanticChange
    symbol: str
    old_value: Any
    new_value: Any
    severity: str  # "breaking", "warning", "info"
    affected_symbols: Set[str]

class SemanticDiffEngine:
    """Semantic diff 계산"""
    
    def compute_semantic_diff(
        self,
        old_ir: RepositoryIR,
        new_ir: RepositoryIR
    ) -> List[SemanticChangeRecord]:
        """
        Semantic changes 탐지:
        1. Symbol-level diff
        2. Graph-level diff
        3. Behavior-level diff
        """
        changes = []
        
        # Symbol signature changes
        changes.extend(self.detect_signature_changes(old_ir, new_ir))
        
        # Side-effect changes
        changes.extend(self.detect_side_effect_changes(old_ir, new_ir))
        
        # Exception changes
        changes.extend(self.detect_exception_changes(old_ir, new_ir))
        
        # Call graph changes
        changes.extend(self.detect_call_changes(old_ir, new_ir))
        
        # Reachability changes
        changes.extend(self.detect_reachability_changes(old_ir, new_ir))
        
        return changes
    
    def detect_signature_changes(
        self,
        old_ir: RepositoryIR,
        new_ir: RepositoryIR
    ) -> List[SemanticChangeRecord]:
        """Signature 변경 탐지"""
        changes = []
        
        for symbol_id in old_ir.symbols & new_ir.symbols:
            old_sym = old_ir.get_symbol(symbol_id)
            new_sym = new_ir.get_symbol(symbol_id)
            
            # Parameter 변경
            old_params = set(old_sym.parameters.keys())
            new_params = set(new_sym.parameters.keys())
            
            if old_params != new_params:
                removed = old_params - new_params
                added = new_params - old_params
                
                if removed:
                    # Breaking change!
                    changes.append(SemanticChangeRecord(
                        change_type=SemanticChange.PARAM_REMOVED,
                        symbol=symbol_id,
                        old_value=removed,
                        new_value=None,
                        severity="breaking",
                        affected_symbols=self.find_callers(symbol_id, old_ir)
                    ))
            
            # Return type 변경
            if old_sym.return_type != new_sym.return_type:
                changes.append(SemanticChangeRecord(
                    change_type=SemanticChange.RETURN_TYPE_CHANGED,
                    symbol=symbol_id,
                    old_value=old_sym.return_type,
                    new_value=new_sym.return_type,
                    severity=self.assess_return_type_change(
                        old_sym.return_type,
                        new_sym.return_type
                    ),
                    affected_symbols=self.find_callers(symbol_id, old_ir)
                ))
        
        return changes
```

**Phase 2: PR Analysis Tool** (1주)
```python
# src/contexts/analysis_indexing/infrastructure/semantic_diff/pr_analyzer.py

class PRAnalyzer:
    """PR semantic 분석"""
    
    def analyze_pr(
        self,
        repo_path: Path,
        base_commit: str,
        head_commit: str
    ) -> PRAnalysisReport:
        """
        PR의 semantic impact 분석:
        1. Base IR 빌드
        2. Head IR 빌드
        3. Semantic diff 계산
        4. Risk 평가
        5. Report 생성
        """
        # Build IRs
        base_ir = self.build_ir_at_commit(repo_path, base_commit)
        head_ir = self.build_ir_at_commit(repo_path, head_commit)
        
        # Semantic diff
        semantic_changes = self.diff_engine.compute_semantic_diff(base_ir, head_ir)
        
        # Group by severity
        breaking = [c for c in semantic_changes if c.severity == "breaking"]
        warnings = [c for c in semantic_changes if c.severity == "warning"]
        info = [c for c in semantic_changes if c.severity == "info"]
        
        # Risk assessment
        risk_level = self.assess_pr_risk(semantic_changes)
        
        return PRAnalysisReport(
            breaking_changes=breaking,
            warnings=warnings,
            info=info,
            risk_level=risk_level,
            affected_files=self.compute_affected_files(semantic_changes),
            test_recommendations=self.recommend_tests(semantic_changes)
        )
```

**Phase 3: GitHub Integration** (3일)
```python
# src/contexts/analysis_indexing/infrastructure/semantic_diff/github_bot.py

class SemanticDiffBot:
    """GitHub bot for semantic diff comments"""
    
    async def comment_on_pr(
        self,
        pr_number: int,
        report: PRAnalysisReport
    ):
        """
        PR에 semantic diff 코멘트:
        
        예:
        ## 🔍 Semantic Analysis
        
        ### ⚠️ Breaking Changes (2)
        - `process_user`: Parameter `role` removed
          - Affects 15 call sites
          - Files: `main.py`, `api.py`, ...
        
        - `get_data`: Return type changed `User` → `Optional[User]`
          - Callers may need null checks
          - Affects 8 call sites
        
        ### 💡 Recommendations
        - Add default value for `role` parameter
        - Update callers to handle `None` return
        - Add tests for null case
        """
        comment = self.format_report(report)
        await self.github_client.create_pr_comment(pr_number, comment)
```

#### 구현 위치
```
src/contexts/analysis_indexing/infrastructure/semantic_diff/
├── __init__.py
├── diff_engine.py             # NEW: Semantic diff engine
├── pr_analyzer.py             # NEW: PR analysis
├── risk_assessor.py           # NEW: Risk 평가
└── github_bot.py              # NEW: GitHub integration
```

---

### 2.4 AutoRRF – Query Fusion Auto Weighting
**Impact**: ⭐⭐⭐⭐ (검색 정확도 +25%)  
**Difficulty**: ⭐⭐⭐ (Medium-Hard)  
**Priority**: P1  
**Status**: 🚧 TODO (Retrieval 확장)

#### 핵심 가치
- 현재: RRF 기반 weighted fusion (정적 weight)
- 목표: **쿼리 의도에 따라 weight 자동 조정**
- LLM feedback으로 self-tuning

#### 구현 전략

**Phase 1: Query Intent Classifier** (1주)
```python
# src/contexts/retrieval_search/infrastructure/auto_rrf/intent_classifier.py

class QueryIntent(Enum):
    """Query 의도"""
    CALL_REFERENCE = "call_reference"      # "어디서 호출?"
    DEFINITION = "definition"              # "정의 찾기"
    EXPLANATION = "explanation"            # "설명해줘"
    REFACTOR_LOCATION = "refactor"         # "리팩터 위치"
    SIMILAR_CODE = "similar"               # "비슷한 코드"

class IntentClassifier:
    """Query 의도 분류"""
    
    async def classify(self, query: str) -> QueryIntent:
        """
        LLM으로 query 의도 분류:
        
        예:
        - "이 API 어디서 호출?" → CALL_REFERENCE
        - "이 로직 설명해줘" → EXPLANATION
        - "정확한 refactor 위치" → REFACTOR_LOCATION
        """
        prompt = f"""
        Classify the intent of this code search query:
        
        Query: "{query}"
        
        Intents:
        - call_reference: Finding where a function/API is called
        - definition: Finding symbol definition
        - explanation: Explaining code logic/behavior
        - refactor: Finding exact location for refactoring
        - similar: Finding similar code patterns
        
        Return only the intent name.
        """
        
        response = await self.llm_client.complete(prompt)
        return QueryIntent(response.strip().lower())
```

**Phase 2: Auto Weight Tuner** (2주)
```python
# src/contexts/retrieval_search/infrastructure/auto_rrf/auto_tuner.py

@dataclass
class RetrievalWeights:
    """Retrieval weights per intent"""
    graph_weight: float       # Call graph, import graph
    embedding_weight: float   # Vector similarity
    symbol_weight: float      # Exact symbol match
    keyword_weight: float     # Keyword search

class AutoWeightTuner:
    """Intent 기반 자동 weight 조정"""
    
    def __init__(self):
        # Intent별 base weights
        self.intent_weights = {
            QueryIntent.CALL_REFERENCE: RetrievalWeights(
                graph_weight=0.5,      # Graph 중요!
                embedding_weight=0.2,
                symbol_weight=0.2,
                keyword_weight=0.1
            ),
            QueryIntent.EXPLANATION: RetrievalWeights(
                graph_weight=0.1,
                embedding_weight=0.6,  # Embedding 중요!
                symbol_weight=0.1,
                keyword_weight=0.2
            ),
            QueryIntent.REFACTOR_LOCATION: RetrievalWeights(
                graph_weight=0.2,
                embedding_weight=0.1,
                symbol_weight=0.5,     # Exact match 중요!
                keyword_weight=0.2
            ),
            QueryIntent.DEFINITION: RetrievalWeights(
                graph_weight=0.3,
                embedding_weight=0.1,
                symbol_weight=0.5,
                keyword_weight=0.1
            ),
            QueryIntent.SIMILAR_CODE: RetrievalWeights(
                graph_weight=0.1,
                embedding_weight=0.7,  # Embedding 중요!
                symbol_weight=0.1,
                keyword_weight=0.1
            )
        }
        
        # Learning data (feedback 축적)
        self.feedback_db = FeedbackDatabase()
    
    def get_weights(
        self,
        intent: QueryIntent,
        query: str
    ) -> RetrievalWeights:
        """
        Intent + 과거 feedback으로 weight 결정:
        1. Base weights (intent별)
        2. Similar query feedback 참고
        3. Adjusted weights 반환
        """
        base_weights = self.intent_weights[intent]
        
        # Similar query feedback
        similar_queries = self.feedback_db.find_similar(query)
        if similar_queries:
            adjustments = self.compute_adjustments(similar_queries)
            return self.apply_adjustments(base_weights, adjustments)
        
        return base_weights
    
    def learn_from_feedback(
        self,
        query: str,
        intent: QueryIntent,
        used_weights: RetrievalWeights,
        user_feedback: float  # 0.0 ~ 1.0 (만족도)
    ):
        """
        사용자 feedback으로 학습:
        - 만족도 높음 (>0.8) → weights 강화
        - 만족도 낮음 (<0.4) → weights 조정 필요
        """
        self.feedback_db.record(
            query=query,
            intent=intent,
            weights=used_weights,
            satisfaction=user_feedback
        )
        
        # Periodic retuning
        if self.feedback_db.size() % 100 == 0:
            self.retune_weights()
```

**Phase 3: Adaptive Retriever** (1주)
```python
# src/contexts/retrieval_search/infrastructure/auto_rrf/adaptive_retriever.py

class AdaptiveRetriever:
    """AutoRRF 기반 adaptive retrieval"""
    
    async def retrieve(
        self,
        query: str,
        repo_id: str
    ) -> List[RetrievalResult]:
        """
        Adaptive retrieval:
        1. Query intent 분류
        2. Intent에 맞는 weights 결정
        3. Multi-index 검색 (가중치 적용)
        4. RRF fusion
        5. Re-ranking
        """
        # Intent classification
        intent = await self.intent_classifier.classify(query)
        
        # Get weights
        weights = self.weight_tuner.get_weights(intent, query)
        
        logger.info(
            "adaptive_retrieval",
            intent=intent.value,
            weights=weights.__dict__
        )
        
        # Multi-index search
        graph_results = await self.graph_searcher.search(query, repo_id)
        embedding_results = await self.vector_searcher.search(query, repo_id)
        symbol_results = await self.symbol_searcher.search(query, repo_id)
        keyword_results = await self.keyword_searcher.search(query, repo_id)
        
        # Weighted RRF fusion
        fused = self.weighted_rrf_fusion(
            [
                (graph_results, weights.graph_weight),
                (embedding_results, weights.embedding_weight),
                (symbol_results, weights.symbol_weight),
                (keyword_results, weights.keyword_weight)
            ],
            k=60
        )
        
        return fused
    
    def weighted_rrf_fusion(
        self,
        results_with_weights: List[Tuple[List[Result], float]],
        k: int = 60
    ) -> List[Result]:
        """
        Weighted RRF:
        score = Σ (weight_i * 1 / (k + rank_i))
        """
        scores = defaultdict(float)
        
        for results, weight in results_with_weights:
            for rank, result in enumerate(results):
                rrf_score = weight / (k + rank)
                scores[result.id] += rrf_score
        
        # Sort by score
        sorted_results = sorted(scores.items(), key=lambda x: -x[1])
        return [result_id for result_id, score in sorted_results]
```

#### 구현 위치
```
src/contexts/retrieval_search/infrastructure/auto_rrf/
├── __init__.py
├── intent_classifier.py       # NEW: Query intent 분류
├── auto_tuner.py              # NEW: Auto weight tuning
├── adaptive_retriever.py      # NEW: Adaptive retrieval
└── feedback_db.py             # NEW: Feedback 저장
```

---

## 📅 Implementation Timeline

### Phase 1 (4주) - P0 핵심 기능
**목표**: Must-Have 18/18 달성 + Type Narrowing 완성

| Week | Tasks | Deliverables |
|------|-------|--------------|
| W1 | Local Overlay (Phase 1-2) | Overlay IR Builder, Graph Merger |
| W2 | Local Overlay (Phase 3-4) + Testing | LSP Integration, Tests |
| W3 | Full Type Narrowing (Phase 1-2) | CFG-based Type State, Call Graph Precision |
| W4 | Full Type Narrowing (Phase 3) + Testing | IR Integration, Tests |

**완료 시 상태**:
- ✅ Must-Have: 18/18 (100%)
- ✅ Call Graph Precision: +30%
- ✅ IDE/Agent Accuracy: +30-50%

---

### Phase 2 (6주) - P0 고급 기능
**목표**: Context-Sensitive + SRI 완성

| Week | Tasks | Deliverables |
|------|-------|--------------|
| W5-6 | Context-Sensitive Call Graph (Phase 1-2) | Call Context, Value Tracking |
| W7-8 | Context-Sensitive Call Graph (Phase 3-4) | CS Analysis, Impact Analysis |
| W9-10 | Semantic Region Index (Phase 1-3) | Region Segmentation, Annotation, Index |
| W11 | SRI (Phase 4) + Integration Testing | Retrieval Integration, E2E Tests |

**완료 시 상태**:
- ✅ Context-Sensitive Call Graph
- ✅ Semantic Region Index
- ✅ **업계 SOTA 확정**

---

### Phase 3 (6주) - P1 차세대 기능
**목표**: Speculative + Semantic Diff 완성

| Week | Tasks | Deliverables |
|------|-------|--------------|
| W12-13 | Impact-Based Partial Rebuild | Change Classifier, Partial Rebuilder |
| W14-16 | Speculative Graph Execution | Virtual IR, Speculative Analyzer |
| W17-18 | Semantic Change Detection | Diff Engine, PR Analyzer |
| W19 | AutoRRF | Intent Classifier, Auto Tuner |

**완료 시 상태**:
- ✅ **차세대 기능 4개 완성**
- ✅ **세계 최고급 Code Intelligence Engine**

---

## 🎯 Success Metrics

### P0 완료 시
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Must-Have:        18/18 (100%) ✅
SCIP Advanced:    20/20 (100%) ✅
Call Graph:       Precision +30%
Type Narrowing:   TS/Python Full
Context-Sensitive: ✅
SRI:              ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: SOTA 확정 🏆
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### P1 완료 시
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
차세대 기능:      4/4 (100%) ✅
Speculative:      ✅
Semantic Diff:    ✅
AutoRRF:          ✅
Impact Rebuild:   ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: 세계 최고급 🌟
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🚀 Quick Start

### 우선순위 추천

**지금 당장 시작할 기능 (Impact 순)**:
1. **Local Overlay** (P0, Critical) - 정확도 즉시 30-50% 향상
2. **Full Type Narrowing** (P0, High) - Call Graph +30% precision
3. **Semantic Region Index** (P0, High) - LLM 차별화
4. **Context-Sensitive CG** (P0, Very High) - 세계 최고급

**Phase별 추천**:
- **Month 1**: Local Overlay + Type Narrowing → Must-Have 18/18
- **Month 2-3**: Context-Sensitive + SRI → SOTA 확정
- **Month 4-5**: Speculative + Semantic Diff → 차세대 엔진

---

## 📝 Notes

### 현재 구조 활용
이미 훌륭한 기반이 구축되어 있음:
- ✅ IR 시스템: `code_foundation` context
- ✅ Incremental Update: `change_detector.py`
- ✅ Type Narrowing 기본 구조: `type_narrowing_full.py`
- ✅ Graph 시스템: Kuzu-based
- ✅ Multi-index: Qdrant + Tantivy + Zoekt

### 추가 구현 패턴
모든 신규 기능은 기존 DDD 패턴 따름:
```
contexts/
└── {context_name}/
    ├── domain/
    │   ├── models.py      # Domain models
    │   └── ports.py       # Interfaces
    ├── infrastructure/
    │   └── {feature}.py   # Implementations
    └── usecase/
        └── {use_case}.py  # Use cases
```

---

**문서 작성 완료**  
**Date**: 2025-12-04  
**Version**: 1.0.0  
**Status**: Ready for Implementation 🚀

