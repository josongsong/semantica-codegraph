# RFC-063: ChunkBuilder Rust 최적화

**Status**: Draft  
**Author**: Semantica Team  
**Created**: 2024-12-26  
**Target**: Phase 3 최적화 (87s → ~15s)

---

## 1. Executive Summary

Phase 3 (Chunk Build)가 전체 인덱싱의 72%를 차지하는 최대 병목입니다.
ChunkBuilder를 Rust로 이전하여 **~80% 성능 향상**을 목표로 합니다.

```
현재 성능 (Python):
  Phase 3: 87초 / 전체 120초 = 72%
  처리량: 152 files/s

목표 성능 (Rust):
  Phase 3: ~15초 / 전체 ~48초 = 31%
  처리량: 880+ files/s
```

---

## 2. SOTA 시스템 비교 분석

### 2.1 업계 SOTA 청킹 시스템

| 시스템 | 언어 | 청킹 방식 | 특징 |
|--------|------|-----------|------|
| **Sourcegraph SCIP** | Rust/Go | AST + Semantic | SCIP 프로토콜, 심볼 기반 |
| **GitHub Code Search** | Rust | Tree-sitter + BM25 | 병렬 인덱싱, 스트리밍 |
| **Cursor** | TypeScript/Rust | Tree-sitter + LLM | RAG 최적화 청킹 |
| **Continue.dev** | TypeScript | Tree-sitter | Function/Class 단위 |
| **LlamaIndex** | Python | AST Splitter | Configurable boundaries |
| **Aider** | Python | Tree-sitter | Diff 기반 청킹 |

### 2.2 SOTA 청킹 핵심 기법

```
1. AST-Aware Chunking (필수)
   - Function/Class/Method 경계 존중
   - Nested structure 보존
   
2. Semantic Hierarchy (SOTA)
   - Repo → Project → Module → File → Class → Function
   - 6-level hierarchy로 컨텍스트 유지
   
3. Content-Addressable (고급)
   - SHA256/MD5 기반 중복 제거
   - Incremental update 지원
   
4. Parallel Processing (필수)
   - Rayon/Tokio 기반 병렬화
   - Lock-free data structures
   
5. Zero-Copy (고급)
   - Cow<str> 활용
   - Arena allocation
```

### 2.3 우리 시스템 vs SOTA

| 기능 | 우리 (현재) | SOTA | 상태 |
|------|-------------|------|------|
| AST-Aware Chunking | ✅ Tree-sitter + IR | ✅ | 동등 |
| 6-Level Hierarchy | ✅ Repo→Function | ✅ | SOTA급 |
| Content Hash | ✅ MD5 | SHA256 | 개선 가능 |
| Symbol Visibility | ✅ Public/Private | ✅ | 동등 |
| Test Detection | ✅ TestDetector | ✅ | 동등 |
| Docstring Chunking | ✅ 별도 청크 | ✅ | SOTA급 |
| Skeleton Generation | ✅ TypeStub | ✅ | SOTA급 |
| **구현 언어** | ❌ Python | Rust | **병목** |
| **병렬 처리** | ❌ Sequential | Rayon | **병목** |

**결론**: 기능적으로 SOTA급이나, 구현 언어(Python)가 병목

---

## 3. 최적화 전략

### 3.1 Phase 1: Core Types & Models (Week 1, Day 1-2)

```rust
// codegraph-ir/src/features/chunk/models.rs

use serde::{Deserialize, Serialize};
use std::borrow::Cow;

/// Chunk 종류 - 6-level hierarchy + semantic types
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "PascalCase")]
pub enum ChunkKind {
    // Hierarchy levels
    Repo,
    Project,
    Module,
    File,
    Class,
    Function,
    Method,
    
    // Semantic types
    Docstring,
    Skeleton,
    FileHeader,
    Import,
    Variable,
    Field,
    Block,
    Expression,
}

/// 코드 청크 - SOTA급 메타데이터 포함
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Chunk {
    pub chunk_id: String,
    pub repo_id: String,
    pub snapshot_id: String,
    pub kind: ChunkKind,
    
    // Location
    pub file_path: String,
    pub start_line: u32,
    pub end_line: u32,
    
    // Identity
    pub fqn: String,
    pub content_hash: Option<String>,
    
    // Hierarchy
    pub parent_id: Option<String>,
    
    // Attributes (flexible metadata)
    pub attrs: ChunkAttrs,
}

/// 청크 속성 - 확장 가능한 메타데이터
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ChunkAttrs {
    pub visibility: Option<String>,      // public, private, protected
    pub decorators: Vec<String>,         // @staticmethod, @property
    pub is_test: bool,                   // 테스트 파일/함수 여부
    pub docstring_length: Option<u32>,   // 문서화 수준
    pub complexity: Option<u32>,         // 순환 복잡도
    pub language: Option<String>,        // python, javascript
}

/// IR → Chunk 매핑 결과
#[derive(Debug, Clone, Default)]
pub struct ChunkToIR {
    pub mappings: Vec<(String, String)>,  // (chunk_id, node_id)
}

/// Chunk → Graph 매핑 결과  
#[derive(Debug, Clone, Default)]
pub struct ChunkToGraph {
    pub mappings: Vec<(String, String)>,  // (chunk_id, graph_node_id)
}
```

