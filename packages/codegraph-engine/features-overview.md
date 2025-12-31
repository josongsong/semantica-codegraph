# Codegraph Engine 전체 기능 목록 (Features Overview)

> **최종 업데이트**: 2024-12-28
> **총 기능 수**: 95개 (대분류 15개, 중분류 35개, 소분류 45개)
> **총 LOC**: ~50,000+ LOC

---

## 📊 요약

| 카테고리 | 기능 수 | 핵심 모듈 |
|---------|--------|----------|
| 🔴 대분류 (Large) | 15개 | IR Pipeline, Taint Analysis, Semantic IR 등 |
| 🟠 중분류 (Medium) | 35개 | SCCP, Slicing, Type Inference 등 |
| 🟢 소분류 (Small) | 45개 | LSP Adapters, Checkers, Utilities 등 |

---

## 🔴 대분류 (Large) - 핵심 시스템 [15개]

### 1. IR Pipeline v3 (Stage-based Architecture)
**핵심 파일**:
- `code_foundation/infrastructure/ir/pipeline/builder.py` - PipelineBuilder (370 LOC)
- `code_foundation/infrastructure/ir/pipeline/pipeline.py`
- `code_foundation/infrastructure/ir/pipeline/orchestrator.py`

**Pipeline Stages (11개)**:
| Stage | 파일 | 설명 |
|-------|------|------|
| Cache | `stages/cache.py` | 캐시 레이어 |
| Structural | `stages/structural.py` | 구조적 IR 생성 |
| LSP Type | `stages/lsp_type.py` | LSP 타입 보강 |
| Cross-file | `stages/cross_file.py` | 크로스 파일 해석 |
| Retrieval | `stages/retrieval.py` | 검색 인덱스 |
| Provenance | `stages/provenance.py` | 출처 추적 |
| Template IR | `stages/template_ir.py` | 템플릿 IR |
| Diagnostics | `stages/diagnostics.py` | 진단 |
| Package | `stages/package.py` | 패키지 분석 |
| Analysis | `stages/analysis.py` | 분석 레이어 |

**알고리즘/방법론**:
- Fluent Builder 패턴
- Stage 기반 순차 실행
- 프리셋 프로파일: `fast` / `balanced` / `full`

**성능**:
- Rust 통합 시 **11.4x** 속도 향상
- Django 901 파일: 0.166s (Python: 8.8s)

---

### 2. Rust IR Adapter (53x Speedup)
**핵심 파일**:
- `code_foundation/infrastructure/generators/rust_adapter.py` - RustIRAdapter (400+ LOC)

**알고리즘/방법론**:
- PyO3 바인딩
- msgpack 직렬화 (25x 빠름)
- GIL-free 병렬 처리 (Rayon)

**성능**:
| Repository | Files | Rust | Python | Speedup |
|------------|-------|------|--------|---------|
| Django | 901 | 0.166s | 8.8s | **53x** |
| Ansible | 1,774 | 0.090s | 17.4s | **194x** |
| Flask | 83 | 0.008s | 0.8s | **100x** |

---

