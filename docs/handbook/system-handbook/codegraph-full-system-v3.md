# Codegraph 전체 시스템 개요 v3

**
**Scope:** 전체 시스템 "현재 상태" 요약 (living doc)
**Audience:** 개발자/리뷰어
**Source of Truth:** `src/contexts/` + `_docs/modules/`

> 참고(스냅샷 메모): 2024-12-13 합집합 기반에서, 2025-12 중 인덱싱/IR/타입추론/보안 분석 관련 업데이트를 반영
> **🚀 Latest Update (2025-12-26)**: Modular IR Pipeline + Rust L1 Occurrence Generation (7.6x faster)

---

## Table of Contents

- Part 1. Architecture & Statistics
- Part 2. Static Analysis
- Part 3. IR & Graph
- Part 4. Search & Retrieval
- Part 5. Agent & Reasoning
- Part 6. Memory Systems
- Part 7. Infrastructure
- Part 8. Indexing Pipeline
- Part 9. 추가 컴포넌트
- Part 10. 개발자 가이드
- Part 11. 참조 알고리즘/논문
- Part 12. TODO / 개선 작업

---

# Part 1. Architecture & Statistics

## 시스템 통계

| 항목 | 수치 |
|------|------|
| 총 Python 파일 | 1,233개 |
| 총 테스트 파일 | 518개 |
| 총 클래스 | 3,490+ |
| 총 async 함수 | 4,670+ |
| Protocol 정의 | 331개 |
| Pydantic/Dataclass 모델 | 1,002개 |
| Enum 정의 | 417개 |
| Logger 사용 | 4,319개 |
| 추정 LOC | 250,000+ |
| TODO 항목 | ~50개 (실제 미구현) |
| NotImplementedError | 126개 (연동 이슈) |

## 아키텍처 원칙

- Hexagonal Architecture (Port/Adapter)
- Domain-Driven Design (Bounded Context)
- SOLID Principles
- CQRS / Event Sourcing
- Facade Pattern

## Bounded Contexts (11개)

```
src/contexts/                        # 10개 도메인 컨텍스트
├── code_foundation/      (380 files) # IR, 파싱, 분석
├── analysis_indexing/    (67 files)  # 9-Stage 파이프라인
├── multi_index/          (67 files)  # 6종 인덱스 인프라
├── retrieval_search/     (75 files)  # V3 리트리벌
├── reasoning_engine/                 # PDG, Slicer, Impact, VFG
├── session_memory/       (50 files)  # Episodic/Semantic Memory
├── codegen_loop/         (53 files)  # ShadowFS, CodeGen/TestGen
├── repo_structure/       (25 files)  # RepoMap, PageRank
├── security_analysis/    (19 files)  # 보안 쿼리
└── agent_code_editing/               # FIM/Refactoring

src/agent/                            # LLM Agent (별도 최상위)
├── domain/reasoning/     # LATS, ToT
├── orchestrator/         # Deep Reasoning
├── tools/                # MCP Tools
└── shared/               # Constitutional AI, Sampling
```

## Facade Pattern

| Facade | 기능 |
|--------|------|
| `UnifiedGraphIndex` | 3개 인덱스 통합 |
| `RetrieverV3Orchestrator` | 검색 통합 |
| `DeepReasoningOrchestrator` | 추론 통합 |

---

## Related Docs (현재 시스템 요약 기준)

- 시스템/구성:
  - `codegraph-full-system-v3.md` (이 문서)
  - `15-multi-repo-structure.md` (멀티레포/연동 구조)
- 현재 구현 커버리지:
  - `static-analysis-techniques.md` (기법별 구현 상태 + 테스트 레퍼런스 인덱스)
  - `static-analysis-coverage.md` (산업/학계 대비 커버리지 매트릭스)
  - `type-inference-system.md` (타입추론 시스템 현황)
- 설계 근거/리뷰/플랜(요약이 아님 → 별도 디렉토리):
  - `_docs/system-handbook/design/` (perf plan, MCP protocol 등)
- 가이드/사용법(요약이 아님 → 별도 디렉토리):
  - `_docs/system-handbook/guides/`
- 모듈 상세(요약이 아님 → 별도 디렉토리):
  - `_docs/modules/`

---

## Core Pipeline (Code Foundation → HCG/Chunk → Indexing)

> “레이어별 처리” 관점의 현재 파이프라인 요약입니다. (상세 스펙: `_docs/modules/indexing/pipeline/IR_HCG.md`)

| 단계 | 산출물(대표) | 담당 컨텍스트 | 핵심 코드 |
|------|--------------|---------------|----------|
| Parsing | Tree-sitter AST | `code_foundation` | `src/contexts/code_foundation/infrastructure/parsing/` |
| IR Generation | **Structural IR**: `IRDocument` (Node/Edge/Span) | `code_foundation` | `src/contexts/code_foundation/infrastructure/generators/` |
| Semantic IR | CFG/DFG/Type/Signature 등 | `code_foundation` | `src/contexts/code_foundation/infrastructure/semantic_ir/`, `.../dfg/` |
| Graph Layer | `GraphDocument` (Heterogeneous Graph) | `code_foundation` | `src/contexts/code_foundation/infrastructure/graph/` |
| HCG Adapter | HCG(Graph↔Chunk/RepoMap 연결) | `analysis_indexing` + `code_foundation` | (상세: `IR_HCG.md`) |
| Chunking | Chunk + ChunkIndex(검색/요약 단위) | `analysis_indexing` | `src/contexts/analysis_indexing/infrastructure/stages/chunk_stage.py` |
| RepoMap | RepoMap(요약/네비게이션) | `analysis_indexing` + `repo_structure` | `src/contexts/analysis_indexing/infrastructure/stages/repomap_stage.py` |
| Multi-Index | vector/lexical/symbol/graph store | `multi_index` | `src/contexts/multi_index/` |

**현재 레이어 매핑(운영 관점)**:
- **L0**: Change detection (git/mtime/hash)
- **L1**: Parsing (AST)
- **L2**: Structural IR + Chunk(기본 단위)
- **L3**: Semantic IR (CFG/DFG/Type)
- **L4+**: 고급 분석(taint/heap/type inference 등) + 인덱스 갱신

**관련 문서(상세)**:
- IR/HCG 전체: `_docs/modules/indexing/pipeline/IR_HCG.md`
- Indexing 파이프라인: `_docs/modules/indexing/pipeline/pipelines-quick-ref.md`

**Chunk 인덱싱(키/조인) 요약**
- **Primary Key**: `chunk_id`  
  - 포맷: `chunk:{repo_id}:{kind}:{fqn}` (예: 함수/클래스/파일 단위)
- **Vector/Domain/Symbol 인덱스**: `IndexDocument.id == chunk_id`로 저장/조회  
  - 공통 필드: `repo_id`, `snapshot_id`, `file_path`, `symbol_id`, `content`, `tags`
