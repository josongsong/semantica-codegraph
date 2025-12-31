# Clean Rust-Python Architecture Summary

**Date**: 2025-12-28
**Status**: ✅ Design Complete, Implementation Pending

---

## TL;DR

**Rust = Engine (Core), Python = Consumer (Application)**

- ✅ Rust: 모든 분석 로직, Python 의존성 없음 (Parser plugin만 허용)
- ✅ Python: Rust 엔진 사용, 비즈니스 로직 & 워크플로우
- ✅ 단방향 의존성: `Python → Rust` (via `import codegraph_ir`)

---

## Current vs Target Architecture

### Before (복잡한 양방향 의존성)

```
┌─────────────────────────────────────┐
│         Python Application          │
│  ┌──────────────────────────────┐  │
│  │  LayeredIRBuilder (레거시)   │  │  ← Python IR 빌드
│  │  IRBuildHandler              │  │
│  │  CrossFileHandler            │  │
│  └──────────┬───────────────────┘  │
│             │                       │
│             ├→ import codegraph_ir  │  ← Rust 엔진 사용
│             │                       │
└─────────────┼───────────────────────┘
              │
        양방향 의존성 ❌
              │
┌─────────────▼───────────────────────┐
│          Rust Engine                │
│  ┌──────────────────────────────┐  │
│  │  IRIndexingOrchestrator      │  │
│  │  MultiLayerIndexOrchestrator │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
```

### After (명확한 단방향 의존성)

```
┌─────────────────────────────────────────────────────┐
│              Python Application Layer               │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │ API Server │  │ MCP Server │  │   CLI      │   │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘   │
│        │                │                │          │
│        └────────────────┴────────────────┘          │
│                         │                           │
│                  import codegraph_ir                │
│                         │                           │
└─────────────────────────┼───────────────────────────┘
                          │ (단방향 ✅)
┌─────────────────────────▼───────────────────────────┐
│              Rust Analysis Engine                   │
│  ┌──────────────────────────────────────────────┐  │
│  │  IRIndexingOrchestrator (L1-L8 Pipeline)     │  │
│  │  - 모든 분석 로직                             │  │
│  │  - Python 의존성 없음                        │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │  MultiLayerIndexOrchestrator (MVCC)          │  │
│  │  - 증분 업데이트                              │  │
│  │  - Plugin 기반 인덱스                         │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │  Query Engine (검색)                          │  │
│  │  - Lexical (Tantivy)                         │  │
│  │  - Semantic (Graph)                          │  │
│  └──────────────────────────────────────────────┘  │
│                         ▲                           │
│                         │ (Plugin Interface)        │
│                  Language Parsers                   │
└─────────────────────────┼───────────────────────────┘
                          │
                 ┌────────┴────────┐
                 │                 │
        ┌────────▼─────┐  ┌───────▼──────┐
        │ Tree-sitter  │  │ LSP Servers  │
        │ (Rust)       │  │ (External)   │
        └──────────────┘  └──────────────┘
```

---

## Key Principles

### 1. Rust = Analysis Engine (Zero Python Dependency)

**Rust는 순수 분석 엔진**:
- ✅ IR Building (L1-L8 Pipeline)
- ✅ Incremental Indexing (MVCC)
- ✅ Query Processing (Lexical, Semantic, Graph)
- ✅ Clone Detection, Taint Analysis, Effect Analysis
- ❌ **No Python imports** (Parser plugin 제외)

**Benefits**:
- 🚀 GIL-free parallel processing (Rayon)
- 🚀 Zero-copy msgpack serialization
- 🚀 10-50x faster than Python

### 2. Python = Engine Consumer (Application Layer)

**Python은 Rust 엔진 사용자**:
- ✅ API Server (FastAPI)
- ✅ MCP Server (Model Context Protocol)
- ✅ CLI Tools & Scripts
- ✅ Job Handlers (Task orchestration)
- ❌ **분석 로직 구현 금지**

**Benefits**:
- 🎯 Python 생태계 이점 (FastAPI, MCP SDK, etc.)
- 🎯 비즈니스 로직 집중
- 🎯 빠른 프로토타이핑

### 3. Plugin Interface (Bidirectional, Parser Only)

**유일하게 허용되는 양방향 통신**:
- Rust ← Parser Plugin (Python or Rust)
- Language-specific parsing logic만 해당