### 3. Interprocedural Taint Analysis
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/interprocedural_taint.py` - InterproceduralTaintAnalyzer (1,900 LOC)
- `code_foundation/infrastructure/analyzers/fixpoint_taint_solver.py` - WorklistTaintSolver (540 LOC)

**알고리즘/방법론**:
- **Worklist-based Fixpoint Algorithm**: 고정점 수렴
- **Tarjan's SCC**: 강연결 요소 분해
- **Context-sensitive**: 콜 컨텍스트 구분
- **Field-sensitive**: 필드별 오염 추적
- **Path-sensitive**: 경로별 조건 분석

**성능**:
- Rust 가속 시 **10-50x** 향상

---

### 4. TaintAnalysisService (Application Layer)
**핵심 파일**:
- `code_foundation/application/taint_analysis_service.py` - TaintAnalysisService (924 LOC)

**알고리즘/방법론**:
- Vulnerability Building: Source → Sink
- DFG 기반 경로 탐색
- Guard Detection (sanitizer 인식)
- FQN 기반 정확 매칭 (`builtins.eval`, `os.system`)

---

### 5. Semantic IR Builder (CFG/BFG/DFG/Expression)
**핵심 파일**:
- `code_foundation/infrastructure/semantic_ir/builder.py` - DefaultSemanticIrBuilder (350 LOC)
- `code_foundation/infrastructure/semantic_ir/cfg/builder.py` - CfgBuilder (450 LOC)
- `code_foundation/infrastructure/semantic_ir/bfg/builder.py` - BfgBuilder (380 LOC)
- `code_foundation/infrastructure/semantic_ir/expression/builder.py` - ExpressionBuilder (2,280 LOC)

**생성 그래프**:
| 그래프 | 설명 |
|--------|------|
| CFG | Control Flow Graph |
| BFG | Basic Flow Graph (단순화된 CFG) |
| DFG | Data Flow Graph |
| Expression IR | 표현식 분석 |

---

### 6. SSA Construction (SOTA)
**핵심 파일**:
- `code_foundation/infrastructure/dfg/ssa/ssa_builder.py` - SSABuilder (260 LOC)
- `code_foundation/infrastructure/dfg/ssa/dominator.py` - DominatorTree (113 LOC)

**알고리즘/방법론**:
- **Cooper-Harvey-Kennedy Algorithm**: Dominator Tree 계산
- **Dominance Frontier**: 지배 경계 계산
- **Phi-node Insertion**: φ 함수 삽입
- **Variable Renaming**: 변수 재명명

---

### 7. Points-to Analysis (Andersen-style)
**핵심 파일**:
- `code_foundation/infrastructure/heap/points_to.py` - PointsToAnalysis (690 LOC)

**알고리즘/방법론**:
- **Andersen's Algorithm**: 포인터 분석
- **Constraint Generation**: 제약 조건 생성
- **Cycle Detection**: 순환 감지 (rustworkx 최적화)

---

### 8. Multi-Index System
**핵심 파일**:
- `multi_index/infrastructure/vector/adapter_qdrant.py` - QdrantVectorIndex (720 LOC)
- `multi_index/infrastructure/lexical/tantivy/code_index.py` - TantivyCodeIndex (600 LOC)
- `multi_index/infrastructure/symbol/symbol_embedding.py` - SymbolEmbeddingManager (350 LOC)

**인덱스 타입**:
| 타입 | 엔진 | 용도 |
|------|------|------|
| Vector | Qdrant | 시맨틱 검색 |
| Lexical | Tantivy | Full-text 검색 |
| Symbol | PostgreSQL | 심볼 검색 |
| Fuzzy | - | 퍼지 매칭 |

---

### 9. GraphBuilder (IR → Graph 변환)
**핵심 파일**:
- `code_foundation/infrastructure/graph/builder.py` - GraphBuilder (910 LOC)

**알고리즘/방법론**:
- IR Node → Graph Node 변환
- IR Edge → Graph Edge 변환 (CFG/DFG 포함)
- Routes/Services/Request Flow 인덱스 빌드

---

### 10. RustTaintEngine (Rust 기반 고속 Taint)
**핵심 파일**:
- `reasoning_engine/infrastructure/engine/rust_taint_engine.py` - RustTaintEngine (755 LOC)

**알고리즘/방법론**:
- **Bidirectional BFS**: 양방향 검색
- **Bloom Filter**: 노드 존재 여부 빠른 체크
- **Parallel Path Finding**: 멀티스레드 경로 검색
- **rustworkx 그래프**: Rust 기반 연산

**성능**:
- LRU 캐시
- ThreadPoolExecutor 병렬화
- **10-50x** 속도 향상

---

### 11. DependencyAnalyzer (의존성 분석)
**핵심 파일**:
- `code_foundation/infrastructure/dependency/analyzer.py` - DependencyAnalyzer (730 LOC)
- `code_foundation/infrastructure/dependency/monorepo_detector.py` - MonorepoDetector (475 LOC)

**알고리즘/방법론**:
- **Tarjan's SCC Algorithm**: 순환 의존성 탐지
- **Dependency Layer Calculation**: 계층화
- **Change Impact Analysis**: BFS 기반 영향 전파
- **Workspace Boundary Validation**: 패키지 간 규칙 검증

---

### 12. UnifiedAnalyzer (통합 분석기)
**핵심 파일**:
- `code_foundation/infrastructure/ir/unified_analyzer.py` - UnifiedAnalyzer (946 LOC)

**Enable Flags**:
- `enable_pdg`: PDG 분석
- `enable_taint`: Taint 분석
- `enable_slicing`: Slicing
- `enable_interprocedural`: 함수 간 분석
- `enable_alias`: Alias 분석
- `use_native`: Rust 네이티브 사용

---

### 13. ReasoningPipeline (추론 파이프라인)
**핵심 파일**:
- `reasoning_engine/application/reasoning_pipeline.py` - ReasoningPipeline (848 LOC)

**제공 분석**:
- Performance Analysis
- Performance Regression
- Effect Analysis
- Impact Analysis
- Slice Extraction
- Cross-language Flow
- Cost Analysis

---

### 14. Indexing Orchestrator
**핵심 파일**:
- `analysis_indexing/infrastructure/orchestrator.py` - IndexingOrchestrator (217 LOC)

**Stages**:
- Discovery → Parsing → IR → Semantic IR → Graph → Chunk → Lexical → Vector → Symbol → Fuzzy → Domain Meta

---

### 15. ChunkBuilder (RAG Retrieval)
**핵심 파일**:
- `code_foundation/infrastructure/chunk/builder.py` - ChunkBuilder (1,581 LOC)

**Chunk 타입 (12개)**:
| 타입 | 설명 |
|------|------|
| REPO | 레포지토리 |
| PROJECT | 프로젝트 |
| MODULE | 모듈 |
| FILE | 파일 |
| CLASS | 클래스 |
| FUNCTION | 함수 |
| DOCSTRING | 문서 |
| HEADER | 헤더 |
| SKELETON | 스켈레톤 |
| USAGE | 사용 예시 |
| CONSTANT | 상수 |
| VARIABLE | 변수 |

---

## 🟠 중분류 (Medium) - 분석 엔진 [35개]

### 16. SCCP (Sparse Conditional Constant Propagation)
**핵심 파일**:
- `code_foundation/infrastructure/dfg/constant/solver.py` - SparseSolver (740 LOC)
- `code_foundation/infrastructure/dfg/constant/lattice.py` - ConstantLattice (321 LOC)

**알고리즘**: 3-level lattice (⊤ → Constant → ⊥)

---

### 17. Program Slicing (PDG-based)
**핵심 파일**:
- `reasoning_engine/infrastructure/slicer/slicer.py` - ProgramSlicer (766 LOC)
- `reasoning_engine/infrastructure/pdg/pdg_builder.py` - PDGBuilder (167 LOC)

**Slicing 타입**: Backward / Forward / Hybrid / Interprocedural

---

### 18. Alias Analyzer
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/alias_analyzer.py` - AliasAnalyzer (338 LOC)

