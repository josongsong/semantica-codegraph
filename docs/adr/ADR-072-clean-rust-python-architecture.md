# ADR-072: Clean Rust-Python Architecture (Engine vs Consumer)

**Status**: Accepted
**Date**: 2025-12-28
**Authors**: Semantica Team
**Decision**: Establish clear architectural boundaries between Rust engine and Python consumers

---

## Context

현재 Semantica v2의 Rust-Python 통합에서 양방향 의존성이 존재하여 아키텍처가 복잡합니다:

1. **Rust → Python**: PyO3를 통한 Python API 노출
2. **Python → Rust**: `codegraph_ir` import를 통한 Rust 엔진 사용
3. **복잡한 의존성**: LayeredIRBuilder 등 Python 레거시 코드와 Rust 엔진의 혼재

이러한 양방향 의존성은 다음과 같은 문제를 야기합니다:
- 순환 의존성으로 인한 빌드 복잡도 증가
- 책임 경계 불명확 (어떤 로직이 어디서 실행되어야 하는지)
- 테스트 및 유지보수 어려움

---

## Decision

**Rust를 엔진(Engine)으로, Python을 소비자(Consumer)로 명확히 분리**합니다.

### 핵심 원칙

1. **Rust = Analysis Engine (Core)**
   - 모든 코드 분석 로직은 Rust에서 구현
   - Python에 대한 의존성 **완전 제거**
   - 단, Language Plugin으로만 Python 호출 허용 (파싱용)

2. **Python = Engine Consumer (Application Layer)**
   - Rust 엔진을 사용하는 역할만 수행
   - API Server, MCP Server, CLI 등 애플리케이션 레이어
   - 비즈니스 로직 및 워크플로우 조율

3. **단방향 의존성: Rust ← Python**
   - Python은 Rust를 import (`import codegraph_ir`)
   - Rust는 Python을 import하지 않음 (Language Plugin 제외)

---

## Architecture

### Layer 구조

```
┌─────────────────────────────────────────────────────────────┐
│                   APPLICATION LAYER (Python)                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ API Server │  │ MCP Server │  │  CLI/Tools │            │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘            │
│         │                │                │                  │
│         └────────────────┴────────────────┘                  │
│                          │                                   │
│                   import codegraph_ir                        │
└──────────────────────────┼───────────────────────────────────┘
                           │ (PyO3 Bindings)
┌──────────────────────────▼───────────────────────────────────┐
│                    ANALYSIS ENGINE (Rust)                     │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  IRIndexingOrchestrator (Full Repository Indexing)     │ │
│  │  - L1-L8 Pipeline (IR, CFG, DFG, Taint, etc.)         │ │
│  │  - Parallel processing (Rayon)                         │ │
│  │  - Zero Python dependency                              │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  MultiLayerIndexOrchestrator (Incremental Updates)     │ │
│  │  - MVCC transaction support                            │ │
│  │  - Plugin-based index system                           │ │
│  │  - Lock-free concurrent updates                        │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Query Engine (Lexical, Semantic, Graph)               │ │
│  │  - Tantivy (lexical search)                            │ │
│  │  - Graph traversal                                     │ │
│  │  - Clone detection                                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                          ▲                                   │
│                          │ (Plugin Interface)                │
│                   Language Parsers                           │
└──────────────────────────┼───────────────────────────────────┘
                           │
              ┌────────────┴────────────┐
              │                         │
    ┌─────────▼──────────┐   ┌─────────▼──────────┐
    │ Tree-sitter        │   │ LSP Servers        │
    │ (Rust native)      │   │ (External process) │
    └────────────────────┘   └────────────────────┘
```

### 의존성 규칙

| Component | Can Import | Cannot Import |
|-----------|-----------|---------------|
| **Rust Engine** | Tree-sitter, External LSP servers | Python modules (except via plugin) |
| **Python Apps** | `codegraph_ir` (Rust), Python stdlib | Direct Rust code manipulation |
| **Language Plugins** | Language-specific parsers | Analysis logic |

---

## Implementation Plan

### Phase 1: Rust Engine 독립성 확보 ✅

**Status**: 이미 대부분 완료됨

- [x] IRIndexingOrchestrator (7,520 LOC) - Python 의존성 없음
- [x] MultiLayerIndexOrchestrator (4,160 LOC) - Python 의존성 없음
- [x] Lexical Search (Tantivy) - Python 의존성 없음
- [x] Clone Detection - Python 의존성 없음