- **Lexical 인덱스**: raw 소스 파일을 직접 인덱싱하고 hit는 보통 `(file_path, line)` 형태로 반환  
  - hit → `ChunkStore`의 `file_path + line → Chunk` 매핑으로 `chunk_id`로 조인 (RAG/리트리벌 통합 키)
- **Graph/HCG 연결**: `ChunkStore`가 `(repo_id, snapshot_id, chunk_id) → graph_node_ids / ir_node_ids` 매핑을 별도 저장  
  - chunk ↔ graph/IR 점프, chunk 기반 서브그래프 추출/증분 갱신에 사용
- **검색 결과 통합(SearchHit)**: 모든 인덱스 결과는 `SearchHit.chunk_id`로 표준화되어, 최종 fusion/리트리벌의 조인 키는 `chunk_id`

---

# Part 2. Static Analysis

## 1. Taint Analysis Stack (10 Layer)

| # | 레이어 | 컴포넌트 | 알고리즘 | 파일 |
|---|-------|---------|---------|------|
| 1 | Inter-procedural | `InterproceduralTaintAnalyzer` | 10-hop, Context-sensitive | `analyzers/interprocedural_taint.py` |
| 2 | Path-sensitive | `PathSensitiveTaintAnalyzer` | Meet-Over-Paths (MOP) | `analyzers/path_sensitive_taint.py` |
| 3 | Field-sensitive | `FieldSensitiveTaintAnalyzer` | Field/Element granularity | `analyzers/field_sensitive_taint.py` |
| 4 | Alias Analysis | `AliasAnalyzer` | May/Must-alias | `analyzers/alias_analyzer.py` |
| 5 | Type Narrowing | `FullTypeNarrowingAnalyzer` | isinstance, truthiness | `analyzers/type_narrowing_full.py` |
| 6 | Context Manager | `CallString` | K-limited Call String | `analyzers/context_manager.py` |
| 7 | Function Summary | `FunctionTaintSummary` | Memoization Cache | `analyzers/function_summary.py` |
| 8 | Graph-based | `GraphBasedTaintAnalyzer` | CFG Worklist, **F1=100%** | `analyzers/graph_taint_analyzer.py` |
| 9 | Taint Slicer | `TaintSlicer` | PDG + Taint | `analyzers/taint_slicer.py` |
| 10 | Deep Security | `DeepSecurityAnalyzer` | Pattern + Taint + SMT | `analyzers/deep_security_analyzer.py` |

### 파일 위치

```
src/contexts/code_foundation/infrastructure/analyzers/
├── taint_engine_full.py
├── interprocedural_taint.py
├── path_sensitive_taint.py
├── graph_taint_analyzer.py
└── taint_rules/
```

## 2. Memory Safety (Infer-grade)

| 컴포넌트 | 알고리즘 | 파일 |
|---------|---------|------|
| `SeparationLogicAnalyzer` | Forward Symbolic Execution | `heap/sep_logic.py` |
| `SymbolicHeap` | x ↦ {fields}, Pure constraints | `heap/symbolic_heap.py` |
| `PointsToAnalysis` | Andersen-style, Field-sensitive | `heap/points_to.py` |
| `LightweightBiabduction` | Backward Precondition Inference | `heap/lightweight_biabduction.py` |
| `NullDereferenceChecker` | Forward + Backward | `heap/null_checker.py` |
| `RealtimeNullAnalyzer` | Incremental, < | `heap/realtime_null_analyzer.py` |
| `AuditNullAnalyzer` | Full Sound, 95% detection | `heap/audit_null_analyzer.py` |
| `UseAfterFreeChecker` | Free tracking, 90%+ precision | `heap/uaf_checker.py` |
| `OwnershipChecker` | Double Free, Stack Escape | `heap/ownership_checker.py` |

### 파일 위치

```
src/contexts/code_foundation/infrastructure/heap/
├── sep_logic.py
├── points_to.py
├── lightweight_biabduction.py
├── smt_path_verifier.py
├── type_state.py
├── field_lifecycle.py
├── realtime_null_analyzer.py
├── cha_call_graph.py
├── java_annotation_registry.py
└── c_cpp_rust_adapter.py
```

### 분석 모드

| 모드 | 설명 | 성능 |
|-----|------|------|
| REALTIME | 증분 분석, 국소 고정점 | < |
| AUDIT | 전역 고정점, Sound 보장 | ~-3s |

## 3. SMT Integration

```
파일: heap/smt/z3_solver.py
지원 Theory: Int, String, Array, Boolean
기능: Path Feasibility, Timeout, Division-by-Zero Guards
```

## 4. Semantic Sanitizer Detector

```
파일: code_foundation/domain/security/semantic_sanitizer_detector.py

특징: NO HARDCODED PATTERNS - IR 기반 자동 탐지

Confidence:
- VERY_HIGH (0.95): Strong evidence
- HIGH (0.85): Multiple indicators
- MEDIUM (0.70): Single strong indicator
- LOW (0.50): Weak/heuristic match
```

## 5. Taint Policy DSL

```
src/contexts/code_foundation/infrastructure/taint/
├── compilation/policy_compiler.py   # WHEN/FLOWS/BLOCK
├── matching/type_aware_matcher.py
└── repositories/yaml_policy_repository.py
```

## 6. Security Rules (YAML)

### Atoms (python.atoms.yaml)

```yaml
sources:
  - base_type: flask.Request
    read: [args, form, json, data, cookies]
  - base_type: django.http.HttpRequest
    read: [GET, POST, body]

sinks:
  - call: sqlite3.Cursor.execute
  - call: subprocess.run
  - call: eval

sanitizers:
  - call: html.escape
```

### Policies (python.policies.yaml)

```yaml
policies:
  - id: sql_injection
    severity: critical
    cwe: CWE-89
    grammar:
      WHEN: source is HTTP_INPUT
      FLOWS: sink is SQL_EXECUTE
      BLOCK UNLESS: sanitizer is SQL_ESCAPE
```

---

# Part 3. IR & Graph

## 1. Modular IR Pipeline System (9 Pluggable Stages)

**🚀 SOTA Performance**: Rust L1 Occurrence Generation (7.6x faster than Python L2)

### Pipeline Architecture

The IR generation now uses a **modular, pluggable pipeline architecture** with 9 independent stages:

| Stage | 이름 | 설명 | Location |
|-------|-----|------|----------|
| 1 | StructuralStage | AST-based IR (symbols, calls, references) | `pipeline/stages/structural.py` |
| 2 | LspTypeStage | Type inference via LSP | `pipeline/stages/lsp_type.py` |
| 3 | CrossFileStage | Import resolution & cross-file analysis | `pipeline/stages/cross_file.py` |
| 4 | PackageStage | Package/module detection | `pipeline/stages/package.py` |
| 5 | DiagnosticsStage | LSP diagnostics integration | `pipeline/stages/diagnostics.py` |
| 6 | ProvenanceStage | Code provenance tracking | `pipeline/stages/provenance.py` |
| 7 | RetrievalStage | Retrieval-optimized metadata | `pipeline/stages/retrieval.py` |
| 8 | TemplateIRStage | Template expansion | `pipeline/stages/template_ir.py` |
| 9 | CacheStage | IR result caching | `pipeline/stages/cache.py` |