**분석**: Must-alias / May-alias 추적

---

### 19. Path-sensitive Taint Analyzer
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/path_sensitive_taint.py` - PathSensitiveTaintAnalyzer (1,018 LOC)

---

### 20. Field-sensitive Taint Analyzer
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/field_sensitive_taint.py` - FieldSensitiveTaintAnalyzer (588 LOC)

---

### 21. Separation Logic Analyzer (Heap Safety)
**핵심 파일**:
- `code_foundation/infrastructure/heap/sep_logic.py` - SeparationLogicAnalyzer (1,168 LOC)

**지원 언어**: C++/Rust, Java/Kotlin, TypeScript

---

### 22. Deep Security Analyzer
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/deep_security_analyzer.py` - DeepSecurityAnalyzer (1,010 LOC)

**Scan Modes**: Quick / Realtime / Deep / Audit

---

### 23. Impact Analyzer
**핵심 파일**:
- `reasoning_engine/infrastructure/impact/impact_analyzer.py` - ImpactAnalyzer (430 LOC)

---

### 24. Type Inference System
**핵심 파일**:
- `code_foundation/infrastructure/type_inference/bidirectional.py` - BidirectionalInference (164 LOC)
- `code_foundation/infrastructure/type_inference/local_flow_inferencer.py` - LocalFlowTypeInferencer (350 LOC)

---

### 25. Query Engine
**핵심 파일**:
- `code_foundation/infrastructure/query/query_engine.py` - QueryEngine (645 LOC)
- `code_foundation/infrastructure/query/traversal_engine.py` - TraversalEngine (400 LOC)

---

### 26. Cross-Language Value Flow Graph
**핵심 파일**:
- `reasoning_engine/infrastructure/cross_lang/value_flow_builder.py` - ValueFlowBuilder (450 LOC)

**통합**: OpenAPI/Swagger, Protobuf, GraphQL

---

### 27. CostAnalyzer (복잡도 분석)
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/cost/cost_analyzer.py` - CostAnalyzer (515 LOC)
- `code_foundation/infrastructure/analyzers/cost/complexity_calculator.py` - ComplexityCalculator (225 LOC)