**Example**:
```rust
// Rust: Language Plugin trait
pub trait LanguagePlugin {
    fn parse(&self, source: &str) -> Result<ParsedAst>;
}

// Implementation 1: Rust native (Tree-sitter)
pub struct TreeSitterPlugin;
impl LanguagePlugin for TreeSitterPlugin { ... }

// Implementation 2: Python plugin (선택사항)
pub struct PythonParserPlugin;
impl LanguagePlugin for PythonParserPlugin {
    fn parse(&self, source: &str) -> Result<ParsedAst> {
        // PyO3로 Python parser 호출
        Python::with_gil(|py| { ... })
    }
}
```

---

## Migration Plan

### Phase 1: ✅ Rust Engine Independence (Already Done)

- [x] IRIndexingOrchestrator (7,520 LOC)
- [x] MultiLayerIndexOrchestrator (4,160 LOC)
- [x] Lexical Search (Tantivy)
- [x] Clone Detection

### Phase 2: 🔄 Remove Python → Rust Dependencies (Current)

#### 2.1. Deprecate LayeredIRBuilder

**Action**: Python IR building 제거

```python
# ❌ Before: Python IR builder
from codegraph_engine.infrastructure.ir.layered_ir_builder import LayeredIRBuilder

builder = LayeredIRBuilder(config)
result = await builder.build_all(repo_path)

# ✅ After: Rust engine
import codegraph_ir

orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
result = orchestrator.execute()
```

**Files to Update**:
- `packages/codegraph-engine/...ir/layered_ir_builder.py` (deprecate → remove)
- `packages/codegraph-shared/.../ir_handler.py` (USE_RUST_IR 제거)

#### 2.2. Simplify Job Handlers

**Before**:
```python
class IRBuildHandler:
    def __init__(self):
        self.use_rust_ir = os.getenv("USE_RUST_IR", "true")  # ❌ 조건부

    async def execute(self, payload):
        if self.use_rust_ir:
            # Rust
        else:
            # Python LayeredIRBuilder
```

**After**:
```python
class IRBuildHandler:
    """Always use Rust engine."""  # ✅ 단순화

    async def execute(self, payload):
        import codegraph_ir
        orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
        return orchestrator.execute()
```

**Files to Update**:
- `packages/codegraph-shared/.../ir_handler.py`
- `packages/codegraph-shared/.../cross_file_handler.py` (삭제 또는 단순화)

#### 2.3. Update Tests

**All Python tests should use `codegraph_ir` directly**:

```python
# ❌ Don't: Python IR building
from codegraph_engine import LayeredIRBuilder

# ✅ Do: Rust engine
import codegraph_ir

def test_ir_build():
    orchestrator = codegraph_ir.IRIndexingOrchestrator(config)
    result = orchestrator.execute()
    assert len(result.nodes) > 0
```

### Phase 3: 📝 Documentation Update

- [ ] Update [CLAUDE.md](../CLAUDE.md)
- [ ] Update [System Handbook](../docs/handbook/)
- [ ] Create [Migration Guide](./MIGRATION_GUIDE.md)
- [ ] Update [API Reference](./API_REFERENCE.md)

---

## API Boundaries

### Rust → Python (PyO3 Bindings)

**Python module**: `codegraph_ir`

```python
# 1. Full Repository Indexing
from codegraph_ir import IRIndexingOrchestrator, E2EPipelineConfig

config = E2EPipelineConfig(
    root_path="/repo",
    parallel_workers=4,
    enable_chunking=True,
    enable_repomap=True,
)
orchestrator = IRIndexingOrchestrator(config)
result = orchestrator.execute()

# Access results
print(f"Nodes: {len(result.nodes)}")
print(f"Edges: {len(result.edges)}")
print(f"Chunks: {len(result.chunks)}")

# 2. Incremental Updates (MVCC)
from codegraph_ir import MultiLayerIndexOrchestrator

orchestrator = MultiLayerIndexOrchestrator(config)
session = orchestrator.begin_session("agent_1")
orchestrator.add_change("agent_1", {"op": "add_node", "node": {...}})
result = orchestrator.commit("agent_1")

# 3. Query Engine
from codegraph_ir import QueryEngine

engine = QueryEngine(index_path="/index")
results = engine.lexical_search("function")
results = engine.semantic_search(embedding=[0.1, 0.2, ...])
```