### 3.2 Phase 2: ChunkIdGenerator (Week 1, Day 3)

```rust
// codegraph-ir/src/features/chunk/id_generator.rs

use sha2::{Sha256, Digest};
use std::sync::atomic::{AtomicU64, Ordering};

/// ID 생성 컨텍스트
pub struct ChunkIdContext {
    pub repo_id: String,
    pub snapshot_id: String,
    pub file_path: String,
    counter: AtomicU64,
}

impl ChunkIdContext {
    pub fn new(repo_id: &str, snapshot_id: &str, file_path: &str) -> Self {
        Self {
            repo_id: repo_id.to_string(),
            snapshot_id: snapshot_id.to_string(),
            file_path: file_path.to_string(),
            counter: AtomicU64::new(0),
        }
    }
    
    /// 고유 청크 ID 생성 (deterministic)
    pub fn generate_id(&self, kind: ChunkKind, fqn: &str) -> String {
        let seq = self.counter.fetch_add(1, Ordering::SeqCst);
        
        // Deterministic ID: repo:snapshot:file:kind:fqn:seq
        let input = format!(
            "{}:{}:{}:{:?}:{}:{}",
            self.repo_id, self.snapshot_id, self.file_path, kind, fqn, seq
        );
        
        let mut hasher = Sha256::new();
        hasher.update(input.as_bytes());
        let result = hasher.finalize();
        
        // First 16 bytes as hex = 32 chars
        hex::encode(&result[..16])
    }
}

/// Content-addressable hash 생성
pub fn compute_content_hash(content: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(content.as_bytes());
    hex::encode(hasher.finalize())
}
```

### 3.3 Phase 3: ChunkBuilder Core (Week 1, Day 4-5)