**분류**: O(1), O(n), O(n²), O(n³), O(2^n)

---

### 28. DifferentialAnalyzer (PR Diff 분석)
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/differential/differential_analyzer.py` - DifferentialAnalyzer (540 LOC)

---

### 29. CodeRefactorer (리팩토링 엔진)
**핵심 파일**:
- `code_foundation/infrastructure/codegen/refactorer.py` - CodeRefactorer (75 LOC)

---

### 30. CodeObfuscator (코드 난독화)
**핵심 파일**:
- `code_foundation/infrastructure/codegen/obfuscator.py` - CodeObfuscator (110 LOC)

---

### 31. SemanticPatchEngine (시맨틱 패치)
**핵심 파일**:
- `reasoning_engine/infrastructure/patch/semantic_patch_engine.py` - SemanticPatchEngine (280 LOC)

---

### 32. ProvenanceBuilder (출처 추적)
**핵심 파일**:
- `code_foundation/infrastructure/provenance/builder.py` - ProvenanceBuilder (215 LOC)

---

### 33. TierPlanner (분석 계층 플래너)
**핵심 파일**:
- `code_foundation/infrastructure/tier_planning/planner.py` - TierPlanner (260 LOC)

---

### 34. SymbolGraphBuilder (심볼 그래프 빌드)
**핵심 파일**:
- `code_foundation/infrastructure/symbol_graph/builder.py` - SymbolGraphBuilder (190 LOC)

---

### 35. OccurrenceGenerator (SCIP 스타일 Occurrence)
**핵심 파일**:
- `code_foundation/infrastructure/ir/occurrence_generator.py` - OccurrenceGenerator (512 LOC)

---

### 36. PackageAnalyzer (패키지 분석)
**핵심 파일**:
- `code_foundation/infrastructure/ir/package_analyzer.py` - PackageAnalyzer (259 LOC)

**지원**: requirements.txt, pyproject.toml, package.json, go.mod

---

### 37. SearchFusion (다중 인덱스 검색 통합)
**핵심 파일**:
- `multi_index/infrastructure/service/search_fusion.py` - SearchFusion (228 LOC)

---

### 38. ConsistencyChecker (인덱스 일관성 검사)
**핵심 파일**:
- `multi_index/infrastructure/service/consistency_checker.py` - ConsistencyChecker (339 LOC)

---

### 39. BatchLSPFetcher (배치 LSP 호출)
**핵심 파일**:
- `code_foundation/infrastructure/ir/external_analyzers/batch_lsp_fetcher.py` - BatchLSPFetcher (327 LOC)

---

### 40. CorrelationIndex (상관관계 인덱스)
**핵심 파일**:
- `multi_index/infrastructure/correlation/adapter_postgres.py` - CorrelationIndex (468 LOC)

---

### 41. HierarchicalSummarizer (계층적 요약)
**핵심 파일**:
- `repo_structure/infrastructure/summarizer/hierarchical_summarizer.py` - HierarchicalSummarizer (437 LOC)

---

### 42. RepoMapTreeBuilder (레포맵 트리)
**핵심 파일**:
- `repo_structure/infrastructure/tree/builder.py` - RepoMapTreeBuilder (395 LOC)

---

### 43. DocumentScorer (문서 점수)
**핵심 파일**:
- `code_foundation/infrastructure/document/scoring.py` - DocumentScorer (305 LOC)

---

### 44. DriftDetector (드리프트 탐지)
**핵심 파일**:
- `code_foundation/infrastructure/document/scoring.py` - DriftDetector

---

### 45. PreciseCallGraphBuilder (정밀 콜그래프)
**핵심 파일**:
- `code_foundation/infrastructure/graphs/precise_call_graph.py` - PreciseCallGraphBuilder (220 LOC)

---

### 46. ContextSensitiveAnalyzer (컨텍스트 민감 분석)
**핵심 파일**:
- `code_foundation/infrastructure/graphs/context_sensitive_analyzer.py` - ContextSensitiveAnalyzer (325 LOC)

---

### 47. ArgumentValueTracker (인자 값 추적)
**핵심 파일**:
- `code_foundation/infrastructure/graphs/value_tracker.py` - ArgumentValueTracker (175 LOC)

---

### 48. Git History Analysis
**핵심 파일**:
- `analysis_indexing/infrastructure/git_history/churn.py` - ChurnAnalyzer
- `analysis_indexing/infrastructure/git_history/blame.py` - GitBlameAnalyzer
- `analysis_indexing/infrastructure/git_history/cochange.py` - CoChangeAnalyzer
- `analysis_indexing/infrastructure/git_history/evolution.py` - EvolutionTracker

---

### 49. ImportResolver
**핵심 파일**:
- `code_foundation/infrastructure/import_resolver.py` - ImportResolver

---

### 50. LocalOverlay (로컬 변경 오버레이)
**핵심 파일**:
- `code_foundation/infrastructure/overlay/local_overlay.py` - LocalOverlay, OverlayIRBuilder

---

## 🟢 소분류 (Small) - 보조 기능 [45개]

### 51. Z3 Path Verifier (SMT Solver)
**핵심 파일**:
- `code_foundation/infrastructure/smt/z3_solver.py` - Z3PathVerifier (175 LOC)

---

### 52. Null Dereference Checker
**핵심 파일**:
- `code_foundation/infrastructure/heap/null_checker.py` - NullDereferenceChecker (254 LOC)

---

### 53. Ownership Checker (Rust-style)
**핵심 파일**:
- `code_foundation/infrastructure/heap/ownership_checker.py` - OwnershipChecker (408 LOC)

---

### 54. CHA Call Graph Builder
**핵심 파일**:
- `code_foundation/infrastructure/heap/cha_call_graph.py` - CallGraphBuilder (294 LOC)

---

### 55. Semantic Differ
**핵심 파일**:
- `reasoning_engine/infrastructure/semantic_diff/semantic_differ.py` - SemanticDiffer (192 LOC)

---

### 56. Graph Simulator (Speculative Analysis)
**핵심 파일**:
- `reasoning_engine/infrastructure/speculative/graph_simulator.py` - GraphSimulator (380 LOC)

---

### 57. Async Race Detector
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/concurrency/race_detector.py` - AsyncRaceDetector (280 LOC)