### Key Performance Improvements

- **Rust L1 Occurrence Generation**: Moved from Python L2 to Rust L1, achieving **7.6x speedup**
- **Batched Parallel Processing**: Using Rayon for parallel file processing
- **Zero-Copy Optimizations**: Following RFC-062-SOTA guidelines
- **Lazy Imports**: Resolved circular dependencies in code_foundation module

### 파일 위치

```
packages/codegraph-engine/codegraph_engine/code_foundation/infrastructure/ir/
├── pipeline/                    # 🆕 Modular IR Pipeline
│   ├── README.md               # Pipeline documentation
│   ├── IMPLEMENTATION.md       # Implementation guide
│   ├── MIGRATION.md            # Migration from legacy IR
│   ├── builder.py              # Pipeline builder (DSL)
│   ├── orchestrator.py         # Pipeline orchestrator
│   ├── pipeline.py             # Core pipeline logic
│   ├── protocol.py             # Stage protocol definitions
│   ├── stages/                 # 9 pluggable stages
│   │   ├── structural.py       # L1: AST-based IR
│   │   ├── lsp_type.py         # L2: Type inference
│   │   ├── cross_file.py       # L3: Import resolution
│   │   ├── package.py          # L4: Package detection
│   │   ├── diagnostics.py      # L5: Diagnostics
│   │   ├── provenance.py       # L6: Code provenance
│   │   ├── retrieval.py        # L7: Retrieval metadata
│   │   ├── template_ir.py      # L8: Template expansion
│   │   └── cache.py            # L9: Caching
│   ├── examples/               # Usage examples
│   │   └── basic_usage.py
│   └── tests/
│       └── test_pipeline.py
├── layered_ir_builder.py       # Legacy IR builder (deprecated)
└── models/
    ├── document.py
    ├── occurrence.py           # 🚀 Now generated in Rust L1
    └── diagnostic.py

packages/codegraph-rust/codegraph-ir/
├── src/
│   ├── features/
│   │   ├── cross_file/         # 🆕 Cross-file resolver (RFC-062)
│   │   │   ├── import_resolver.rs
│   │   │   ├── symbol_index.rs
│   │   │   ├── dep_graph.rs
│   │   │   └── types.rs
│   │   └── parsing/
│   │       └── extractors/
│   │           └── import.rs   # 🆕 Import statement extraction
│   ├── shared/
│   │   └── models/
│   │       └── occurrence.rs   # 🆕 Occurrence model in Rust
│   └── pipeline/
│       └── processor.rs        # 🚀 Batched occurrence generation
```

### RFC References

- **RFC-061**: Phase 2 Indexing Optimization
- **RFC-062**: CrossFileResolver Rust Optimization
- **RFC-062-SOTA**: Zero-Copy Solutions

### 외부 LSP 연동

```
src/contexts/code_foundation/infrastructure/ir/external_analyzers/
├── pyright_daemon.py        # Python
├── typescript_lsp.py        # TypeScript
├── rust_analyzer.py         # Rust
├── gopls.py                 # Go
├── kotlin_lsp.py            # Kotlin
└── jdtls_client.py          # Java
```

### 언어별 Generator

```
src/contexts/code_foundation/infrastructure/generators/
├── python_generator.py
├── typescript_generator.py
├── java_generator.py
└── python/analyzers/
    ├── class_analyzer.py
    ├── function_analyzer.py
    ├── import_analyzer.py
    ├── call_analyzer.py
    ├── dataflow_analyzer.py
    └── exception_analyzer.py
```

## 2. Semantic IR

| 컴포넌트 | 기능 |
|----------|------|
| Type IR | 타입 정보 |
| Signature IR | 시그니처 |
| BFG | Basic Flow Graph |
| CFG | Control Flow Graph |
| DFG | Data Flow Graph |
| Expression IR | 표현식 |

### 디렉토리 구조

```
src/contexts/code_foundation/infrastructure/semantic_ir/
├── builder.py
├── parallel_builder.py
├── incremental_updater.py
├── typing/
│   ├── builder.py
│   ├── models.py
│   └── resolver.py
├── signature/
│   ├── builder.py
│   └── models.py
├── bfg/
│   ├── builder.py
│   ├── generator_lowering.py
│   └── models.py
├── cfg/
│   ├── builder.py
│   └── models.py
└── expression/
    ├── builder.py
    └── models.py
```

## 3. SSA (Static Single Assignment)

```
src/contexts/code_foundation/infrastructure/dfg/ssa/
├── dominator.py             # Cooper-Harvey-Kennedy (2001)
├── frontier.py              # Cytron et al. (1991)
├── ssa_builder.py
├── cfg_to_ssa.py
└── models.py
```

4단계: Dominator Tree → Dominator Frontier → Phi-node → Renaming
성능: O(n × e)

## 4. Program Dependence Graph (PDG)

```
파일: reasoning_engine/infrastructure/pdg/pdg_builder.py
PDG = CFG + DFG = Control Dependency + Data Dependency
```

## 5. Program Slicing

```
파일: reasoning_engine/infrastructure/slicer/slicer.py
알고리즘: Weiser's Algorithm (1981)
최적화: 5-20x memoization
```

## 6. Value Flow Graph (VFG)

```
파일: reasoning_engine/infrastructure/cross_lang/value_flow_graph.py
End-to-end: Frontend → Backend → Database

Edge 타입:
- Intra: CALL, RETURN, ASSIGN, PARAMETER
- Cross: HTTP_REQUEST, GRPC_CALL
- Persist: DB_WRITE, DB_READ, CACHE_WRITE
- MQ: QUEUE_SEND, QUEUE_RECEIVE
```

## 7. Impact Analysis

```
파일: reasoning_engine/infrastructure/impact/impact_analyzer.py
성능: O(V+E), Lazy Path, Parallel
```

## 8. Semantic Diff (4 Components)

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| SemanticDiffer | Behavior vs Refactoring 구분 | `semantic_diff/semantic_differ.py` |
| EffectAnalyzer | Side Effect 분석 | `semantic_diff/effect_analyzer.py` |
| EffectDiffer | Effect 차이 비교 | `semantic_diff/effect_differ.py` |
| EffectSystem | Effect 타입 시스템 | `semantic_diff/effect_system.py` |

## 9. Speculative Analysis

```
src/contexts/reasoning_engine/infrastructure/speculative/
├── graph_simulator.py       # Patch Simulation
├── delta_graph.py           # CoW DeltaGraph
└── risk_analyzer.py
```

## 10. Reasoning Executors (4 Types)

| Executor | 기능 | 파일 |
|---------|------|------|
| SliceExecutor | Program Slicing 실행 | `executors/slice_executor.py` |
| ImpactExecutor | Impact Analysis 실행 | `executors/impact_executor.py` |
| SpeculativeExecutor | 투기적 분석 실행 | `executors/speculative_executor.py` |
| EffectExecutor | Effect 분석 실행 | `executors/effect_executor.py` |

