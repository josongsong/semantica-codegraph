# RFC-052: MCP Service Layer Architecture

## Status: Draft
## Author: Codegraph Team
## Created: 2025-12-22

---

## 1. 문제 정의

### 현재 문제점

```
MCP Handler → container.query_engine() 직접 호출  ❌ 레이어 위반
MCP Handler → CallGraphQueryBuilder              ❌ 또 다른 경로
MCP Handler → SlicerAdapter                      ❌ 일관성 없음
```

- **레이어 위반**: MCP 핸들러가 Infrastructure 직접 접근
- **일관성 부재**: QueryEngine, CallGraphQueryBuilder, SlicerAdapter 혼용
- **테스트 어려움**: 비즈니스 로직이 핸들러에 분산
- **확장성 제한**: 새 기능 추가 시 패턴 불명확

---

## 2. 목표

1. **Hexagonal Architecture 준수**: MCP = Adapter, Service = Application Layer
2. **단일 쿼리 경로**: QueryEngine 기반 통합
3. **SOTA 차별화**: 타입 추론, 자동 수정 제안 등 고급 기능
4. **테스트 용이성**: Service 단위 테스트 가능

---

## 3. 아키텍처

### 3.1 레이어 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Handlers (Thin Adapter)                  │
│  server/mcp_server/handlers/                                    │
│  - 파라미터 검증                                                 │
│  - JSON 직렬화                                                   │
│  - 에러 핸들링                                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                Application Services (Business Logic)            │
│  src/contexts/code_foundation/application/services/             │
│  - GraphAnalysisService                                         │
│  - ContextService                                               │
│  - SearchService                                                │
│  - VerificationService                                          │
│  - AnalysisService                                              │
│  - TypeInferenceService  ⭐ SOTA                                │
│  - AutoFixService        ⭐ SOTA                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                         │
│  - QueryEngine (Query DSL)                                      │
│  - UnifiedGraphIndex                                            │
│  - IRAnalyzer                                                   │
│  - TaintAnalysisService                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Service 정의