---

### 58. Type Narrowing Analyzer
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/type_narrowing_full.py` - FullTypeNarrowingAnalyzer (320 LOC)

---

### 59. Language Plugin Registry
**핵심 파일**:
- `code_foundation/infrastructure/language_plugin/registry.py` - LanguagePluginRegistry (256 LOC)

---

### 60. Incremental IR Builder
**핵심 파일**:
- `code_foundation/infrastructure/incremental/incremental_builder.py` - IncrementalIRBuilder (268 LOC)
- `code_foundation/infrastructure/incremental/change_tracker.py` - ChangeTracker (152 LOC)

---

### 61. PageRank Engine
**핵심 파일**:
- `repo_structure/infrastructure/pagerank/engine.py` - PageRankEngine (199 LOC)

---

### 62. Cross-file Resolver
**핵심 파일**:
- `code_foundation/infrastructure/ir/cross_file_resolver.py` - CrossFileResolver (270 LOC)

---

### 63. Function Summary Cache
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/function_summary.py`

---

### 64. Lightweight Bi-abduction
**핵심 파일**:
- `code_foundation/infrastructure/heap/lightweight_biabduction.py` - LightweightBiabduction (313 LOC)

---

### 65. PythonRoleDetector (역할 탐지)
**핵심 파일**:
- `code_foundation/infrastructure/role_detection/python_detector.py` - PythonRoleDetector (315 LOC)