---

# Part 4. Search & Retrieval

## 1. Multi-Index System (6개)

| 인덱스 | 기술 | 파일 |
|-------|------|------|
| Lexical (Base) | Zoekt | `lexical/adapter_zoekt.py` |
| Lexical (Delta) | Tantivy | `lexical/delta/delta_index.py` |
| Merging | Base+Delta fusion | `lexical/merge/merging_index.py` |
| Vector | Qdrant (Embedded) | `vector/adapter_qdrant.py` + `infra/vector/__init__.py` |
| Symbol | Memgraph/PostgreSQL | `symbol_graph/postgres_adapter.py` |
| Correlation | PostgreSQL | `correlation/adapter_postgres.py` |

### 파일 위치

```
src/contexts/multi_index/infrastructure/
├── lexical/
│   ├── adapter_zoekt.py
│   ├── delta/
│   ├── merge/
│   └── compaction/
├── vector/
│   ├── adapter_qdrant.py          # QdrantVectorIndex
│   ├── embedding_queue.py
│   └── worker_pool.py
│
└── (공통)
    src/infra/vector/
    ├── __init__.py                 # create_qdrant_client (3 modes)
    └── qdrant.py                   # QdrantAdapter (low-level)
├── symbol/
│   ├── adapter_memgraph.py
│   └── call_graph_query.py
├── fuzzy/
│   └── adapter_pgtrgm.py
└── domain_meta/
    └── adapter_meta.py
```

### Laptop Mode vs Server Mode

| 컴포넌트 | Laptop | Server |
|----------|--------|--------|
| Graph | InMemory | Memgraph |
| Cache | L1 only | 3-Tier |
| Vector | Local | Qdrant Cluster |

## 2. Compaction

```
파일: lexical/compaction/manager.py
Two-Phase: Freeze → Rebuild → Promote
트리거: 200 files or 24 hours
```

## 3. Retrieval Orchestration

```
파일: retrieval_search/infrastructure/v3/orchestrator.py
특징: Async parallel, Sub-, Strategy Router
```

## 4. Query Enhancement (8개)

| 컴포넌트 | 기술 | 파일 |
|---------|------|------|
| HyDE | Hypothetical Document Embeddings | `query/hyde.py` |
| Self-RAG | Self-Reflective RAG | `adaptive/self_rag.py` |
| Multi-Query | Query decomposition | `query/multi_query.py` |
| Multi-Hop | Sequential retrieval | `query/multi_hop.py` |
| Query Decomposition | 쿼리 분해 | `query/` |
| Contextual Expansion | 컨텍스트 확장 | `query/` |
| IntentClassifier | 의도 분류 | `planner/intent.py` |
| StrategyRouter | 전략 라우팅 | `planner/router.py` |

### 파일 위치

```
src/contexts/retrieval_search/infrastructure/adaptive/
├── self_rag.py
├── weight_learner.py
├── topk_selector.py
└── feedback_processor.py
```

## 5. Reranking (11개)

| 컴포넌트 | 기술 | 파일 |
|---------|------|------|
| CrossEncoderReranker | BERT-based | `hybrid/cross_encoder_reranker.py` |
| CachedCrossEncoderReranker | Cached BERT | `hybrid/cross_encoder_reranker.py` |
| LLMReranker | GPT-based | `hybrid/llm_reranker.py` |
| CachedLLMReranker | Cached LLM | `hybrid/llm_reranker_cache.py` |
| BGEReranker | BGE M3 | `hybrid/bge_reranker.py` |
| LearnedReranker | ML-based | `hybrid/learned_reranker.py` |
| HybridReranker | 앙상블 | `hybrid/learned_reranker.py` |
| HybridFinalReranker | 최종 앙상블 | `hybrid/cross_encoder_reranker.py` |
| CallGraphReranker | Call graph proximity | `code_reranking/callgraph_reranker.py` |
| StructuralReranker | AST structural | `code_reranking/structural_reranker.py` |
| Compressor | LLMLingua | `context_builder/compressor.py` |

## 6. Adaptive Embeddings

```
파일: adaptive_embeddings/lora_trainer.py, adaptive_model.py
기능: Repo-specific LoRA adaptation
```

## 7. Filtering & Boosting

| 컴포넌트 | 기술 | 파일 |
|---------|------|------|
| ErrorProneScorer | Nagappan 2006 | `filtering/error_prone.py` |
| GitRanker | Recency/Ownership | `git_enrichment/ranker.py` |
| ScopeSelector | RepoMap + Intent | `scope/selector.py` |

## 8. Fusion

```
src/contexts/retrieval_search/infrastructure/fusion/
├── engine.py                # RRF
├── smart_interleaving.py
└── golden_set.py
```

## 9. Context Building

```
src/contexts/retrieval_search/infrastructure/context_builder/
├── compressor.py
├── dependency_order.py
├── domain_aware.py
└── position_bias_reorderer.py
```

## 10. Feedback & Training

| 컴포넌트 | 기술 | 파일 |
|---------|------|------|
| ContrastiveTrainer | Contrastive Learning | `feedback/contrastive_training.py` |
| HardNegativeMiner | Hard Negative Mining | `feedback/hard_negatives.py` |
| TestTimeCompute | TTC Scaling | `reasoning/test_time_compute.py` |

---

# Part 5. Agent & Reasoning

## 1. LATS (Language Agent Tree Search)

```
src/agent/shared/reasoning/lats/
├── lats_search.py           # MCTS + UCT
└── lats_reflexion.py        # Verbal Feedback, 3x 효율

4단계: Selection → Expansion → Simulation → Backpropagation
```

## 2. Tree-of-Thought (ToT)

```
파일: agent/domain/reasoning/tot/tot_scorer.py
알고리즘: MCDM (Multi-Criteria Decision Making)
```

## 3. Deep Reasoning Orchestrator

```
파일: agent/orchestrator/deep_reasoning_orchestrator.py
전략: o1/r1, Beam, Debate, AlphaCode + Constitutional AI
```

### 파일 위치

```
src/agent/shared/reasoning/
├── lats/
├── tot/
├── beam/beam_search.py
├── deep/
│   ├── o1_engine.py
│   └── r1_engine.py
├── debate/
├── sampling/               # AlphaCode
├── constitutional/
├── critic/
└── ttc/
    ├── adaptive_sampler.py
    ├── budget_optimizer.py
    └── compute_allocator.py
```

## 4. Query DSL

```python
# FlowExpr
source >> sink    # N-hop forward
source > sink     # 1-hop adjacency
source << sink    # N-hop backward

# 체이닝
(source >> sink).via(E.DFG).where(depth=5)

# Node Selectors
Q.Var("user_input")
Q.Func("process")
Q.Call("execute")
Q.Source("request")
Q.Sink("sql")
Q.Module("core.*")
Q.Any()
```