```python
# ================================================================
# 1. GraphAnalysisService - 그래프/흐름 분석 (핵심)
# ================================================================
class GraphAnalysisService:
    """QueryEngine 기반 그래프 분석 통합 서비스"""
    
    def __init__(self, query_engine: QueryEngine, graph_index: UnifiedGraphIndex):
        self._engine = query_engine
        self._graph = graph_index
    
    # --- Slicing ---
    def slice(
        self, 
        anchor: str, 
        direction: Literal["backward", "forward", "both"] = "backward",
        max_depth: int = 5,
        max_lines: int = 100
    ) -> SliceResult:
        """Semantic slicing - 버그 root cause 최소 추출"""
    
    # --- Dataflow ---
    def dataflow(
        self,
        source: str,
        sink: str,
        policy: str | None = None  # sql_injection, xss, etc.
    ) -> DataflowResult:
        """Source → Sink 도달 가능성 증명"""
    
    def find_taint_flow(
        self,
        source_pattern: str,
        sink_pattern: str,
        max_depth: int = 10
    ) -> list[TaintPath]:
        """Taint flow 탐지 (QueryDSL: Q.Source >> Q.Sink)"""
    
    # --- Call Graph ---
    def get_callers(self, symbol: str, limit: int = 20) -> list[Caller]:
        """심볼을 호출하는 함수들"""
    
    def get_callees(self, symbol: str, limit: int = 20) -> list[Callee]:
        """심볼이 호출하는 함수들"""
    
    def find_call_chain(
        self,
        from_func: str,
        to_func: str,
        max_depth: int = 5
    ) -> list[CallChain]:
        """A → B 호출 경로 탐색 (QueryDSL: Q.Func >> Q.Func)"""
    
    # --- Data Dependency ---
    def find_data_dependency(
        self,
        from_var: str,
        to_var: str,
        max_hops: int = 5
    ) -> list[DependencyPath]:
        """변수 간 데이터 의존성 (QueryDSL: Q.Var >> Q.Var)"""
    
    # --- Impact Preview ---
    def preview_impact(
        self,
        changed_symbols: list[str],
        include_transitive: bool = True
    ) -> ImpactResult:
        """변경 영향 범위 미리보기"""
    
    def preview_taint_path(
        self,
        source: str,
        sink: str
    ) -> TaintPathPreview:
        """Taint path 미리보기 (lightweight)"""


# ================================================================
# 2. ContextService - 코드 컨텍스트
# ================================================================
class ContextService:
    """코드 위치 기반 컨텍스트 제공"""
    
    def __init__(self, ir_analyzer: IRAnalyzer, graph_index: UnifiedGraphIndex):
        self._ir = ir_analyzer
        self._graph = graph_index
    
    def get_context(
        self,
        file_path: str,
        line: int,
        radius: int = 10
    ) -> ContextResult:
        """특정 위치의 코드 컨텍스트"""
    
    def get_definition(self, symbol: str) -> DefinitionResult:
        """심볼 정의 위치"""
    
    def get_references(
        self,
        symbol: str,
        limit: int = 50
    ) -> list[Reference]:
        """심볼 참조 위치들"""
    
    def get_scope_variables(
        self,
        file_path: str,
        line: int
    ) -> list[ScopeVariable]:
        """해당 스코프에서 접근 가능한 변수들"""


# ================================================================
# 3. SearchService - 검색
# ================================================================
class SearchService:
    """심볼/청크 검색"""
    
    def __init__(self, chunk_store, retrieval_service):
        self._chunks = chunk_store
        self._retrieval = retrieval_service
    
    def search_symbols(
        self,
        query: str,
        kind: str | None = None,  # function, class, variable
        limit: int = 20
    ) -> list[SymbolMatch]:
        """심볼 검색 (fuzzy + semantic)"""
    
    def search_chunks(
        self,
        query: str,
        file_pattern: str | None = None,
        limit: int = 20
    ) -> list[ChunkMatch]:
        """청크 검색"""
    
    def get_symbol(self, fqn: str) -> Symbol | None:
        """FQN으로 심볼 조회"""
    
    def get_chunk(self, chunk_id: str) -> Chunk | None:
        """ID로 청크 조회"""


# ================================================================
# 4. VerificationService - 검증
# ================================================================
class VerificationService:
    """패치/수정 검증"""
    
    def __init__(self, compiler, linter, taint_service):
        self._compiler = compiler
        self._linter = linter
        self._taint = taint_service
    
    def verify_compile(self, patch: str, file_path: str) -> CompileResult:
        """패치 적용 후 컴파일 검증"""
    
    def verify_finding_resolved(
        self,
        finding_id: str,
        patch: str
    ) -> bool:
        """특정 취약점이 해결되었는지 검증"""
    
    def verify_no_new_findings(
        self,
        patch: str,
        file_path: str
    ) -> list[Finding]:
        """패치로 인한 새 취약점 탐지"""
    
    def verify_type_safety(
        self,
        patch: str,
        file_path: str
    ) -> TypeCheckResult:
        """타입 안전성 검증"""


# ================================================================
# 5. AnalysisService - 정적 분석
# ================================================================
class AnalysisService:
    """정적 분석 도구"""
    
    def __init__(self, ir_analyzer, complexity_analyzer):
        self._ir = ir_analyzer
        self._complexity = complexity_analyzer
    
    def analyze_cost(self, symbol: str) -> CostResult:
        """시간/공간 복잡도 분석"""
    
    def analyze_race(self, file_path: str) -> list[RaceCondition]:
        """Race condition 탐지"""
    
    def analyze_complexity(
        self,
        file_path: str,
        threshold: float = 10.0
    ) -> ComplexityResult:
        """Cyclomatic complexity 분석"""
    
    def analyze_cfg(self, function: str) -> CFGResult:
        """Control Flow Graph 분석"""
    
    def find_dead_code(self, file_path: str) -> list[DeadCode]:
        """Dead code 탐지"""


# ================================================================
# 6. TypeInferenceService - 타입 추론 ⭐ SOTA 차별화
# ================================================================
class TypeInferenceService:
    """타입 추론 서비스 (정적 분석 엔진 강점)"""
    
    def __init__(self, type_inference_engine, narrowing_engine):
        self._inference = type_inference_engine
        self._narrowing = narrowing_engine
    
    def get_type_info(
        self,
        symbol: str,
        file_path: str | None = None
    ) -> TypeInfo:
        """심볼의 추론된 타입 정보"""
    
    def get_narrowed_type(
        self,
        symbol: str,
        file_path: str,
        line: int
    ) -> NarrowedType:
        """특정 위치에서의 좁혀진 타입 (Type Narrowing)"""
    
    def get_possible_types(
        self,
        expression: str,
        context_file: str,
        context_line: int
    ) -> list[PossibleType]:
        """표현식의 가능한 타입들"""
    
    def check_type_compatibility(
        self,
        source_type: str,
        target_type: str
    ) -> TypeCompatibility:
        """타입 호환성 검사"""


# ================================================================
# 7. AutoFixService - 자동 수정 제안 ⭐ SOTA 차별화
# ================================================================
class AutoFixService:
    """취약점/이슈 자동 수정 제안"""
    
    def __init__(self, taint_service, fix_generator, template_engine):
        self._taint = taint_service
        self._generator = fix_generator
        self._templates = template_engine
    
    def suggest_fix(
        self,
        finding_id: str,
        strategy: Literal["sanitize", "validate", "escape"] = "sanitize"
    ) -> list[FixSuggestion]:
        """취약점에 대한 수정 제안"""
    
    def suggest_refactoring(
        self,
        symbol: str,
        issue_type: str  # complexity, duplication, naming
    ) -> list[RefactoringSuggestion]:
        """리팩토링 제안"""
    
    def explain_vulnerability(
        self,
        finding_id: str
    ) -> VulnerabilityExplanation:
        """취약점 원인 및 흐름 설명"""
    
    def generate_test(
        self,
        function: str,
        coverage_target: float = 0.8
    ) -> GeneratedTest:
        """테스트 코드 자동 생성"""
```