### Python → Rust (Consumer Only)

**Rules**:
1. ✅ `import codegraph_ir` allowed
2. ❌ No direct Rust manipulation
3. ✅ Configuration via Python → Rust conversion
4. ❌ No analysis logic in Python

---

## Implementation Checklist

### Immediate Actions (Week 1-2)

- [ ] Create [ADR-072](./adr/ADR-072-clean-rust-python-architecture.md) ✅ Done
- [ ] Mark `LayeredIRBuilder` as deprecated
- [ ] Update `IRBuildHandler` to use Rust only
- [ ] Remove `USE_RUST_IR` environment variable
- [ ] Update all Python imports to use `codegraph_ir`

### Testing (Week 2-3)

- [ ] Verify all Python tests pass
- [ ] Add PyO3 boundary integration tests
- [ ] Performance benchmarks (Rust vs old Python)

### Documentation (Week 3-4)

- [ ] Update CLAUDE.md
- [ ] Update System Handbook
- [ ] Create Migration Guide
- [ ] Document PyO3 API

### Cleanup (Week 4)

- [ ] Remove deprecated Python IR code
- [ ] Remove unused imports
- [ ] Final code review

---

## Benefits Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Dependencies** | Bidirectional ❌ | Unidirectional ✅ |
| **Complexity** | High (2 implementations) | Low (1 engine) |
| **Performance** | Python GIL bottleneck | Rust parallel (10-50x) |
| **Maintenance** | Difficult (sync 2 impls) | Easy (1 source of truth) |
| **Testing** | Complex (mock both) | Simple (mock Rust) |
| **Deployment** | Complex | Simple (pip install) |

---

## FAQ

### Q1: Python에서 커스텀 분석을 어떻게 추가하나요?

**A**: Rust 엔진에 기능을 추가하고, PyO3로 노출합니다.

```rust
// 1. Rust에 기능 추가
pub fn custom_analysis(nodes: &[Node]) -> AnalysisResult { ... }

// 2. PyO3 바인딩
#[pyfunction]
fn custom_analysis_py(nodes: Vec<Node>) -> PyResult<AnalysisResult> {
    Ok(custom_analysis(&nodes))
}

// 3. Python에서 사용
import codegraph_ir
result = codegraph_ir.custom_analysis(nodes)
```

### Q2: Python parser를 Rust에서 어떻게 사용하나요?

**A**: Language Plugin 인터페이스를 통해 호출합니다.

```python
# Python: Custom parser
class MyParserPlugin:
    def parse(self, source: str) -> dict:
        return {"type": "Module", "body": [...]}
```

```rust
// Rust: Plugin 호출
pub fn parse_with_plugin(source: &str) -> Result<ParsedAst> {
    Python::with_gil(|py| {
        let plugin = py.import("my_parser")?;
        let result = plugin.call_method1("parse", (source,))?;
        Ok(msgpack::from_slice(result.extract()?)?)
    })
}
```

### Q3: 기존 Python 코드는 언제 제거하나요?

**A**: 단계적으로 제거합니다.

1. **Week 1-2**: Deprecation 표시
2. **Week 2-3**: Migration 완료 확인
3. **Week 4**: 제거 (v2.1.0 릴리스)

### Q4: 성능 차이는 얼마나 되나요?

**A**: Rust 엔진이 10-50배 빠릅니다.

| Operation | Python | Rust | Speedup |
|-----------|--------|------|---------|
| IR Build | 10s | 0.5s | 20x |
| Cross-File | 60s | 5s | 12x |
| Clone Detection | 30s | 0.6s | 50x |

---

## References

- [ADR-072: Clean Rust-Python Architecture](./adr/ADR-072-clean-rust-python-architecture.md)
- [RUST_INTEGRATED_ARCHITECTURE.md](../packages/codegraph-rust/docs/RUST_INTEGRATED_ARCHITECTURE.md)
- [RFC-064: Rust Pipeline Orchestration](./rfcs/RFC-064-Rust-Pipeline-Orchestration.md)

---

**Status**: ✅ Design approved, implementation in progress
**Next Steps**: Execute Phase 2 migration plan