```rust
// codegraph-ir/src/features/chunk/builder.rs

use rayon::prelude::*;
use dashmap::DashMap;
use crate::shared::models::{IRDocument, Node, NodeKind};

pub struct ChunkBuilder {
    config: ChunkBuilderConfig,
}

pub struct ChunkBuilderConfig {
    pub min_chunk_lines: u32,      // 최소 청크 크기 (기본: 1)
    pub max_chunk_lines: u32,      // 최대 청크 크기 (기본: 500)
    pub include_docstrings: bool,  // 독스트링 별도 청크화
    pub include_skeletons: bool,   // 타입 스켈레톤 생성
    pub compute_complexity: bool,  // 복잡도 계산
}

impl Default for ChunkBuilderConfig {
    fn default() -> Self {
        Self {
            min_chunk_lines: 1,
            max_chunk_lines: 500,
            include_docstrings: true,
            include_skeletons: true,
            compute_complexity: true,
        }
    }
}

impl ChunkBuilder {
    pub fn new(config: ChunkBuilderConfig) -> Self {
        Self { config }
    }
    
    /// IR 문서에서 청크 생성 (병렬)
    pub fn build_from_ir(
        &self,
        repo_id: &str,
        snapshot_id: &str,
        ir_doc: &IRDocument,
        file_content: &str,
    ) -> ChunkBuildResult {
        let ctx = ChunkIdContext::new(repo_id, snapshot_id, &ir_doc.file_path);
        let lines: Vec<&str> = file_content.lines().collect();
        
        // Phase 1: Build hierarchy chunks (Repo → Project → Module → File)
        let mut chunks = self.build_hierarchy_chunks(&ctx, ir_doc, &lines);
        
        // Phase 2: Build code chunks (parallel over nodes)
        let code_chunks: Vec<Chunk> = ir_doc.nodes
            .par_iter()
            .filter_map(|node| self.build_node_chunk(&ctx, node, &lines))
            .collect();
        
        chunks.extend(code_chunks);
        
        // Phase 3: Build docstring chunks (parallel)
        if self.config.include_docstrings {
            let doc_chunks: Vec<Chunk> = ir_doc.nodes
                .par_iter()
                .filter_map(|node| self.build_docstring_chunk(&ctx, node, &lines))
                .collect();
            chunks.extend(doc_chunks);
        }
        
        // Phase 4: Build skeleton chunks
        if self.config.include_skeletons {
            let skeleton_chunks: Vec<Chunk> = ir_doc.nodes
                .par_iter()
                .filter(|n| matches!(n.kind, NodeKind::Class | NodeKind::Function | NodeKind::Method))
                .map(|node| self.build_skeleton_chunk(&ctx, node, &lines))
                .collect();
            chunks.extend(skeleton_chunks);
        }
        
        // Build mappings
        let chunk_to_ir = self.build_ir_mapping(&chunks, ir_doc);
        
        ChunkBuildResult {
            chunks,
            chunk_to_ir,
            chunk_to_graph: ChunkToGraph::default(),
        }
    }
    
    fn build_node_chunk(
        &self,
        ctx: &ChunkIdContext,
        node: &Node,
        lines: &[&str],
    ) -> Option<Chunk> {
        // Skip non-chunkable nodes
        let kind = match node.kind {
            NodeKind::Class => ChunkKind::Class,
            NodeKind::Function => ChunkKind::Function,
            NodeKind::Method => ChunkKind::Method,
            NodeKind::Module => ChunkKind::Module,
            NodeKind::File => ChunkKind::File,
            NodeKind::Variable => ChunkKind::Variable,
            NodeKind::Field => ChunkKind::Field,
            _ => return None,
        };
        
        let start = node.span.start_line as usize;
        let end = node.span.end_line as usize;
        
        // Validate bounds
        if start >= lines.len() || end > lines.len() || start > end {
            return None;
        }
        
        // Extract content
        let content: String = lines[start..end].join("\n");
        
        // Compute content hash
        let content_hash = compute_content_hash(&content);
        
        Some(Chunk {
            chunk_id: ctx.generate_id(kind, &node.fqn),
            repo_id: ctx.repo_id.clone(),
            snapshot_id: ctx.snapshot_id.clone(),
            kind,
            file_path: ctx.file_path.clone(),
            start_line: node.span.start_line,
            end_line: node.span.end_line,
            fqn: node.fqn.clone(),
            content_hash: Some(content_hash),
            parent_id: node.parent_id.clone(),
            attrs: self.extract_attrs(node),
        })
    }
    
    fn extract_attrs(&self, node: &Node) -> ChunkAttrs {
        ChunkAttrs {
            visibility: node.attrs.get("visibility").map(|v| v.to_string()),
            decorators: node.attrs.get("decorators")
                .and_then(|v| v.as_array())
                .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
                .unwrap_or_default(),
            is_test: node.attrs.get("is_test")
                .and_then(|v| v.as_bool())
                .unwrap_or(false),
            docstring_length: node.attrs.get("docstring")
                .and_then(|v| v.as_str())
                .map(|s| s.len() as u32),
            complexity: if self.config.compute_complexity {
                node.attrs.get("cyclomatic_complexity")
                    .and_then(|v| v.as_u64())
                    .map(|v| v as u32)
            } else {
                None
            },
            language: Some("python".to_string()),
        }
    }
}
```

### 3.4 Phase 4: PyO3 Bindings (Week 2, Day 1-2)

```rust
// codegraph-ir/src/lib.rs (추가)

/// Python에서 호출 가능한 청크 빌드 함수
#[pyfunction]
#[pyo3(signature = (repo_id, snapshot_id, ir_docs, file_contents))]
fn build_chunks_py(
    py: Python,
    repo_id: &str,
    snapshot_id: &str,
    ir_docs: &PyList,
    file_contents: &PyDict,
) -> PyResult<Py<PyList>> {
    init_rayon();
    
    // Convert Python IR docs to Rust
    let rust_irs: Vec<IRDocument> = ir_docs
        .iter()
        .filter_map(|doc| IRDocument::from_py_dict(doc.downcast::<PyDict>().ok()?).ok())
        .collect();
    
    // Convert file contents
    let contents: HashMap<String, String> = file_contents
        .iter()
        .filter_map(|(k, v)| {
            Some((k.extract::<String>().ok()?, v.extract::<String>().ok()?))
        })
        .collect();
    
    // Build chunks (releases GIL for parallel processing)
    let builder = ChunkBuilder::new(ChunkBuilderConfig::default());
    
    let all_chunks: Vec<Vec<Chunk>> = py.allow_threads(|| {
        rust_irs
            .par_iter()
            .filter_map(|ir| {
                let content = contents.get(&ir.file_path)?;
                Some(builder.build_from_ir(repo_id, snapshot_id, ir, content).chunks)
            })
            .collect()
    });
    
    // Flatten and convert to Python
    let flat_chunks: Vec<Chunk> = all_chunks.into_iter().flatten().collect();
    
    // Convert to Python list
    let py_list = PyList::empty(py);
    for chunk in flat_chunks {
        py_list.append(chunk.to_py_dict(py)?)?;
    }
    
    Ok(py_list.into())
}
```