---

### 66. RegionSegmenter (시맨틱 영역 분할)
**핵심 파일**:
- `code_foundation/infrastructure/semantic_regions/segmenter.py` - RegionSegmenter (280 LOC)

---

### 67. FormatStringDetector (포맷 스트링 취약점)
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/patterns/format_string.py`

---

### 68. SearchIndexBuilder (검색 인덱스 빌드)
**핵심 파일**:
- `code_foundation/infrastructure/search_index/builder.py` - SearchIndexBuilder (395 LOC)

---

### 69. LayeredIRBuilder (레거시)
**핵심 파일**:
- `code_foundation/infrastructure/ir/layered_ir_builder.py` - LayeredIRBuilder (3,124 LOC)

> ⚠️ **Deprecated**: Pipeline v3로 대체됨

---

### 70. UseAfterFreeChecker (UAF 검사)
**핵심 파일**:
- `code_foundation/infrastructure/heap/uaf_checker.py` - UseAfterFreeChecker (323 LOC)

---

### 71. TypeStateRegistry (타입 상태 레지스트리)
**핵심 파일**:
- `code_foundation/infrastructure/heap/type_state.py` - TypeStateRegistry (109 LOC)

---

### 72. SymbolicExecutor (심볼릭 실행)
**핵심 파일**:
- `code_foundation/infrastructure/heap/symbolic_heap.py` - SymbolicExecutor (330 LOC)

---

### 73. SMTPathVerifier (Heap)
**핵심 파일**:
- `code_foundation/infrastructure/heap/smt_path_verifier.py` - SMTPathVerifier (190 LOC)

---

### 74. HeapAwareAnalyzer
**핵심 파일**:
- `code_foundation/infrastructure/heap/heap_aware_analyzer.py` - HeapAwareAnalyzer

---

### 75. PyrightAdapter (Python LSP)
**핵심 파일**:
- `code_foundation/infrastructure/ir/lsp/pyright.py` - PyrightAdapter

---

### 76. TypeScriptLSP
**핵심 파일**:
- `code_foundation/infrastructure/ir/lsp/typescript.py`

---

### 77. GoPlsAdapter (Go LSP)
**핵심 파일**:
- `code_foundation/infrastructure/ir/lsp/gopls.py`

---

### 78. RustAnalyzerAdapter (Rust LSP)
**핵심 파일**:
- `code_foundation/infrastructure/ir/lsp/rust_analyzer.py`

---

### 79. JdtlsAdapter (Java LSP)
**핵심 파일**:
- `code_foundation/infrastructure/ir/lsp/jdtls.py`
- `code_foundation/infrastructure/ir/lsp/jdtls_client.py`

---

### 80. KotlinLSP
**핵심 파일**:
- `code_foundation/infrastructure/ir/lsp/kotlin.py`

---

### 81. PriorityMemoryCache
**핵심 파일**:
- `code_foundation/infrastructure/ir/cache/priority_cache.py` - PriorityMemoryCache

---

### 82. HealthChecker (시스템 헬스체크)
**핵심 파일**:
- `multi_index/infrastructure/health/health_check.py` - HealthChecker

---

### 83-88. Indexing Pipeline Stages
**핵심 파일**:
- `analysis_indexing/infrastructure/stages/discovery_stage.py`
- `analysis_indexing/infrastructure/stages/parsing_stage.py`
- `analysis_indexing/infrastructure/stages/ir_stage.py`
- `analysis_indexing/infrastructure/stages/graph_stage.py`
- `analysis_indexing/infrastructure/stages/chunk_stage.py`
- `analysis_indexing/infrastructure/stages/indexing_stage.py`

---

### 89. IRDocumentStore
**핵심 파일**:
- `code_foundation/infrastructure/storage/ir_document_store.py` - IRDocumentStore

---

### 90. WriteAheadLog (WAL)
**핵심 파일**:
- `reasoning_engine/infrastructure/storage/wal.py` - WriteAheadLog

---

### 91. CrashRecoveryManager
**핵심 파일**:
- `reasoning_engine/infrastructure/storage/crash_recovery.py` - CrashRecoveryManager

---

### 92. CacheMetrics (Prometheus)
**핵심 파일**:
- `code_foundation/infrastructure/monitoring/cache_metrics.py`

---

### 93. FQNResolver
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/fqn_resolver.py` - FQNResolver