## 5. Agent Router (4 Components)

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| UnifiedRouter | < routing | `router/unified_router.py` |
| IntentClassifier | 의도 분류 | `router/intent_classifier.py` |
| ConfidenceScorer | 신뢰도 점수 | `router/confidence_scorer.py` |
| Router | 기본 라우터 | `router/router.py` |

## 6. Agent Workflow

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| StateMachine | IDLE→PLANNING→EXECUTING | `workflow/state_machine.py` |
| EventBus | 이벤트 버스 | `events/event_bus.py` |
| TaskPlanner | DAG-based | `task_graph/planner.py` |
| BatchProcessor | Priority Queue, Backpressure | `infrastructure/batch_processor.py` |

## 7. Safety & Compliance

```
src/agent/domain/safety/
├── orchestrator.py          # SafetyOrchestrator
├── models.py                # 11 Enums
└── policies.py

src/agent/adapters/safety/
├── secret_scanner.py        # Pattern, Entropy, PII
├── license_checker.py       # allowed/review/blocked
└── action_gate.py

src/agent/adapters/guardrail/
└── guardrails_adapter.py    # NeMo Guardrails
```

## 8. Code Editing

```
src/agent/domain/code_editing/
├── fim/models.py            # Fill-in-the-Middle
├── atomic_edit/models.py
└── refactoring/models.py

src/agent/adapters/code_editing/
├── fim/adapter.py
├── atomic_edit/adapter.py
└── refactoring/
    ├── code_transformer.py
    ├── type_hint_generator.py
    └── symbol_finder.py
```

## 9. ShadowFS v2

```
파일: codegen_loop/infrastructure/shadowfs/core_v2.py
특징: MVCC, Optimistic Concurrency, < write
참조: Bernstein & Goodman (1983), OverlayFS (2014)
```

## 10. Cascade (Bug Fix Pipeline)

```
src/agent/adapters/cascade/
├── orchestrator.py
├── reproduction_engine.py
├── fuzzy_patcher.py
├── graph_pruner.py
└── process_manager.py
```

## 11. Agent Tools

| 도구 | 기능 |
|-----|------|
| VulnerabilityScan | 보안 취약점 스캔 |
| CallGraph | 호출 그래프 조회 |
| FindReferences | 참조 검색 |
| SymbolDefinition | 심볼 정의 조회 |
| ChangeImpact | 변경 영향 분석 |

### 파일 위치

```
src/agent/tools/code_foundation/
├── understanding/
│   ├── symbol_definition.py
│   ├── find_references.py
│   └── call_graph.py
├── impact/
│   ├── change_impact.py
│   └── affected_code.py
└── security/
    └── vulnerability_scan.py
```

---

# Part 6. Memory Systems

## 1. Episodic Memory

```
파일: session_memory/infrastructure/episodic.py
기능: 태스크 실행 기록, 유사성 검색, 사용량 추적
```

## 2. Working Memory

```
파일: session_memory/infrastructure/working.py
기능: 현재 세션 컨텍스트, 단기 기억
```

## 3. Semantic Memory (6 Managers)

| Manager | 기능 | 파일 |
|---------|------|------|
| SemanticMemoryManager | 통합 관리 | `semantic/semantic_memory_manager.py` |
| BugPatternManager | 버그 패턴 학습 | `semantic/bug_pattern_manager.py` |
| CodePatternManager | 코드 패턴 학습 | `semantic/code_pattern_manager.py` |
| CodeRuleManager | 코드 규칙 관리 | `semantic/code_rule_manager.py` |
| ProjectKnowledgeManager | 프로젝트 지식 | `semantic/project_knowledge_manager.py` |
| StyleAnalyzer | 코딩 스타일 분석 | `semantic/style_analyzer.py` |

### 파일 위치

```
src/contexts/session_memory/infrastructure/
├── episodic.py
└── semantic/
    ├── code_pattern_manager.py
    ├── bug_pattern_manager.py
    └── project_knowledge_manager.py
```

## 4. Memory Pipeline

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| ReadPipeline | 메모리 조회 | `read_pipeline.py` |
| WritePipeline | 메모리 저장 | `write_pipeline.py` |
| PatternMatcher | 패턴 매칭 | `pattern_matcher.py` |
| Reflection | 자기 성찰 | `reflection.py` |

## 5. Memory Persistence

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| MemoryStore | 메모리 저장소 | `persistence/store.py` |
| EmbeddingStore | 임베딩 저장 | `persistence/embedding_store.py` |
| PostgresStore | PostgreSQL 저장 | `persistence/postgres_store.py` |
| PatternRepository | 패턴 저장소 | `repositories/pattern_repository.py` |

## 6. Memory Infra

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| MemoryCache | 메모리 캐시 | `cache.py` |
| DistributedLock | 분산 락 | `distributed_lock.py` |
| Fallback | 폴백 처리 | `fallback.py` |
| Scoring | 메모리 스코어링 | `scoring.py` |
| Retrieval | 메모리 검색 | `retrieval.py` |

## 7. Agent Experience

```
파일: agent/domain/experience/models.py
구조: problem, strategy, code_chunks, success, score
```

---

# Part 7. Infrastructure

## 1. Three-Tier Cache

| Tier | 저장소 | 속도 |
|------|--------|------|
| L1 | In-Memory LRU | ~ |
| L2 | Redis | ~1- |
| L3 | PostgreSQL/Qdrant | ~10- |

```
파일: infra/cache/three_tier_cache.py
```

## 2. Advanced Cache

```
파일: agent/infrastructure/cache/advanced_cache.py
특징: Bloom Filter, LRU, Compression, Warming
```

## 3. Resilience Patterns

| 패턴 | 설명 | 파일 |
|------|------|------|
| CircuitBreaker | 장애 차단 | `infra/resilience.py` |
| Retry + Backoff + Jitter | 재시도 | `infra/resilience.py` |
| Fallback | 폴백 | `infra/resilience.py` |
| Bulkhead | 격리 | `infra/resilience.py` |
| Token Bucket | Rate Limiting | `infra/resilience.py` |
| WAL | Write-Ahead Log | `storage/wal.py` |
| ConsistencyChecker | Cross-index validation | `service/consistency_checker.py` |

## 4. LLM Integration

```
src/infra/llm/
├── litellm_adapter.py       # Multi-Provider
├── local_llm.py
└── rate_limiter.py

Provider: OpenAI, Anthropic, Azure, Ollama
```

## 5. Observability

```
src/infra/observability/
├── metrics.py               # OpenTelemetry/Prometheus
├── tracing.py               # 분산 트레이싱
├── alerting.py              # Slack/PagerDuty
└── cost_tracking.py         # LLM/Vector 비용
```

## 6. Storage

```
src/infra/storage/
├── postgres.py
├── postgres_enhanced.py
└── sqlite.py
```

## 7. Storage (Zero Configuration)

### 7.1 Qdrant Embedded Mode

**구현 완료**: 
**테스트**: 150/150 PASSED
**상태**: Production Ready

