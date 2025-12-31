# RFC-040: Multi-Module Architecture

**Status**: Draft  
**Created**:   
**Priority**: P1 (Strategic)  
**Type**: Architecture Decision

---

## 1. 목적

**codegraph를 재사용 가능한 독립 모듈로 분리**

**목표**:
- 각 컴포넌트 독립 배포
- 선택적 설치 (필요한 것만)
- 외부 프로젝트 재사용
- 명확한 의존 관계

---

## 2. 문제 정의

### 현재 (Monolith)

```
codegraph/ (20MB)
└── 모든 것이 한 패키지
    - IR builder
    - Query engine
    - Taint analysis
    - CLI
    
문제:
❌ 전체 설치 강제 (IR만 필요해도 20MB)
❌ 재사용 어려움 (QueryEngine만 쓰고 싶어도 전체 필요)
❌ 릴리즈 결합 (작은 수정도 전체 버전업)
❌ 기여 어려움 (전체 이해 필요)
```

---

## 3. 해결: Multi-Module Architecture

### 3-1. 모듈 구조

```
codegraph/ (Monorepo)
│
├── packages/
│   ├── core/              # codegraph-core
│   ├── query/             # codegraph-query
│   ├── taint/             # codegraph-taint
│   └── cli/               # codegraph (umbrella)
│
├── external/
│   └── srcr/              # Git submodule or external
│
└── pyproject.toml         # Workspace root
```

---

## 4. 모듈 상세 정의

### Module 1: **codegraph-core** (Foundation)

**책임**: Source code → IRDocument

```
codegraph-core/
├── pyproject.toml
│   name: codegraph-core
│   version: 1.0.0
│   dependencies: [tree-sitter, pydantic]
│
├── src/codegraph_core/
│   ├── __init__.py
│   │   # Exports: IRDocument, IRBuilder, Expression
│   │
│   ├── models/
│   │   ├── ir_document.py      # Core data structure
│   │   ├── node.py              # Node, Edge
│   │   ├── expression.py        # Expression (DFG)
│   │   └── symbol.py
│   │
│   ├── builders/
│   │   ├── ir_builder.py        # Main builder
│   │   ├── python/              # Python extractor
│   │   ├── typescript/          # TypeScript extractor
│   │   ├── java/
│   │   ├── kotlin/
│   │   └── go/
│   │
│   ├── semantic/
│   │   ├── dfg/                 # Data Flow Graph
│   │   ├── cfg/                 # Control Flow Graph
│   │   └── call_graph/
│   │
│   └── protocols/
│       ├── program_ir.py        # Abstract IR interface
│       └── builder_protocol.py
│
└── tests/ (1000+ tests)

크기: ~3MB
라인: ~15K
의존: tree-sitter, pydantic
재사용: ✅ 다른 static analysis 도구
```

**설치**:
```bash
pip install codegraph-core

# 사용
from codegraph_core import IRBuilder, IRDocument

builder = IRBuilder()
ir = builder.build("myfile.py")
# 다른 도구에서 자유롭게 사용!
```

---

### Module 2: **codegraph-query** (Q.DSL)

**책임**: Graph query language & engine

```
codegraph-query/
├── pyproject.toml
│   name: codegraph-query
│   version: 1.0.0
│   dependencies: [codegraph-core]
│
├── src/codegraph_query/
│   ├── __init__.py
│   │   # Exports: QueryEngine, Q, E, PathQuery
│   │
│   ├── dsl/
│   │   ├── query_dsl.py         # Q.Call, Q.Var, Q.Func
│   │   ├── edge_dsl.py          # E.DFG, E.CFG, E.CALL
│   │   ├── path_query.py        # >>, |, &
│   │   └── verification.py      # PathSet, VerificationResult
│   │
│   ├── engine/
│   │   ├── query_engine.py      # Main engine (ADR-002)
│   │   ├── traversal.py         # BFS/DFS
│   │   ├── path_finder.py       # find_paths()
│   │   └── matcher.py
│   │
│   ├── indexes/
│   │   ├── unified_index.py     # Multi-index
│   │   ├── node_index.py
│   │   ├── edge_index.py
│   │   └── semantic_index.py
│   │
│   └── protocols/
│       └── graph_protocol.py    # Abstract graph interface
│
└── tests/ (500+ tests)

크기: ~500KB
라인: ~7K
의존: codegraph-core (IRDocument)
재사용: ✅✅✅ 어떤 그래프든! (Neo4j, NetworkX, RustWorkX)
```