---

### 94. SourceRegistry V2
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/source_registry_v2.py` - SourceRegistryV2

---

### 95. Taint Rules (Sources/Sinks)
**핵심 파일**:
- `code_foundation/infrastructure/analyzers/taint_rules/base.py`
- `code_foundation/infrastructure/analyzers/taint_rules/sources/python_core.py`
- `code_foundation/infrastructure/analyzers/taint_rules/sinks/python_core.py`

---

## 🦀 Rust 전환 우선순위

### 🔴 최고 우선순위 (Phase 1) - 2주
| # | 기능 | LOC | 예상 향상 | 복잡도 |
|---|-----|-----|----------|-------|
| 1 | SCCP Solver | 740 | 15-30x | ⭐⭐⭐ |
| 2 | PageRankEngine | 190 | 10-30x | ⭐⭐ |
| 3 | OccurrenceGenerator | 512 | 10-20x | ⭐⭐⭐ |
| 4 | CostAnalyzer | 740 | 10-20x | ⭐⭐ |

### 🟡 높은 우선순위 (Phase 2) - 4주
| # | 기능 | LOC | 예상 향상 | 복잡도 |
|---|-----|-----|----------|-------|
| 5 | GraphBuilder | 910 | 10-20x | ⭐⭐⭐ |
| 6 | UnifiedAnalyzer | 946 | 10-30x | ⭐⭐⭐⭐ |
| 7 | DependencyAnalyzer | 730 | 10-30x | ⭐⭐⭐ |
| 8 | SearchFusion | 228 | 5-10x | ⭐⭐ |
| 9 | CorrelationIndex | 468 | 5-15x | ⭐⭐⭐ |
| 10 | AliasAnalyzer | 338 | 15-30x | ⭐⭐⭐ |

### 🟢 중간 우선순위 (Phase 3) - 8주
| # | 기능 | LOC | 예상 향상 | 복잡도 |
|---|-----|-----|----------|-------|
| 11 | DocumentScorer | 535 | 5-10x | ⭐⭐ |
| 12 | RepoMapTreeBuilder | 395 | 5-10x | ⭐⭐ |
| 13 | SymbolicExecutor | 473 | 10-20x | ⭐⭐⭐⭐ |
| 14 | SMTPathVerifier | 232 | 5-10x | ⭐⭐⭐ |
| 15 | UseAfterFreeChecker | 323 | 10-20x | ⭐⭐⭐ |

---

## 🏗️ 아키텍처 다이어그램

```
┌─────────────────────────────────────────────────────────────────┐
│                    Codegraph Engine (95 기능)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  code_foundation (핵심 분석) - 65 기능                    │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ IR        │  │ Semantic  │  │ Analyzers     │       │   │
│  │  │ Pipeline  │→ │ IR        │→ │ (Taint/Cost/  │       │   │
│  │  │ v3        │  │ (CFG/BFG/ │  │  Security)    │       │   │
│  │  │ (11 stg)  │  │  DFG/SSA) │  │               │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ Chunk     │  │ Graph     │  │ Query         │       │   │
│  │  │ Builder   │  │ Builder   │  │ Engine        │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ Heap      │  │ Type      │  │ LSP Adapters  │       │   │
│  │  │ Analysis  │  │ Inference │  │ (6 languages) │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  reasoning_engine (고급 추론) - 15 기능                   │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ Slicer    │  │ Impact    │  │ Cross-lang    │       │   │
│  │  │ (PDG)     │  │ Analyzer  │  │ VFG           │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ Rust      │  │ Specul-   │  │ Semantic      │       │   │
│  │  │ Taint     │  │ ative     │  │ Patch         │       │   │
│  │  │ Engine    │  │ Analysis  │  │ Engine        │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  multi_index (다중 인덱스) - 10 기능                      │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ Qdrant    │  │ Tantivy   │  │ Symbol        │       │   │
│  │  │ Vector    │  │ Lexical   │  │ Embedding     │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ Search    │  │ Correla-  │  │ Consistency   │       │   │
│  │  │ Fusion    │  │ tion      │  │ Checker       │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  analysis_indexing (파이프라인) - 5 기능                  │   │
│  │                                                         │   │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────────┐       │   │
│  │  │ Orchestr- │  │ Git       │  │ Stages        │       │   │
│  │  │ ator      │  │ History   │  │ (9 stages)    │       │   │
│  │  └───────────┘  └───────────┘  └───────────────┘       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📈 지원 언어