**3가지 모드**:

| Mode | 용도 | 시작 시간 | 처리량 | 영속성 | 동시 접근 |
|------|------|----------|--------|--------|----------|
| memory | 테스트 | < | 666 vec/s | X | 무제한 |
| embedded | 로컬 개발 | ~1-2s | 333 vec/s | O | 단일 프로세스 |
| server | 프로덕션 | ~5-10s | 1000 vec/s | O | 다중 클라이언트 |

**핵심 기능**:
```python
# Helper function (DRY)
from src.infra.vector import create_qdrant_client

# Memory mode (테스트)
client = create_qdrant_client(mode="memory")

# Embedded mode (로컬 - 기본값)
client = create_qdrant_client(
    mode="embedded",
    storage_path="./data/qdrant_storage",
    check_disk_space=True,      # 100MB 최소 체크
    min_disk_space_mb=100
)

# Server mode (프로덕션)
client = create_qdrant_client(
    mode="server",
    url="http://qdrant:6333",
    timeout=120,                 # Configurable
    prefer_grpc=True             # 2-5x faster
)
```

**Critical Protections**:
- ✅ Concurrent access: File-based locking (fcntl.LOCK_EX)
- ✅ Disk space: Pre-creation 체크 + 상세 에러
- ✅ Resource leak: atexit cleanup
- ✅ Type safety: Literal types + Pydantic

**파일 위치**:
```
src/infra/vector/
├── __init__.py               # create_qdrant_client, _LockFileManager
└── qdrant.py                 # QdrantAdapter (upsert, search, etc.)
```

### 7.2 SQLite Lock Store ()

**구현 완료**: 
**테스트**: 12/12 PASSED
**상태**: Production Ready

**3가지 모드**:

| Mode | 용도 | 의존성 | 성능 |
|------|------|--------|------|
| memory | 테스트 | 없음 | < |
| sqlite | 로컬 개발 (기본) | Python 내장 | < |
| redis | 팀/서버 | Redis | < |

**핵심 기능**:
```python
# Auto-detect (권장)
from src.agent.infrastructure.sqlite_lock_store import create_lock_store

store = create_lock_store(mode="auto")  # Redis 있으면 Redis, 없으면 SQLite

# SQLite 모드
store = SQLiteLockStore(".agent_locks.db")
await store.set(file_path, lock_data, ttl=1800)
await store.get(file_path)
await store.delete(file_path)
await store.scan()  # Redis SCAN 호환
await store.cleanup_expired()  # TTL 자동 정리
```

**파일 위치**:
```
src/agent/infrastructure/
└── sqlite_lock_store.py      # SQLiteLockStore, create_lock_store
```

### 7.3 Embedding Worker

```
파일: multi_index/infrastructure/vector/worker_pool.py
특징: N workers, asyncio.Condition notify
```

---

# Part 8. Indexing Pipeline

## 1. 9-Stage Indexing Pipeline

**🚀 SOTA Update**: IR Stage now uses modular pipeline architecture with Rust L1 optimizations (See Part 3)

| Stage | 클래스 | 기능 | Performance |
|-------|--------|------|-------------|
| 1 | GitStage | Git 상태 수집 | ~ |
| 2 | DiscoveryStage | 파일 탐색 | ~ |
| 3 | ParsingStage | Tree-sitter AST 파싱 | ~ |
| 4 | IRStage | 🚀 **Modular IR Pipeline** (9 pluggable stages) | **7.6x faster** (Rust L1 occurrence gen) |
| 5 | SemanticIRStage | Semantic IR 생성 | ~ |
| 6 | GraphStage | 그래프 빌딩 | ~ |
| 7 | ChunkStage | 청크 생성 | ~ |
| 8 | RepoMapStage | RepoMap 빌딩 | ~ |
| 9 | IndexingStage | 멀티 인덱스 저장 | ~ |

**문서:** `_docs/modules/indexing/` (pipeline/ops/verification)

**IR Pipeline 주요 변경사항:**
- **Modular Architecture**: 9개 독립 스테이지로 재구성 (See Part 3.1)
- **Rust L1 Occurrence Generation**: Python L2에서 Rust L1으로 이동 (7.6x 성능 향상)
- **Cross-File Resolver**: RFC-062 기반 import 해석 인프라 추가
- **Lazy Imports**: Circular dependency 해결

### 파일 위치

```
src/contexts/analysis_indexing/infrastructure/
├── orchestrator.py
├── orchestrator_slim.py
├── job_orchestrator.py
└── stages/
    ├── git_stage.py
    ├── discovery_stage.py
    ├── parsing_stage.py
    ├── ir_stage.py
    ├── graph_stage.py
    ├── chunk_stage.py
    ├── repomap_stage.py
    └── indexing_stage.py
```

## 2. Indexing Modes

| Mode | Layer | 범위 | 시간 (10K) |
|------|-------|------|-----------|
| FAST | L1-L2 | 변경 파일만 | ~5초 |
| BALANCED | L1-L2-L3 | 변경 + 1-hop | ~2분 |
| DEEP | L1-L2-L3-L4 | 변경 + 2-hop | ~30분 |
| BOOTSTRAP | L1-L2-L3_SUMMARY | 전체 | ~10분 |
| REPAIR | 동적 | 복구 | 가변 |

**자동 Escalation:** SIGNATURE_CHANGED 감지 시 FAST/BALANCED -> DEEP 자동 전환

## 3. Incremental Indexing

**트리거 방식 (6종):**
- ShadowFS Plugin (IDE 편집, <)
- FileWatcher (외부 변경, <)
- BackgroundScheduler (Idle 5분 후 자동)
- ChangeDetector (CLI/API)
- Job Queue (대규모 배치)
- PR 분석 (미구현)

**핵심 컴포넌트:**
```
src/contexts/analysis_indexing/infrastructure/
├── change_detector.py       # Git/mtime/hash 3단계
├── scope_expander.py        # SIGNATURE_CHANGED 자동 escalation
├── mode_manager.py          # 모드 자동 선택
├── background_scheduler.py  # Idle -> BALANCED
├── file_watcher.py          # Watchdog 기반
├── watcher_debouncer.py     #  debounce (Race condition 수정)
├── job_orchestrator.py      # Distributed Lock + Checkpoint
└── snapshot_gc.py           # 스냅샷 GC
```

**엣지케이스:** 16개 문서화 및 해결 (`indexing/edge-case-coverage.md`)

## 4. Incremental Parsing

```
파일: code_foundation/infrastructure/parsing/incremental_parser.py
특징: Tree-sitter edit/reparse, 변경 부분만 재파싱
```

## 5. Git History Analysis

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| Churn | 변경 빈도 | `git_history/churn.py` |
| Blame | 작성자 | `git_history/blame.py` |
| CoChange | 함께 변경 | `git_history/cochange.py` |
| Evolution | 진화 추적 | `git_history/evolution.py` |

## 6. Chunking System (6레벨)

```
Repo → Project → Module → File → Class → Function
```