**설치**:
```bash
pip install codegraph-query

# 사용 (Taint 아니어도!)
from codegraph_query import QueryEngine, Q, E

# Neo4j에서도 사용 가능
engine = QueryEngine(neo4j_graph)
results = engine.execute(Q.Node("User") >> E.FOLLOWS >> Q.Node("Post"))
```

**가치**: **범용 Graph Query Language!**

---

### Module 3: **codegraph-taint**

**책임**: Taint analysis orchestration

```
codegraph-taint/
├── pyproject.toml
│   name: codegraph-taint
│   version: 1.0.0
│   dependencies: [codegraph-core, codegraph-query, srcr]
│
├── src/codegraph_taint/
│   ├── __init__.py
│   │   # Exports: TaintAnalyzer
│   │
│   ├── service/
│   │   └── taint_analysis_service.py
│   │
│   ├── engine/
│   │   └── taint_engine.py
│   │
│   ├── guard/
│   │   └── guard_detector.py    # RFC-030
│   │
│   ├── adapters/
│   │   ├── ir_adapter.py        # IRDocument → srcr
│   │   └── query_adapter.py     # QueryEngine → srcr
│   │
│   └── formatters/
│       ├── json_formatter.py
│       └── sarif_formatter.py
│
└── tests/ (300+ tests)

크기: ~300KB
라인: ~3K
의존: core, query, srcr
재사용: ⚠️ 낮음 (Taint 전용)
```

---

### Module 4: **srcr** (별도 레포)

```
srcr/
├── src/srcr/
│   ├── compiler/
│   ├── runtime/
│   └── indexes/
│
└── rules/
    ├── atoms/
    └── policies/

크기: ~500KB
의존: 0
재사용: ✅✅ Rule engine (범용!)
```

---

### Module 5: **codegraph** (Umbrella)

```
codegraph/
├── pyproject.toml
│   name: codegraph
│   dependencies: [core, query, taint, srcr]
│
├── src/codegraph/
│   ├── __init__.py         # Re-export
│   ├── analyzer.py         # Main API
│   └── cli.py              # CLI
│
└── tests/integration/      # E2E

크기: ~100KB
라인: ~500
의존: 전부
```

---

## 🎯 SOTA 여부?

### ✅ YES! 이유:

**1. 명확한 레이어**
```
Core (IR) → Query (Graph) → Taint (Analysis) → CLI
```

**2. 각 레벨 재사용 가능**
```
Core: 다른 static analysis
Query: 다른 graph 시스템  
srcr: 다른 rule-based 도구
```

**3. Protocol 기반**
```
ProgramIR, GraphProtocol
→ 구현체 교체 가능
```

**4. 언어 확장 쉬움**
```
core/builders/rust/ 추가만 하면 끝
→ query, taint는 수정 없음!
```

---

## 📊 업계 비교

| Feature | CodeQL | Semgrep | **Ours** |
|---------|--------|---------|----------|
| IR 독립성 | ❌ | ❌ | ✅ |
| Query 독립성 | ⚠️ (QL 전용) | ❌ | ✅ |
| Rule 독립성 | ⚠️ | ⚠️ | ✅ |
| 언어 추가 | 복잡 | 복잡 | **쉬움** |
| 재사용성 | 낮음 | 낮음 | **높음** |

**결론**: **SOTA! CodeQL/Semgrep보다 나음** 🏆