### Phase 2: Python → Rust 의존성 정리 (이번 작업)

**목표**: Python 코드에서 Rust를 명확하게 소비자로만 사용

#### 2.1. LayeredIRBuilder 제거/Deprecate

**현재 상태**:
```python
# packages/codegraph-engine/.../layered_ir_builder.py
class LayeredIRBuilder:
    """9-layer IR construction pipeline"""
    # 레거시 Python IR 빌드 로직
```

**제거 계획**:
1. LayeredIRBuilder를 deprecated로 표시 (현재 이미 표시됨)
2. 모든 사용처를 `codegraph_ir.IRIndexingOrchestrator`로 마이그레이션
3. LayeredIRBuilder 삭제

**Migration Path**:
```python
# Before (Python LayeredIRBuilder)
from codegraph_engine.code_foundation.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

builder = LayeredIRBuilder(config)
result = await builder.build_all(repo_path)

# After (Rust Engine)
import codegraph_ir

config = codegraph_ir.E2EPipelineConfig(
    root_path=repo_path,
    parallel_workers=4,
    enable_chunking=True,
)
orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()
```

#### 2.2. IRBuildHandler 단순화

**현재 상태**:
```python
# packages/codegraph-shared/.../ir_handler.py
class IRBuildHandler(JobHandler):
    def __init__(self):
        self.use_rust_ir = os.getenv("USE_RUST_IR", "true").lower() == "true"

    async def execute(self, payload):
        if self.use_rust_ir:
            # Rust 사용
            pass
        else:
            # LayeredIRBuilder 사용 (레거시)
            pass
```

**변경 후**:
```python
# packages/codegraph-shared/.../ir_handler.py
class IRBuildHandler(JobHandler):
    """IR Build using Rust engine only."""

    async def execute(self, payload):
        # Always use Rust
        import codegraph_ir

        config = codegraph_ir.E2EPipelineConfig(...)
        orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
        result = orchestrator.execute()
        return JobResult.success(data=result.to_dict())
```

#### 2.3. Cross-File Handler 마이그레이션

**현재 상태**:
```python
# packages/codegraph-shared/.../cross_file_handler.py
class CrossFileHandler(JobHandler):
    """Python 기반 cross-file resolution"""
```

**변경 후**:
Rust의 L3 (Cross-File) stage가 이미 구현되어 있으므로:
```python
# 삭제 또는 Rust 호출로 단순화
# L3는 IRIndexingOrchestrator 내부에서 자동 실행됨
```

### Phase 3: Language Plugin Interface 명확화

**현재 상태**: Rust에서 직접 Tree-sitter 사용

**개선 방향**: Plugin 인터페이스 명확화
```rust
// packages/codegraph-rust/codegraph-ir/src/features/parsing/ports/language_plugin.rs

pub trait LanguagePlugin: Send + Sync {
    /// Language identifier
    fn language(&self) -> Language;

    /// Parse source code to AST
    fn parse(&self, source: &str) -> Result<ParsedAst, ParseError>;

    /// Extract IR nodes from AST
    fn extract_nodes(&self, ast: &ParsedAst) -> Vec<Node>;

    /// Extract IR edges from AST
    fn extract_edges(&self, ast: &ParsedAst) -> Vec<Edge>;
}
```

**현재 구현**:
- ✅ Tree-sitter 기반 (Rust native)
- ❌ Python 기반 parser는 아직 없음 (필요시 추가)

**Python Parser Plugin (선택사항)**:
```python
# packages/codegraph-parsers/python_parser.py
class PythonParserPlugin:
    """Custom Python parser using ast module"""

    def parse(self, source: str) -> dict:
        """Returns msgpack-compatible AST"""
        tree = ast.parse(source)
        return self._ast_to_dict(tree)
```

```rust
// Rust에서 Python parser 호출 (필요시)
pub fn parse_with_python_plugin(source: &str) -> Result<ParsedAst> {
    // PyO3를 통해 Python parser 호출
    Python::with_gil(|py| {
        let parser = py.import("codegraph_parsers.python_parser")?;
        let result = parser.call_method1("parse", (source,))?;
        Ok(msgpack::from_slice(result.extract()?)?)
    })
}
```

---

## API Boundaries

### Rust → Python (PyO3 Bindings)

**Exposed API** (`codegraph_ir` Python module):