### 파일 위치

```
src/contexts/code_foundation/infrastructure/chunk/
├── builder.py
├── models.py
├── store.py
├── cached_store.py
├── store_postgres.py
├── diff_analyzer.py
├── fqn_builder.py
└── visibility.py
```

## 7. RepoMap

```
src/contexts/repo_structure/infrastructure/
├── builder/orchestrator.py
├── pagerank/
│   ├── aggregator.py
│   ├── incremental.py
│   └── engine.py           # rustworkx (400x faster)
└── summarizer/
    ├── llm_summarizer.py
    └── hierarchical_summarizer.py
```

## 8. CodeGen Specs (3 Types)

| Spec | 기능 | 파일 |
|------|------|------|
| ArchSpec | Layer Violation 감지 | `codegen_loop/domain/specs/arch_spec.py` |
| IntegritySpec | 코드 무결성 검사 | `codegen_loop/domain/specs/integrity_spec.py` |
| SecuritySpec | 보안 검사 | `codegen_loop/domain/specs/security_spec.py` |

---

# Part 9. 추가 컴포넌트

## 1. Monorepo Detection

```
파일: code_foundation/infrastructure/dependency/monorepo_detector.py

지원:
- npm/yarn/pnpm workspaces
- Cargo workspaces
- Go workspaces (go.work)
- Python monorepos
- Lerna/Nx/Turborepo
```

## 2. Test Detector

```
파일: code_foundation/infrastructure/chunk/test_detector.py

패턴:
- Function: test_*, *_test, it, describe
- File: test_*.py, *.spec.ts, *_test.go
- Decorator: @pytest.mark, @Test
```

## 3. Visibility Extractor

```
파일: code_foundation/infrastructure/chunk/visibility.py

언어별:
- Python: _private, __dunder
- TS/JS: private, protected, public
- Go: Uppercase=public, lowercase=private
```

## 4. Graph Impact Analyzer

```
파일: code_foundation/infrastructure/graph/impact_analyzer.py

기능:
- 심볼 수준 affected callers 탐색
- 시그니처 변경 감지 (SIGNATURE_CHANGED)
- Transitive callers 분석
```

## 5. Call Graph (3종)

| 컴포넌트 | 알고리즘 | 파일 |
|---------|---------|------|
| `PreciseCallGraph` | Context-sensitive | `graphs/precise_call_graph.py` |
| `ContextSensitiveAnalyzer` | K-CFA | `graphs/context_sensitive_analyzer.py` |
| `CHACallGraph` | Class Hierarchy Analysis | `heap/cha_call_graph.py` |

## 6. Document Processing

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| `DocumentService` | 문서 처리 통합 | `document/service.py` |
| `DocumentScorer` | 문서 중요도 점수 | `document/scoring.py` |
| `CodeLinker` | 코드-문서 연결 | `document/code_linker.py` |
| `NotebookParser` | Jupyter 노트북 | `document/parsers/notebook_parser.py` |
| `PDFParser` | PDF 문서 | `document/parsers/pdf_parser.py` |

## 7. LSP Adapters (7종)

| 언어 | 파일 |
|-----|------|
| Python | `ir/lsp/pyright.py` |
| TypeScript | `ir/lsp/typescript.py` |
| Rust | `ir/lsp/rust_analyzer.py` |
| Go | `ir/lsp/gopls.py` |
| Java | `ir/lsp/jdtls.py` |
| Kotlin | `ir/lsp/kotlin.py` |
| TSMorph | `ir/external_analyzers/tsmorph_adapter.py` |

## 8. Query Infrastructure

| 컴포넌트 | 기능 | 파일 |
|---------|------|------|
| QueryEngine | 쿼리 실행 엔진 | `query/query_engine.py` |
| QueryExecutor | 쿼리 실행자 | `query/query_executor.py` |
| TraversalEngine | 그래프 순회 | `query/traversal_engine.py` |
| NodeIndex | 노드 인덱스 | `query/indexes/node_index.py` |
| EdgeIndex | 엣지 인덱스 | `query/indexes/edge_index.py` |
| DefaultStrategy | 기본 전략 | `query/strategies/default_strategy.py` |

---

# Part 10. 개발자 가이드

## 1. Query DSL 사용법

```python
from src.contexts.code_foundation.domain.query.factories import Q, E

# Node Selectors
Q.Var("user_input")              # 변수
Q.Func("process")                # 함수
Q.Call("execute")                # 호출
Q.Source("request")              # 보안 source
Q.Sink("sql")                    # 보안 sink
Q.Module("core.*")               # 모듈 glob
Q.Any()                          # 와일드카드

# Flow Expressions
source >> sink                   # N-hop forward
source > sink                    # 1-hop direct
(Q.Source("request") >> Q.Sink("sql")).via(E.DFG).where(depth=5)
```

## 2. 검출 규칙 등록

### Atoms (taint/rules/atoms/python.atoms.yaml)

```yaml
atoms:
  - id: input.http.custom
    kind: source                 # source|sink|propagator|sanitizer
    tags: [untrusted, web]
    match:
      - base_type: "myapp.Request"
        read: "params"

  - id: sink.sql.custom
    kind: sink
    match:
      - base_type: "mydb.Cursor"
        call: "execute"
        args: [0]
        constraints:
          arg_type: "not_const"
```

### Policies (taint/rules/policies/python.policies.yaml)

```yaml
policies:
  - id: "custom-injection"
    severity: critical
    cwe: "CWE-89"
    grammar:
      WHEN: { tag: untrusted }
      FLOWS: [{ id: sink.sql.custom }]
      BLOCK: { UNLESS: { kind: sanitizer, tag: sql } }
```

## 3. 인덱싱 모드

| Mode | 범위 | 사용 시점 |
|------|------|----------|
| FAST | 변경만 | 빠른 피드백 |
| BALANCED | +직접 의존성 | 일반 |
| DEEP | +전이 의존성 | 시그니처 변경 |
| FULL | 전체 | 초기화 |

## 4. 보안 분석

```python
# TaintAnalysisService
service = TaintAnalysisService(atom_repo, policy_repo, matcher, validator)
results = await service.analyze(ir_doc, control_config)

# DeepSecurityAnalyzer (QUICK|DEEP|AUTO|REALTIME|AUDIT)
analyzer = DeepSecurityAnalyzer(ir_doc, call_graph)
results = await analyzer.analyze(mode=AnalysisMode.AUTO)
```

---

# Part 11. 참조 알고리즘/논문

| 분류 | 알고리즘 | 출처 |
|------|----------|------|
| Dominators | Cooper-Harvey-Kennedy | 2001 |
| SSA | Cytron et al. | 1991 |
| Points-to | Andersen | - |
| Separation Logic | Facebook Infer | - |
| SMT | Z3 Solver | Microsoft |
| Slicing | Weiser's Algorithm | 1981 |
| MCTS/UCT | LATS | 2023 |
| Tree-of-Thought | Yao et al. | 2023 |
| HyDE | Gao et al. | 2022 |
| Self-RAG | Asai et al. | 2023 |
| ColBERT | Late Interaction | - |
| LLMLingua | Jiang et al. | 2023 |
| AlphaCode | DeepMind | - |
| PageRank | Google | - |
| RRF | Reciprocal Rank Fusion | - |
| ShadowFS | Bernstein & Goodman (MVCC), OverlayFS | 1983, 2014 |