---

## 4. MCP Tool 매핑

### 4.1 완전한 MCP Tool 목록

| MCP Tool | Service | Method | SOTA |
|----------|---------|--------|------|
| `graph_slice` | GraphAnalysisService | `slice()` | |
| `graph_dataflow` | GraphAnalysisService | `dataflow()` | |
| `get_callers` | GraphAnalysisService | `get_callers()` | |
| `get_callees` | GraphAnalysisService | `get_callees()` | |
| `find_call_chain` | GraphAnalysisService | `find_call_chain()` | |
| `find_taint_flow` | GraphAnalysisService | `find_taint_flow()` | |
| `find_data_dependency` | GraphAnalysisService | `find_data_dependency()` | |
| `preview_impact` | GraphAnalysisService | `preview_impact()` | |
| `preview_taint_path` | GraphAnalysisService | `preview_taint_path()` | |
| `get_context` | ContextService | `get_context()` | |
| `get_definition` | ContextService | `get_definition()` | |
| `get_references` | ContextService | `get_references()` | |
| `get_scope_vars` | ContextService | `get_scope_variables()` | ⭐ |
| `search_symbols` | SearchService | `search_symbols()` | |
| `search_chunks` | SearchService | `search_chunks()` | |
| `get_symbol` | SearchService | `get_symbol()` | |
| `verify_compile` | VerificationService | `verify_compile()` | |
| `verify_resolved` | VerificationService | `verify_finding_resolved()` | |
| `verify_no_new` | VerificationService | `verify_no_new_findings()` | |
| `verify_types` | VerificationService | `verify_type_safety()` | ⭐ |
| `analyze_cost` | AnalysisService | `analyze_cost()` | |
| `analyze_race` | AnalysisService | `analyze_race()` | |
| `analyze_complexity` | AnalysisService | `analyze_complexity()` | |
| `analyze_cfg` | AnalysisService | `analyze_cfg()` | |
| `find_dead_code` | AnalysisService | `find_dead_code()` | |
| `get_type_info` | TypeInferenceService | `get_type_info()` | ⭐ |
| `get_narrowed_type` | TypeInferenceService | `get_narrowed_type()` | ⭐ |
| `suggest_fix` | AutoFixService | `suggest_fix()` | ⭐ |
| `explain_vuln` | AutoFixService | `explain_vulnerability()` | ⭐ |
| `generate_test` | AutoFixService | `generate_test()` | ⭐ |

### 4.2 MCP Handler 예시