### 3.5 Phase 5: Integration & Benchmarking (Week 2, Day 3-5)

```python
# packages/codegraph-shared/.../handlers/chunk_handler.py

class ChunkBuildHandler(BaseJobHandler):
    async def execute(self, job: Job) -> JobResult:
        ir_docs = await self._load_ir_docs(job.ir_cache_key)
        file_contents = await self._load_file_contents(ir_docs)
        
        # 🚀 Rust 직접 호출!
        try:
            import codegraph_ir
            
            chunks = codegraph_ir.build_chunks_py(
                repo_id=job.repo_id,
                snapshot_id=job.snapshot_id,
                ir_docs=[doc.to_dict() for doc in ir_docs.values()],
                file_contents=file_contents,
            )
            
            logger.info("rust_chunk_build_success", count=len(chunks))
            
        except ImportError:
            # Fallback to Python
            logger.warning("rust_unavailable_fallback_python")
            builder = ChunkBuilder(ChunkIdGenerator())
            chunks = self._build_with_python(builder, ir_docs, file_contents)
        
        return JobResult(
            success=True,
            data={"chunks": chunks, "count": len(chunks)},
        )
```

---

## 4. 레포지토리 구조

### 4.1 새로 추가될 Rust 파일

```
codegraph-rust/codegraph-ir/src/features/
├── chunk/                        # 🆕 새 모듈
│   ├── mod.rs                   # 모듈 선언
│   ├── models.rs                # Chunk, ChunkKind, ChunkAttrs
│   ├── builder.rs               # ChunkBuilder 핵심
│   ├── id_generator.rs          # ChunkIdContext, ID 생성
│   ├── hierarchy.rs             # Repo→File 계층 빌드
│   ├── docstring.rs             # Docstring 청크 생성
│   ├── skeleton.rs              # Type skeleton 생성
│   ├── visibility.rs            # Public/Private 추출
│   └── test_detector.rs         # 테스트 파일 감지
├── cross_file/                  # ✅ 기존
├── data_flow/                   # ✅ 기존
├── flow_graph/                  # ✅ 기존
├── ir_generation/               # ✅ 기존
├── parsing/                     # ✅ 기존
├── pdg/                         # ✅ 기존
├── slicing/                     # ✅ 기존
├── ssa/                         # ✅ 기존
├── taint_analysis/              # ✅ 기존
├── type_resolution/             # ✅ 기존
└── mod.rs                       # chunk 추가
```

### 4.2 수정될 Python 파일

```
packages/codegraph-shared/.../handlers/
├── chunk_handler.py             # 🔄 Rust 호출로 변경
└── __init__.py                  # 🔄 export 추가

packages/codegraph-engine/.../chunk/
├── builder.py                   # 🔄 Rust fallback 추가
└── models.py                    # ✅ 유지 (Python 인터페이스)
```

### 4.3 전체 레포 구조 (최종)

```
codegraph/
├── packages/
│   ├── codegraph-rust/
│   │   ├── codegraph-ir/
│   │   │   ├── src/
│   │   │   │   ├── features/
│   │   │   │   │   ├── chunk/          # 🆕 Week 1-2
│   │   │   │   │   ├── cross_file/     # ✅ 완료
│   │   │   │   │   ├── ir_generation/  # ✅ 완료
│   │   │   │   │   ├── parsing/        # ✅ 완료
│   │   │   │   │   └── ...
│   │   │   │   ├── lib.rs              # 🔄 build_chunks_py 추가
│   │   │   │   └── ...
│   │   │   └── Cargo.toml
│   │   └── codegraph-core/
│   │       └── src/
│   │           └── types.rs            # ✅ NodeKind 동기화됨
│   │
│   ├── codegraph-engine/
│   │   └── codegraph_engine/
│   │       └── code_foundation/
│   │           └── infrastructure/
│   │               └── chunk/
│   │                   ├── builder.py   # 🔄 Rust fallback
│   │                   └── models.py    # ✅ 유지
│   │
│   └── codegraph-shared/
│       └── codegraph_shared/
│           └── infra/
│               └── jobs/
│                   └── handlers/
│                       └── chunk_handler.py  # 🔄 Rust 호출
│
├── docs/
│   └── rfcs/
│       └── RFC-063-ChunkBuilder-Rust-Optimization.md  # 🆕 본 문서
│
└── tools/
    └── benchmark/
        └── bench_indexing_dag.py  # 🔄 성능 측정
```