---

# Part 12. TODO / 개선 작업

## 0. 구현 완료 (검증 완료)

| 컴포넌트 | 상태 | 검증 | 파일 |
|---------|------|------|------|
| **RealIRAnalyzerAdapter** | ✅ 완료 | 25/25 테스트 통과 | `real_adapters.py` |
| **RealImpactAnalyzerAdapter** | ✅ 완료 | 통합 검증 | `real_adapters.py` |
| **RealCallGraphBuilderAdapter** | ✅ 완료 | 통합 검증 | `real_adapters.py` |
| **RealCrossFileResolverAdapter** | ✅ 완료 | 통합 검증 | `real_adapters.py` |
| **RealDependencyGraphAdapter** | ✅ 완료 | AST fallback | `real_adapters.py` |
| **RealSecurityAnalyzerAdapter** | ✅ 완료 | TaintService 연동 | `real_adapters.py` |
| **Cascade._generate_fix()** | ✅ 완료 | DeepReasoning 연동 | `cascade/orchestrator.py` |
| **Cascade._build_graph()** | ✅ 완료 | GraphBuilder 연동 | `cascade/orchestrator.py` |
| **다국어 감지** | ✅ 완료 | 9개 언어 | `deep_reasoning_orchestrator.py` |
| **CodeBERT 통합** | ✅ 완료 | fallback 지원 | `embedding_service.py` |
| **Rope Refactoring** | ✅ 완료 | AST fallback | `code_transformer.py` |

## 1. 남은 작업 (P2-P3)

## 2. High Priority (P2) - Taint 확장

| 영역 | TODO | 파일 |
|------|------|------|
| Taint | Policy wildcard 지원 | `taint/policy.py` |
| Taint | Q.DSL with_barrier 완성 | `taint/compilation/policy_compiler.py` |
| Taint | FIELD_ACCESS 매칭 | `taint/matching/type_aware_matcher.py` |
| IR | Semantic IR 지원 추가 | `adapters/graph_builder_adapter.py` |
| IR | 거리 계산 구현 | `ir/retrieval_index.py` |

## 3. Medium Priority (P3)

| 영역 | TODO | 파일 |
|------|------|------|
| Heap | Heap alias 전역 재계산 | `analyzers/deep_security_analyzer.py` |
| Query | Cost-based optimization | `query/strategies/default_strategy.py` |
| Container | Experience Store v2 연동 | `container.py` |
| Docker | Docker 격리 모드 완성 | `sandbox_adapter.py` (fallback→real) |

## 2. 언어 지원

| 언어 | 상태 | Generator | LSP |
|-----|------|-----------|-----|
| Python | ✅ 완료 | 완료 | Pyright |
| TypeScript/JS | ✅ 완료 | 1000줄+ | ts-morph |
| Java | ✅ 완료 | 2600줄+ | JDTLS |
| Kotlin | 🟡 부분 | 기본 | Kotlin LSP |
| Go | ❌ 미구현 | - | gopls |
| Rust | ❌ 미구현 | - | rust-analyzer |

## 3. 통합 검증 결과 (2024-12-13)

| 테스트 범위 | 결과 |
|------------|------|
| Integration Tests | **25/25 통과 (100%)** |
| Hexagonal Architecture | ✅ Port 준수 |
| SOLID Principles | ✅ 검증 완료 |
| No Fake/Stub | ✅ Real 컴포넌트만 |
| Stress Test | ✅ 100 concurrent OK |
| Memory Leak | ✅ <10% growth |
| 다국어 지원 | ✅ 9개 언어 |

**연동 완료 컴포넌트:**
```
Agent Layer (real_adapters.py) → Domain Layer
├─ ImpactAnalyzer ✅
├─ CallGraphBuilder ✅
├─ CrossFileResolver ✅
├─ DependencyGraph ✅
├─ SecurityAnalyzer ✅
└─ TaintAnalysisService ✅
```

## 4. NotImplementedError 현황

| 상태 | 개수 | 설명 |
|------|------|------|
| **해결 완료** | 124/126 | Agent Tools 연동 완료 |
| 남은 2개 | 2 | 의도적 (Guard/Deprecated) |

---

# 최종 통계

| 카테고리 | 개수 |
|---------|------|
| Bounded Contexts | 11 |
| Taint Analysis Layers | 10 |
| Memory Safety Checkers | 9 |
| IR Layers | 9 |
| Search Indexes | 6 |
| Query Enhancers | 8 |
| Rerankers | 11 |
| Reasoning Engines | 6 |
| Cache Layers | 4 |
| Indexing Stages | 9 |
| Agent Tools | 5 |
| Semantic IR Builders | 4 |
| Call Graph Variants | 3 |
| Document Parsers | 5 |
| Dependency Analyzers | 4 |
| Parsing Components | 4 |
| Symbol Graph Components | 2 |
| Search Index Adapters | 3 |
| Chunk Extensions | 5 |
| Additional Analyzers | 5 |
| LSP Adapters | 7 |
| IR Extensions | 4 |
| Value Tracking | 2 |
| Caching Components | 4 |
| Validators/Checkers | 6 |
| Semantic Diff Components | 4 |
| Reasoning Executors | 4 |
| Feedback/Training | 3 |
| Query Planning | 3 |
| Semantic Memory Managers | 6 |
| Memory Pipeline | 4 |
| Memory Persistence | 4 |
| Memory Infra | 5 |
| CodeGen Specs | 3 |
| Agent Router | 4 |
| Agent Workflow | 4 |
| Query Infrastructure | 6 |
| **총 핵심 알고리즘** | **175+** |
| **TODO 항목** | **~50개** (실제 미구현) |
| **NotImplementedError** | **126개** (대부분 연동 이슈) |
| **도메인 구현률** | **90%+** |
| **Agent 연동률** | **~60%** (real_adapters 미완) |

---

## 최근 업데이트

### : 인덱싱 & Multi-Agent 시스템
- 인덱싱 파이프라인 13개 문서 (280페이지)
- Multi-Agent Deadlock 해결 (LockKeeper, DeadlockDetector)
- SQLite Lock Store (Redis 제거)
- 56개 테스트 추가 (91% 통과)
- 비판적 검증 및 버그 수정 (Race condition, 메모리 누수)

### : Qdrant Embedded Mode
- 3가지 실행 모드 추가 (memory/embedded/server)
- Docker 불필요 (로컬 개발)
- Critical protections (lock, disk space, timeout)
- 150 tests (100% passed)
- Production ready

---

**문서 최종 업데이트**:  v3.2 (인덱싱 시스템 완전 문서화)