```python
# server/mcp_server/handlers/graph_analysis.py

async def graph_slice(arguments: dict[str, Any]) -> str:
    """MCP Handler - Thin Adapter"""
    # 1. 파라미터 검증
    anchor = arguments.get("anchor")
    if not anchor:
        return json.dumps({"error": "anchor is required"})
    
    direction = arguments.get("direction", "backward")
    max_depth = arguments.get("max_depth", 5)
    
    # 2. Service 호출
    try:
        service = container.graph_analysis_service()
        result = service.slice(
            anchor=anchor,
            direction=direction,
            max_depth=max_depth
        )
        
        # 3. JSON 직렬화
        return result.to_json()
    
    except Exception as e:
        return json.dumps({"error": str(e)})


async def get_type_info(arguments: dict[str, Any]) -> str:
    """SOTA: 타입 추론 정보"""
    symbol = arguments.get("symbol")
    if not symbol:
        return json.dumps({"error": "symbol is required"})
    
    service = container.type_inference_service()
    result = service.get_type_info(
        symbol=symbol,
        file_path=arguments.get("file_path")
    )
    
    return result.to_json()


async def suggest_fix(arguments: dict[str, Any]) -> str:
    """SOTA: 자동 수정 제안"""
    finding_id = arguments.get("finding_id")
    if not finding_id:
        return json.dumps({"error": "finding_id is required"})
    
    service = container.auto_fix_service()
    suggestions = service.suggest_fix(
        finding_id=finding_id,
        strategy=arguments.get("strategy", "sanitize")
    )
    
    return json.dumps({
        "finding_id": finding_id,
        "suggestions": [s.to_dict() for s in suggestions]
    })
```

---

## 5. Container 통합

```python
# src/container.py

class Container:
    """DI Container with Service Layer"""
    
    # --- Infrastructure ---
    def query_engine(self) -> QueryEngine: ...
    def graph_index(self) -> UnifiedGraphIndex: ...
    def ir_analyzer(self) -> IRAnalyzer: ...
    def chunk_store(self) -> ChunkStore: ...
    
    # --- Application Services ---
    @cached
    def graph_analysis_service(self) -> GraphAnalysisService:
        return GraphAnalysisService(
            query_engine=self.query_engine(),
            graph_index=self.graph_index()
        )
    
    @cached
    def context_service(self) -> ContextService:
        return ContextService(
            ir_analyzer=self.ir_analyzer(),
            graph_index=self.graph_index()
        )
    
    @cached
    def search_service(self) -> SearchService:
        return SearchService(
            chunk_store=self.chunk_store(),
            retrieval_service=self.retrieval_service()
        )
    
    @cached
    def verification_service(self) -> VerificationService:
        return VerificationService(...)
    
    @cached
    def analysis_service(self) -> AnalysisService:
        return AnalysisService(...)
    
    # --- SOTA Services ---
    @cached
    def type_inference_service(self) -> TypeInferenceService:
        return TypeInferenceService(
            type_inference_engine=self.type_inference_engine(),
            narrowing_engine=self.narrowing_engine()
        )
    
    @cached
    def auto_fix_service(self) -> AutoFixService:
        return AutoFixService(
            taint_service=self.taint_analysis_service(),
            fix_generator=self.fix_generator(),
            template_engine=self.template_engine()
        )
```

---

## 6. 구현 계획

### Phase 1: Service Layer 기반 구축 (1-2일)
- [ ] Application Service 인터페이스 정의
- [ ] GraphAnalysisService 구현 (기존 로직 이전)
- [ ] Container 통합

### Phase 2: MCP Handler 리팩토링 (1일)
- [ ] 기존 핸들러 → Service 호출로 변경
- [ ] 테스트 추가

### Phase 3: SOTA 기능 추가 (2-3일)
- [ ] TypeInferenceService 구현
- [ ] AutoFixService 구현
- [ ] 새 MCP Tool 등록

### Phase 4: 통합 테스트 (1일)
- [ ] E2E 테스트
- [ ] 성능 벤치마크

---

## 7. 기대 효과

1. **아키텍처 정합성**: Hexagonal Architecture 준수
2. **테스트 용이성**: Service 단위 테스트 가능
3. **확장성**: 새 기능 추가 패턴 명확
4. **SOTA 차별화**: 타입 추론, 자동 수정 등 고급 기능
5. **일관성**: 단일 쿼리 경로 (QueryEngine)

---

## 8. 참고

- RFC-SEM-022: Graph Semantics MCP Protocol
- RFC-051: Template IR Integration
- Hexagonal Architecture (Ports & Adapters)