---

## 5. 성능 목표 및 측정

### 5.1 벤치마크 대상

| 규모 | 파일 수 | LOC | 현재 (Python) | 목표 (Rust) |
|------|---------|-----|---------------|-------------|
| Small | 100 | 10K | 0.6s | <0.1s |
| Medium | 1,000 | 100K | 6s | <1s |
| Large | 10,000 | 1M | 60s | <10s |
| **XL (codegraph)** | **13,217** | **1.95M** | **87s** | **<15s** |

### 5.2 성능 검증 스크립트

```bash
# 벤치마크 실행
python tools/benchmark/bench_indexing_dag.py \
    /Users/songmin/Documents/code-jo/semantica-v2/codegraph \
    --output benchmark/artifacts/reports/chunk_rust_benchmark.txt

# 기대 결과
# Phase 3 (Chunk): 87s → ~15s (5.8x faster)
# 전체: 120s → ~48s (2.5x faster)
```

---

## 6. 타임라인

### Week 1: Core Implementation

| Day | Task | Deliverable | Hours |
|-----|------|-------------|-------|
| 1 | Models 정의 | `models.rs` | 4h |
| 2 | ID Generator | `id_generator.rs` | 3h |
| 3 | Hierarchy Builder | `hierarchy.rs` | 4h |
| 4 | Node Chunk Builder | `builder.rs` (core) | 6h |
| 5 | Docstring/Skeleton | `docstring.rs`, `skeleton.rs` | 4h |

### Week 2: Integration & Testing

| Day | Task | Deliverable | Hours |
|-----|------|-------------|-------|
| 1 | PyO3 Bindings | `lib.rs` 확장 | 4h |
| 2 | Python Handler | `chunk_handler.py` | 3h |
| 3 | Unit Tests | `tests/chunk/` | 4h |
| 4 | Integration Tests | `tests/integration/` | 4h |
| 5 | Benchmark & Docs | Reports, RFC 업데이트 | 4h |

**총 예상 시간: 40시간 (2주)**

---

## 7. 리스크 및 대응

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| PyO3 데이터 변환 오버헤드 | 중 | 중 | Msgpack 바이너리 직렬화 |
| Python fallback 호환성 | 낮 | 낮 | 기존 Python 코드 유지 |
| 청크 ID 불일치 | 중 | 높 | 동일 알고리즘 적용 |
| 복잡도 계산 차이 | 낮 | 낮 | Python 로직 포팅 |

---

## 8. 결론

### SOTA 검증 결과

| 기준 | 상태 |
|------|------|
| AST-Aware Chunking | ✅ SOTA급 |
| 6-Level Hierarchy | ✅ SOTA급 |
| Content-Addressable | ✅ SOTA급 |
| Parallel Processing | ⏳ 구현 필요 |
| Zero-Copy | ⏳ 구현 필요 |

**결론**: 기능적으로 SOTA급이며, Rust 이전으로 성능도 SOTA급 달성 가능

### 예상 ROI

```
투자: 40시간 (2주)
효과: Phase 3 87s → 15s (5.8x)
      전체 120s → 48s (2.5x)
      
대규모 프로젝트:
  - 100만 LOC: 1분 → 24초
  - 500만 LOC: 5분 → 2분
```

---

## Appendix A: 의존성

```toml
# Cargo.toml 추가
[dependencies]
sha2 = "0.10"          # Content hash
hex = "0.4"            # Hex encoding
rayon = "1.8"          # Parallel iteration
dashmap = "5.5"        # Concurrent HashMap
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
```

---

## Appendix B: 참고 자료

1. Sourcegraph SCIP Protocol: https://github.com/sourcegraph/scip
2. Tree-sitter: https://tree-sitter.github.io/tree-sitter/
3. LlamaIndex CodeSplitter: https://docs.llamaindex.ai/en/stable/module_guides/loading/node_parsers/modules/code_splitter/
4. Cursor Technical Blog: https://cursor.sh/blog
5. Rayon Data Parallelism: https://docs.rs/rayon/latest/rayon/