| 언어 | Parsing | LSP | Type Inference | Taint |
|------|---------|-----|----------------|-------|
| Python | ✅ | ✅ Pyright | ✅ | ✅ |
| TypeScript/JS | ✅ | ✅ TSServer | ✅ | ✅ |
| Java | ✅ | ✅ JDT.LS | ✅ | ✅ |
| Kotlin | ✅ | ✅ KLS | ✅ | ✅ |
| Go | ✅ | ✅ Gopls | ✅ | ✅ |
| Rust | ✅ | ✅ rust-analyzer | ✅ | ✅ |

---

## 📊 성능 벤치마크

| 작업 | Python Only | With Rust | Speedup |
|------|-------------|-----------|---------|
| IR Generation | 8.8s | 0.166s | **53x** |
| Cross-file Resolution | 62s | 5s | **12x** |
| Taint Analysis | 60s | 3s | **20x** |
| SSA Construction | 5s | 0.5s | **10x** |

---

## 🔗 관련 문서

- [CLAUDE.md](./CLAUDE.md) - 개발 가이드
- [IR Pipeline README](./codegraph_engine/code_foundation/infrastructure/ir/pipeline/README.md)
- [SSA README](./codegraph_engine/code_foundation/infrastructure/dfg/ssa/README.md)
- [SCCP README](./codegraph_engine/code_foundation/infrastructure/dfg/constant/README.md)
- [Cross-lang VFG README](./codegraph_engine/reasoning_engine/infrastructure/cross_lang/README.md)