```python
# 1. IRIndexingOrchestrator
from codegraph_ir import IRIndexingOrchestrator, E2EPipelineConfig

config = E2EPipelineConfig(
    root_path="/repo",
    parallel_workers=4,
    enable_chunking=True,
    enable_repomap=True,
)
orchestrator = IRIndexingOrchestrator(config)
result = orchestrator.execute()

# 2. MultiLayerIndexOrchestrator
from codegraph_ir import MultiLayerIndexOrchestrator, IndexOrchestratorConfig

orchestrator = MultiLayerIndexOrchestrator(config)
session = orchestrator.begin_session("agent_1")
orchestrator.add_change("agent_1", {"op": "add_node", "node": {...}})
result = orchestrator.commit("agent_1")

# 3. Query Engine
from codegraph_ir import QueryEngine

engine = QueryEngine(index_path="/index")
results = engine.lexical_search("function")
results = engine.semantic_search(embedding=[...])
```

**No Python → Rust imports except**: `import codegraph_ir`

### Python → Rust (Consumer Only)

**Python Applications**:
- API Server (`server/api_server/`)
- MCP Server (`server/mcp_server/`)
- CLI Tools (`tools/`)
- Job Handlers (`packages/codegraph-shared/infra/jobs/handlers/`)

**Rules**:
1. ✅ `import codegraph_ir` allowed
2. ❌ Direct manipulation of Rust internals forbidden
3. ✅ Configuration via Python dataclasses → Rust structs
4. ❌ Python logic should not be called from Rust (except parsers)

---

## Migration Checklist

### Immediate Actions (Phase 2)

- [ ] Mark LayeredIRBuilder as deprecated with removal date
- [ ] Update IRBuildHandler to use Rust engine only
- [ ] Remove USE_RUST_IR environment variable (always use Rust)
- [ ] Migrate CrossFileHandler to use Rust L3 stage
- [ ] Update all Python tests to use `codegraph_ir` directly
- [ ] Remove Python-based IR building code

### Documentation Updates

- [ ] Update CLAUDE.md with new architecture
- [ ] Update system handbook
- [ ] Create migration guide for existing code
- [ ] Document PyO3 API reference

### Testing

- [ ] Verify all Python tests pass with Rust-only engine
- [ ] Add integration tests for PyO3 boundary
- [ ] Performance benchmarks (Rust vs Python)

---

## Benefits

### 1. **명확한 책임 분리**
- Rust: 성능이 중요한 분석 엔진
- Python: 비즈니스 로직 및 워크플로우

### 2. **개발 속도 향상**
- Rust 개발자: Python 코드 신경 쓸 필요 없음
- Python 개발자: Rust를 라이브러리로 사용

### 3. **테스트 단순화**
- Rust: 순수 Rust 테스트 (cargo test)
- Python: Rust를 모킹하여 테스트

### 4. **성능 최적화**
- Rust에서 GIL 없이 병렬 처리
- Python에서 orchestration만 담당

### 5. **배포 단순화**
- Rust: 단일 .so 파일 (maturin build)
- Python: pip install codegraph-ir

---

## Alternatives Considered

### Alternative 1: Full Python Rewrite
- ❌ 성능 희생 (GIL 문제)
- ❌ 개발 속도 느림

### Alternative 2: Full Rust Rewrite
- ❌ Python 생태계 이점 상실 (FastAPI, MCP SDK 등)
- ❌ 러닝 커브 높음

### Alternative 3: Microservices (Rust + Python)
- ❌ 배포 복잡도 증가
- ❌ IPC 오버헤드

---

## Consequences

### Positive
- ✅ 아키텍처 명확성
- ✅ 개발 속도 향상
- ✅ 성능 최적화
- ✅ 테스트 및 유지보수 용이

### Negative
- ⚠️ PyO3 API 유지보수 필요
- ⚠️ Rust 컴파일 시간 증가 (vs Python)

### Neutral
- Language Plugin 인터페이스 확장 가능성 (향후 필요시)

---

## References

- [RFC-064: Rust Pipeline Orchestration](../rfcs/RFC-064-Rust-Pipeline-Orchestration.md)
- [RUST_INTEGRATED_ARCHITECTURE.md](../../packages/codegraph-rust/docs/RUST_INTEGRATED_ARCHITECTURE.md)
- [PyO3 Documentation](https://pyo3.rs/)

---

## Timeline

- **Week 1** (Current): Document architecture, update ADR
- **Week 2**: Deprecate LayeredIRBuilder, migrate IRBuildHandler
- **Week 3**: Remove Python IR building code, update tests
- **Week 4**: Documentation update, final review
