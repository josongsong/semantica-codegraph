# Semantica CodeGraph v4 - 구현 로드맵

**작성일**: 2024-11-24
**전체 진행도**: 97%

---

## 📊 전체 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent Layer (계획)                       │
│           LangGraph 기반 코드 에이전트                        │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                  Application Layers                          │
├──────────────────────────────────────────────────────────────┤
│  Server Layer (✅)   │  API Server, MCP Server               │
│  Retriever Layer (✅) │  Multi-index Search, Fusion           │
│  Index Layer (✅ 98%) │  Lexical, Vector, Symbol, Fuzzy      │
│  RepoMap Layer (✅)   │  PageRank, Summary, Storage           │
│  Chunk Layer (✅)     │  6-tier Hierarchy, Incremental        │
└──────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│                  Foundation Layer (✅)                        │
├──────────────────────────────────────────────────────────────┤
│  Graph Layer        │  Kuzu-based GraphDocument              │
│  Semantic IR        │  CFG, DFG, Type/Signature              │
│  IR Layer           │  Language-neutral IR v4                │
│  Parsing Layer      │  Tree-sitter based AST                 │
└──────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────┴───────────────────────────────────────┐
│              Infrastructure Layer (✅)                        │
├──────────────────────────────────────────────────────────────┤
│  Storage    │ PostgreSQL, Redis, Kuzu                        │
│  Search     │ Zoekt, Qdrant                                  │
│  LLM        │ OpenAI, LiteLLM                                │
│  Git        │ GitPython                                      │
└──────────────────────────────────────────────────────────────┘
```

---

## ✅ 현재 구현 완료 (97%)

### 1. Foundation Layer (100%)

#### 1.1 Parsing Layer
**위치**: `src/foundation/parsing/`

**구현 완료**:
- ✅ `parser_registry.py` - Tree-sitter 파서 레지스트리
  - 지원 언어: Python, TypeScript, JavaScript, Go, Java, Rust, C, C++
  - 파일 확장자 기반 자동 언어 감지
  - 싱글톤 패턴으로 파서 캐싱

- ✅ `source_file.py` - 소스 파일 추상화
  - 파일 로딩 (디스크/문자열)
  - 라인 기반 텍스트 추출
  - 좌표 기반 범위 추출 (`get_text(start_line, start_col, end_line, end_col)`)

- ✅ `ast_tree.py` - AST 트리 래퍼
  - Tree-sitter 노드 순회 (`walk()`, `find_by_type()`)
  - 에러 노드 감지
  - 증분 파싱 지원 (`parse_incremental()`)

**핵심 알고리즘**:
```python
# 파서 선택 알고리즘
def detect_language(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext, "unknown")

# AST 순회 알고리즘 (DFS)
def walk(node: Node) -> Iterator[Node]:
    yield node
    for child in node.children:
        yield from walk(child)
```

---

#### 1.2 IR Layer (Intermediate Representation)
**위치**: `src/foundation/ir/`

**구현 완료**:
- ✅ `models/core.py` - IR 핵심 모델
  - `IRNode`: File, Module, Class, Function, Variable, Import
  - `IRDocument`: 파일 단위 IR 컨테이너
  - 안정적인 ID 생성: `{lang}:{repo}:{kind}:{span_hash}`

- ✅ `generators/python_generator.py` - Python IR 생성기
  - AST → IRNode 변환
  - FQN (Fully Qualified Name) 생성
  - 스코프 추적 (module → class → function)
  - Import resolution
  - Call site 추출

- ✅ `generators/scope_stack.py` - 스코프 스택
  - 중첩 스코프 관리
  - 심볼 테이블 (per-scope symbol registry)
  - 섀도잉 처리

**핵심 알고리즘**:
```python
# FQN 생성 알고리즘
def build_fqn(scope_stack: ScopeStack, name: str) -> str:
    parts = []
    for frame in scope_stack.frames:
        if frame.kind in ("module", "class"):
            parts.append(frame.name)
    parts.append(name)
    return ".".join(parts)

# Call site 추출 알고리즘
def extract_calls(node: Node) -> list[CallSite]:
    calls = []
    for child in walk(node):
        if child.type == "call":
            callee = extract_callee_name(child)
            calls.append(CallSite(callee=callee, line=child.start_point[0]))
    return calls
```

**데이터 흐름**:
```
SourceFile → AstTree → PythonGenerator → IRDocument
                ↓
          ScopeStack (심볼 추적)
                ↓
          IRNode (FQN, Signature, Type)
```

---

#### 1.3 Semantic IR Layer (CFG, DFG, Type/Signature)
**위치**: `src/foundation/semantic_ir/`

**구현 완료**:
- ✅ `cfg/builder.py` - Control Flow Graph 생성
  - Basic block 추출
  - 조건 분기 (if/elif/else, match)
  - 루프 (for/while), 예외 처리 (try/except)
  - CFGBlock 노드, CFGEdge (NORMAL, BRANCH, LOOP_BACK, EXCEPTION)

- ✅ `dfg/builder.py` - Data Flow Graph 생성
  - 변수 읽기/쓰기 추적
  - Assignment, Use site 추출
  - SSA 준비 (향후 확장 가능)

- ✅ `typing/builder.py` - 타입 시스템
  - `TypeEntity`: primitive, builtin, user-defined, generic
  - 타입 해결 단계: raw → builtin → local → module → external
  - Generic 타입 분해 (List[T], Dict[K, V])

- ✅ `signature/builder.py` - 함수 시그니처
  - `SignatureEntity`: parameters, return_type, decorators
  - 가시성 (public, protected, private)
  - Async/static/classmethod 플래그

**핵심 알고리즘**:
```python
# CFG Basic Block 추출
def extract_basic_blocks(func_node: Node) -> list[CFGBlock]:
    blocks = []
    current_block = CFGBlock(kind=CFGBlockKind.ENTRY)

    for stmt in func_node.body:
        if is_branch(stmt):  # if, elif, else
            blocks.append(current_block)
            current_block = CFGBlock(kind=CFGBlockKind.CONDITION)
        elif is_loop(stmt):  # for, while
            blocks.append(current_block)
            current_block = CFGBlock(kind=CFGBlockKind.LOOP_HEADER)
        else:
            current_block.statements.append(stmt)

    blocks.append(current_block)
    return blocks

# DFG 변수 추적
def extract_variable_usage(stmt: Node) -> tuple[set[str], set[str]]:
    reads = set()  # 읽기
    writes = set()  # 쓰기

    if stmt.type == "assignment":
        writes.add(extract_target(stmt.left))
        reads.update(extract_names(stmt.right))
    elif stmt.type == "expression":
        reads.update(extract_names(stmt))

    return reads, writes
```

---

#### 1.4 Graph Layer (Kuzu-based)
**위치**: `src/foundation/graph/`

**구현 완료**:
- ✅ `models.py` - GraphDocument 모델
  - `GraphNode`: Symbol, Type, Signature 노드
  - `GraphEdge`: CONTAINS, CALLS, IMPORTS, READS, WRITES, REFERENCES_TYPE

- ✅ `builder.py` - Graph 생성기
  - IRDocument → GraphDocument 변환
  - External node 생성 (`external::{lang}::{symbol}`)
  - Edge 중복 제거, Normalization

- ✅ `src/foundation/storage/kuzu/store.py` - Kuzu 스토리지
  - Embedded Kuzu DB
  - Node/Edge 일괄 UPSERT
  - Cypher-style 쿼리 지원

**핵심 알고리즘**:
```python
# IRNode → GraphNode 승격
def promote_to_graph_node(ir_node: IRNode) -> GraphNode:
    return GraphNode(
        node_id=ir_node.node_id,
        kind="Symbol",
        properties={
            "name": ir_node.name,
            "fqn": ir_node.fqn,
            "kind": ir_node.kind,
            "visibility": ir_node.visibility,
        }
    )

# Call edge 생성
def create_call_edges(ir_doc: IRDocument) -> list[GraphEdge]:
    edges = []
    for func in ir_doc.functions:
        for call_site in func.calls:
            target_id = resolve_callee_id(call_site.callee, ir_doc)
            if target_id:
                edges.append(GraphEdge(
                    source=func.node_id,
                    target=target_id,
                    kind="CALLS",
                    properties={"line": call_site.line}
                ))
    return edges
```

**Kuzu 스키마**:
```cypher
// Nodes
CREATE NODE TABLE Symbol (
    node_id STRING PRIMARY KEY,
    name STRING,
    fqn STRING,
    kind STRING,
    visibility STRING
)

// Edges
CREATE REL TABLE CALLS (FROM Symbol TO Symbol)
CREATE REL TABLE IMPORTS (FROM Symbol TO Symbol)
CREATE REL TABLE CONTAINS (FROM Symbol TO Symbol)
```

---

### 2. Chunk Layer (100%)

**위치**: `src/foundation/chunk/`

**구현 완료**:
- ✅ `models.py` - Chunk 모델
  - 6단계 계층: Repo → Project → Module → File → Class → Function
  - 확장 타입: route, service, repository, config, job, middleware
  - Span tracking (original_start_line 포함)
  - 버전 관리 (version, is_deleted, last_indexed_commit)

- ✅ `id_generator.py` - Stable ID 생성
  - FQN 기반: `chunk:{repo_id}:{kind}:{fqn}`
  - 충돌 시 content_hash suffix

- ✅ `builder.py` - ChunkBuilder (계층 생성)
  - `_build_repo_chunk()` - Repository 최상위
  - `_build_project_chunks()` - 프로젝트 단위
  - `_build_module_chunks()` - 모듈 단위
  - `_build_file_chunks()` - 파일 단위
  - `_build_class_chunks()` - 클래스 단위
  - `_build_function_chunks()` - 함수 단위 (Leaf)
  - IR/Graph 매핑 자동 연결

- ✅ `boundary.py` - Boundary 검증
  - Sibling gap/overlap 검출
  - Invalid range 검출
  - Large chunk 경고 (토큰 기준)

- ✅ `mapping.py` - IR/Graph 매핑
  - `ChunkMapper`: Chunk → IRNode (라인 범위 기반)
  - `ChunkGraphMapper`: Chunk → GraphNode (1:1 또는 집계)
  - GraphNodeFilter (function/class/method만 포함)

- ✅ `incremental.py` - 증분 업데이트
  - **Phase A**: 파일 추가/삭제/수정 처리
  - **Phase B**: Span drift, Rename 감지
  - **Phase C**: Diff-based partial updates
    - `DiffParser`: unified diff 파싱
    - `_identify_affected_chunks()`: Hunk overlap 검사
    - 영향받지 않은 chunk는 재사용 (성능 최적화!)
  - Hook: `ChunkUpdateHook` (on_modified, on_drifted, on_renamed)

- ✅ `store.py` - ChunkStore 구현
  - **InMemoryChunkStore**: 개발/테스트용 (O(1) file index)
  - **PostgresChunkStore**: Production 구현
    - asyncpg 기반
    - 배치 UPSERT (500개씩)
    - `find_chunk_by_file_and_line()` - Zoekt 매핑 핵심 쿼리
    - Soft delete 지원

**핵심 알고리즘**:
```python
# 6단계 계층 생성 알고리즘
def build_chunk_hierarchy(ir_doc: IRDocument, graph_doc: GraphDocument):
    # 1. Repo chunk (root)
    repo_chunk = create_repo_chunk(repo_id)

    # 2. Project chunks (grouping by directory structure)
    project_chunks = group_by_project(ir_doc.files)
    for proj in project_chunks:
        proj.parent_id = repo_chunk.chunk_id

    # 3. Module chunks (Python packages)
    module_chunks = group_by_module(ir_doc.modules)

    # 4. File chunks (1:1 with files)
    file_chunks = [create_file_chunk(f) for f in ir_doc.files]

    # 5. Class chunks (from IR classes)
    class_chunks = [create_class_chunk(c) for c in ir_doc.classes]

    # 6. Function chunks (Leaf, from IR functions)
    func_chunks = [create_function_chunk(f) for f in ir_doc.functions]

    return all_chunks

# Diff-based partial update 알고리즘
def handle_modified_file_partial(file_path, diff_text):
    # 1. Diff 파싱
    hunks = parse_diff(diff_text)

    # 2. 영향받은 chunk 식별
    affected_chunks = []
    for chunk in old_chunks:
        for hunk in hunks:
            if overlaps(chunk.span, hunk.new_range):
                affected_chunks.append(chunk)

    # 3. 영향받은 chunk만 재생성
    new_ir = generate_ir(file_path)
    new_chunks = build_chunks(new_ir)

    # 4. 영향받지 않은 chunk는 기존 것 재사용
    final_chunks = merge(affected_new_chunks, unaffected_old_chunks)

    return final_chunks

# Zoekt file+line → Chunk 매핑 알고리즘
def find_chunk_by_file_and_line(repo_id, file_path, line):
    candidates = get_chunks_for_file(repo_id, file_path)

    # 1. Line 범위 필터링
    matching = [c for c in candidates
                if c.start_line <= line <= c.end_line]

    # 2. 우선순위 정렬
    priority = {
        "function": 1,
        "method": 1,
        "class": 2,
        "file": 3
    }
    matching.sort(key=lambda c: (
        priority.get(c.kind, 4),
        c.end_line - c.start_line  # 작은 chunk 우선
    ))

    return matching[0] if matching else None
```

**DB 스키마** (`infra/db/migrations/001_create_chunk_tables.sql`):
```sql
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,

    -- Hierarchy
    project_id TEXT,
    module_path TEXT,
    file_path TEXT,
    parent_id TEXT,

    -- Metadata
    kind TEXT NOT NULL,
    fqn TEXT NOT NULL,
    language TEXT,

    -- Source location (Zoekt 매핑용)
    start_line INTEGER,
    end_line INTEGER,
    original_start_line INTEGER,  -- Span drift tracking
    original_end_line INTEGER,

    -- Incremental
    content_hash TEXT,
    version INTEGER DEFAULT 1,
    is_deleted BOOLEAN DEFAULT FALSE,

    -- LLM
    summary TEXT,
    importance REAL DEFAULT 0.0,

    attrs JSONB DEFAULT '{}'
);

-- 핵심 인덱스: Zoekt 매핑용
CREATE INDEX idx_chunks_file_span
ON chunks (repo_id, file_path, start_line, end_line);
```

---

### 3. RepoMap Layer (100%)

**위치**: `src/repomap/`

**구현 완료**:
- ✅ `models.py` - RepoMap 모델
  - `RepoMapNode`: chunk 기반 트리 노드
  - `PageRankResult`: 중요도 점수
  - `RepoMapDocument`: 전체 맵 컨테이너

- ✅ `builder/orchestrator.py` - 오케스트레이터
  - Chunk hierarchy → RepoMap tree 변환
  - LLM summary 통합
  - PageRank 점수 병합

- ✅ `pagerank/engine.py` - PageRank 계산
  - Graph-based importance 계산
  - CALLS, IMPORTS edge 가중치
  - Damping factor: 0.85

- ✅ `summarizer/llm_summarizer.py` - LLM 요약
  - OpenAI/LiteLLM 기반
  - Chunk 단위 summary 생성
  - Cost control (token budget)
  - Redis 캐싱

- ✅ `storage_postgres.py` - PostgreSQL 저장소
  - RepoMap 영속화
  - 증분 업데이트 지원

- ✅ `incremental.py` - 증분 업데이트
  - Chunk 변경 감지 → RepoMap 부분 재생성
  - PageRank 재계산 (영향받은 서브그래프만)

**핵심 알고리즘**:
```python
# PageRank 알고리즘 (Graph-based)
def calculate_pagerank(graph: GraphDocument, damping=0.85, max_iter=100):
    nodes = set(graph.nodes.keys())
    n = len(nodes)

    # 초기값: 균등 분포
    ranks = {node: 1.0 / n for node in nodes}

    for _ in range(max_iter):
        new_ranks = {}
        for node in nodes:
            # 들어오는 링크의 rank 합산
            rank_sum = sum(
                ranks[src] / out_degree(src)
                for src in incoming_links(node)
            )
            new_ranks[node] = (1 - damping) / n + damping * rank_sum

        # 수렴 체크
        if converged(ranks, new_ranks):
            break

        ranks = new_ranks

    return ranks

# RepoMap 트리 생성
def build_repomap_tree(chunks: list[Chunk], pagerank: dict):
    # 1. Chunk hierarchy → Tree 변환
    tree = build_tree_from_chunks(chunks)

    # 2. PageRank 점수 병합
    for node in tree.nodes:
        node.importance = pagerank.get(node.chunk_id, 0.0)

    # 3. LLM summary 생성 (leaf chunks만)
    for leaf in tree.leaves():
        leaf.summary = llm_summarize(leaf.content)

    return tree
```

---

### 4. Index Layer (98%)

**위치**: `src/index/`

**구현 완료**:
- ✅ `common/documents.py` - 공통 모델
  - `IndexDocument`: Chunk → Index 입력
  - `SearchHit`: 통합 검색 결과 (source, score, metadata)

- ✅ `common/transformer.py` - 변환기
  - Chunk → IndexDocument 변환
  - `search_text` 생성: summary + code + identifiers

- ✅ `lexical/adapter_zoekt.py` - Lexical Index (Zoekt)
  - **Hybrid 매핑 전략**: Zoekt file+line → ChunkStore → SearchHit
  - **3단계 Fallback**:
    1. Exact function/class chunk → score 1.0
    2. File chunk fallback → score 0.8
    3. Virtual chunk_id → score 0.5 (warning)
  - Zoekt DSL 쿼리 빌더 (`repo:`, `lang:`, `file:`)
  - 매핑 통계 로깅

- ✅ `vector/adapter_qdrant.py` - Vector Index (Qdrant)
  - `EmbeddingProvider` 추상화 (Protocol)
  - `OpenAIEmbeddingProvider` 구현 (text-embedding-3-small)
  - Batch embedding (최대 2048 texts)
  - Collection 전략: `code_embeddings_{repo_id}_{snapshot_id_short}`
  - Batch upsert (256 points per batch)
  - Async/await 전체 적용

- ✅ `service.py` - IndexingService
  - 5개 index 오케스트레이션 (Lexical, Vector, Symbol, Fuzzy, Domain)
  - `search()`: Weighted fusion (RRF, score normalization)
  - Partial failure 처리 (일부 index 실패해도 계속)
  - 에러 로깅 및 수집

- ✅ `factory.py` - Factory Pattern
  - `create_indexing_service()`: 전체 구성
  - `create_indexing_service_minimal()`: MVP (Lexical + Vector만)
  - `IndexingConfig`: 환경별 프리셋 (DEV, PROD, TEST)
  - DI 통합 지원

**핵심 알고리즘**:
```python
# Zoekt Hybrid 매핑 알고리즘
async def search_with_chunk_mapping(query: str, repo_id: str):
    # 1. Zoekt 검색 (file+line 결과)
    zoekt_results = await zoekt.search(query, limit=100)

    search_hits = []
    stats = {"exact": 0, "file_fallback": 0, "virtual": 0}

    for match in zoekt_results:
        file_path = match.FileName
        line = match.LineNumber

        # 2. ChunkStore 조회 (우선순위 정렬)
        chunk = await chunk_store.find_chunk_by_file_and_line(
            repo_id, file_path, line
        )

        if chunk and chunk.kind in ("function", "class"):
            # 2-1. Exact mapping
            search_hits.append(SearchHit(
                chunk_id=chunk.chunk_id,
                score=1.0,
                source="lexical",
                metadata={"match_type": "exact"}
            ))
            stats["exact"] += 1

        elif file_chunk := await chunk_store.find_file_chunk(repo_id, file_path):
            # 2-2. File fallback
            search_hits.append(SearchHit(
                chunk_id=file_chunk.chunk_id,
                score=0.8,
                source="lexical",
                metadata={"match_type": "file_fallback"}
            ))
            stats["file_fallback"] += 1

        else:
            # 2-3. Virtual chunk_id
            virtual_id = f"virtual:{repo_id}:{file_path}:{line}"
            search_hits.append(SearchHit(
                chunk_id=virtual_id,
                score=0.5,
                source="lexical",
                metadata={"match_type": "virtual", "warning": "no_chunk_found"}
            ))
            stats["virtual"] += 1

    logger.info(f"Zoekt mapping stats: {stats}")
    return search_hits

# Vector Index 배치 처리 알고리즘
async def index_documents_batch(docs: list[IndexDocument]):
    # 1. 텍스트 추출
    texts = [doc.search_text for doc in docs]

    # 2. Batch embedding (OpenAI API)
    embeddings = await embedding_provider.embed_batch(
        texts, batch_size=2048
    )

    # 3. Qdrant points 생성
    points = [
        PointStruct(
            id=hash_id(doc.chunk_id),
            vector=embedding,
            payload={
                "chunk_id": doc.chunk_id,
                "repo_id": doc.repo_id,
                "file_path": doc.file_path,
                "kind": doc.kind,
            }
        )
        for doc, embedding in zip(docs, embeddings)
    ]

    # 4. 배치 upsert (256개씩)
    for batch in chunked(points, 256):
        await qdrant_client.upsert(
            collection_name=collection_name,
            points=batch
        )

# Weighted Fusion 알고리즘 (RRF)
def fuse_search_results(
    results: list[SearchHit],
    weights: dict[str, float]
) -> list[SearchHit]:
    # 1. Source별 그룹화
    by_source = defaultdict(list)
    for hit in results:
        by_source[hit.source].append(hit)

    # 2. RRF (Reciprocal Rank Fusion)
    fused_scores = defaultdict(float)
    k = 60  # RRF constant

    for source, hits in by_source.items():
        weight = weights.get(source, 1.0)
        for rank, hit in enumerate(hits, start=1):
            rrf_score = weight / (k + rank)
            fused_scores[hit.chunk_id] += rrf_score

    # 3. 정규화 및 정렬
    max_score = max(fused_scores.values()) if fused_scores else 1.0
    final_hits = [
        SearchHit(
            chunk_id=chunk_id,
            score=score / max_score,
            source="fusion",
            metadata={"sources": list(by_source.keys())}
        )
        for chunk_id, score in fused_scores.items()
    ]

    final_hits.sort(key=lambda h: h.score, reverse=True)
    return final_hits
```

**미완료 (Phase 3)**:
- ⏳ Symbol Index (Kuzu Graph) - 2%
- ⏳ Fuzzy Index (PostgreSQL pg_trgm)
- ⏳ Domain Index (문서 전용 검색)

---

### 5. Retriever Layer (100%)

**위치**: `src/retriever/`

**구현 완료**:
- ✅ **Phase 1: MVP**
  - `intent/rule_classifier.py` - Intent 분류 (find_definition, find_usage, etc.)
  - `multi_index/orchestrator.py` - 다중 인덱스 병렬 쿼리
  - `fusion/engine.py` - Weighted fusion, RRF
  - `context_builder/builder.py` - Context 패키징

- ✅ **Phase 2: Enhanced SOTA**
  - Late Interaction Search (ColBERT-style MaxSim)
  - Cross-encoder Reranking
  - Correlation-aware Fusion
  - Hard Negative Mining

- ✅ **Phase 3: Advanced SOTA**
  - `query/decomposer.py` - Multi-hop query 분해
  - `reasoning/test_time_reasoner.py` - o1-style reasoning
  - `observability/explainer.py` - 검색 결과 설명
  - `code_reranking/structural_reranker.py` - AST 기반 재순위
  - `code_reranking/callgraph_reranker.py` - Call graph proximity
  - `adaptive_embeddings/lora_trainer.py` - Repo-adaptive embeddings

**핵심 알고리즘**:
```python
# Multi-hop Retrieval 알고리즘
async def retrieve_multi_hop(decomposed_query: DecomposedQuery):
    results = []
    context = {}

    for step in decomposed_query.steps:
        # 1. 현재 step 검색 (이전 context 활용)
        step_results = await retriever.search(
            query=step.query,
            context=context,
            intent=step.intent
        )

        # 2. 결과를 context에 추가
        context[step.step_id] = step_results

        # 3. Graph expansion (필요 시)
        if step.expand_graph:
            expanded = await graph_expander.expand(
                step_results,
                direction=step.direction,
                depth=step.depth
            )
            context[step.step_id].extend(expanded)

        results.extend(step_results)

    # 4. 최종 fusion
    final = fusion_engine.fuse(results)
    return final

# Call Graph Proximity Reranking
def rerank_by_call_graph(
    candidates: list[SearchHit],
    reference_functions: list[str],
    call_graph: KuzuCallGraphAdapter
) -> list[SearchHit]:
    reranked = []

    for hit in candidates:
        # 1. Reference 함수와의 call graph 거리 계산
        distances = []
        for ref_func in reference_functions:
            # BFS shortest path
            dist = call_graph.shortest_path(
                ref_func, hit.symbol_id
            )
            distances.append(dist if dist else float('inf'))

        # 2. 최소 거리 기준 boost
        min_dist = min(distances)
        if min_dist < float('inf'):
            boost = 1.0 / (1 + min_dist)  # 거리 1 → boost 0.5
            hit.score *= (1 + 0.2 * boost)  # 최대 20% boost
            hit.metadata["call_graph_boost"] = boost

        reranked.append(hit)

    reranked.sort(key=lambda h: h.score, reverse=True)
    return reranked
```

---

### 6. Server Layer (100%)

**위치**: `server/`

**구현 완료**:
- ✅ `api_server/main.py` - FastAPI 애플리케이션
  - Lifespan 관리 (startup/shutdown)
  - Container 기반 DI
  - CORS 미들웨어

- ✅ `api_server/routes/search.py` - 검색 API
  - `GET /search` - 통합 하이브리드 검색
  - `GET /search/lexical` - Lexical 전용
  - `GET /search/vector` - Vector 전용
  - `GET /search/symbol` - Symbol 전용 (stub)
  - `GET /search/fuzzy` - Fuzzy 전용 (stub)
  - `GET /search/domain` - Domain 전용 (stub)

- ✅ `api_server/routes/indexing.py` - 인덱싱 API (stub)
  - `POST /index/repo` - Full indexing
  - `POST /index/incremental` - Incremental indexing
  - `DELETE /index/repo` - Delete index
  - `GET /index/status/{repo_id}` - Status check

- ✅ `mcp_server/main.py` - MCP Server
  - Claude 통합 툴
  - `search_code`, `get_chunk`, `get_symbol` 등

---

### 7. Infrastructure Layer (100%)

**위치**: `src/infra/`

**구현 완료**:
- ✅ `storage/postgres.py` - PostgreSQL (asyncpg pool)
- ✅ `cache/redis.py` - Redis cache
- ✅ `vector/qdrant.py` - Qdrant async client
- ✅ `graph/kuzu.py` - Kuzu embedded DB
- ✅ `search/zoekt.py` - Zoekt HTTP client
- ✅ `llm/openai.py` - OpenAI/LiteLLM
- ✅ `git/git_cli.py` - GitPython wrapper

**테스트**: 426 tests (100% pass)

---

## 🚧 구현 예정 (3%)

### 1. Agent Layer (0%)

**목표**: Cursor급 코드 에이전트 구현

#### Phase 1: Tool Layer (1주)

**위치**: `src/agent/tools/` (신규)

**구현 예정**:
```python
# src/agent/tools/code_tools.py
async def code_search(query: str, scope: str = "repo") -> SearchResult:
    """
    Semantica Codegraph 기반 코드 검색.

    Args:
        query: 검색 쿼리 (자연어 or 키워드)
        scope: repo | module | file

    Returns:
        SearchResult with ranked chunks
    """
    pass

async def symbol_search(name: str) -> Symbol:
    """심볼 검색 (정확한 이름 매칭)"""
    pass

async def graph_neighbors(
    symbol_id: str,
    direction: str = "both",
    depth: int = 1
) -> list[Symbol]:
    """
    Call graph 탐색.

    Args:
        symbol_id: Symbol ID
        direction: callers | callees | both
        depth: 탐색 깊이
    """
    pass

# src/agent/tools/file_tools.py
async def open_file(path: str, span: Span | None = None) -> str:
    """
    파일 열기 (전체 또는 일부).

    Args:
        path: 파일 경로
        span: 특정 범위 (start_line, end_line)
    """
    pass

async def get_span(path: str, start_line: int, end_line: int) -> str:
    """파일의 특정 범위 추출"""
    pass

# src/agent/tools/patch_tools.py
async def propose_patch(
    path: str,
    span: Span,
    new_code: str,
    reason: str
) -> Patch:
    """
    패치 제안 (dry-run, 실행 안 함).

    Args:
        path: 파일 경로
        span: 수정 범위
        new_code: 새 코드
        reason: 수정 이유

    Returns:
        Patch with validation result
    """
    pass

async def apply_patch(patch: Patch) -> ApplyResult:
    """
    패치 적용 (실제 파일 수정).

    주의: Reviewer 승인 후에만 호출!
    """
    pass

# src/agent/tools/test_tools.py
async def run_tests(scope: str = "all") -> TestResult:
    """
    테스트 실행.

    Args:
        scope: all | module | file | function
    """
    pass

async def run_lint(path: str) -> LintResult:
    """Linter 실행"""
    pass

# src/agent/tools/git_tools.py
async def git_diff(path: str | None = None) -> str:
    """Git diff 조회"""
    pass
```

**핵심 설계**:
- 모든 툴은 JSON 스키마 기반 (LLM 호출 가능)
- Async/await 전체 적용
- Dry-run 기본 (side-effect는 명시적 승인 필요)
- 에러 핸들링 + 재시도 로직

---

#### Phase 2: Agent Orchestration (LangGraph) (1-2주)

**위치**: `src/agent/orchestration/` (신규)

**구현 예정**:
```python
# src/agent/orchestration/state.py
class AgentState(TypedDict):
    """LangGraph State"""
    messages: list[BaseMessage]
    plan: Plan  # Step-by-step plan
    current_step: int
    tool_results: dict[str, Any]
    context: ContextBundle  # Semantica context
    done: bool
    error: str | None

# src/agent/orchestration/nodes.py
async def planner_node(state: AgentState) -> AgentState:
    """
    계획 생성 노드.

    입력: User request, context
    출력: Step-by-step plan

    알고리즘:
    1. Intent 분석 (find_bug, refactor, add_feature, etc.)
    2. Context 수집 (관련 파일, 심볼, call chain)
    3. Plan 생성 (STEP 1: analyze, STEP 2: propose_patch, ...)
    """
    pass

async def tool_router_node(state: AgentState) -> str:
    """
    다음 툴 선택 노드.

    입력: Current plan, current_step
    출력: Tool name (code_search, open_file, propose_patch, etc.)

    알고리즘:
    1. Plan의 current_step 파싱
    2. Step에 필요한 툴 식별
    3. 툴 파라미터 준비
    """
    pass

async def tool_node(state: AgentState, tool_name: str) -> AgentState:
    """
    툴 실행 노드.

    입력: Tool name, parameters
    출력: Tool result (added to state.tool_results)
    """
    pass

async def reviewer_node(state: AgentState) -> AgentState:
    """
    검토 노드.

    입력: Tool results, plan
    출력: 승인 or 재계획 요청

    알고리즘:
    1. Proposal 검증 (syntax check, test pass, etc.)
    2. 파일 일치성 확인
    3. LLM hallucination 감지
    4. OK → answer_node, NG → planner_node (revise)
    """
    pass

async def answer_node(state: AgentState) -> AgentState:
    """최종 답변 생성"""
    pass

# src/agent/orchestration/graph.py
def create_agent_graph() -> StateGraph:
    """
    LangGraph 정의.

    구조:
        START → planner → tool_router → tool → reviewer
                  ↑                              ↓
                  └──────────(revise)────────────┘
                                                 ↓
                                               answer → END
    """
    graph = StateGraph(AgentState)

    # Nodes
    graph.add_node("planner", planner_node)
    graph.add_node("tool_router", tool_router_node)
    graph.add_node("tool", tool_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("answer", answer_node)

    # Edges
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "tool_router")
    graph.add_edge("tool_router", "tool")
    graph.add_edge("tool", "reviewer")

    # Conditional edges
    graph.add_conditional_edges(
        "reviewer",
        should_continue,
        {
            "revise": "planner",  # 재계획
            "answer": "answer",   # 완료
        }
    )

    graph.add_edge("answer", END)

    return graph.compile()
```

**핵심 알고리즘**:
```python
# Plan 생성 알고리즘
async def generate_plan(user_request: str, context: ContextBundle) -> Plan:
    # 1. Intent 분석
    intent = classify_intent(user_request)

    # 2. Intent별 템플릿 선택
    if intent == "fix_bug":
        template = BUG_FIX_TEMPLATE
    elif intent == "refactor":
        template = REFACTOR_TEMPLATE
    elif intent == "add_feature":
        template = ADD_FEATURE_TEMPLATE

    # 3. Context 기반 계획 커스터마이징
    plan = template.customize(context)

    # 4. LLM으로 plan 검증/개선
    refined_plan = await llm.refine_plan(plan, user_request)

    return refined_plan

# Workflow 템플릿
BUG_FIX_TEMPLATE = [
    {"step": 1, "action": "symbol_search", "param": "{error_symbol}"},
    {"step": 2, "action": "open_file", "param": "{file_path}"},
    {"step": 3, "action": "graph_neighbors", "param": "{symbol_id}", "direction": "callers"},
    {"step": 4, "action": "propose_patch", "param": "{fix_location}"},
    {"step": 5, "action": "run_tests", "param": "related"},
    {"step": 6, "action": "finalize"},
]
```

---

#### Phase 3: Context Builder (1주)

**위치**: `src/agent/context/` (신규)

**구현 예정**:
```python
# src/agent/context/builder.py
class ContextBuilder:
    """
    Semantica Codegraph 기반 Context 패키징.

    목적: Agent가 "어디를 고쳐야 하는지" 정확히 찾도록 지원
    """

    def __init__(
        self,
        search_service: IndexingService,
        graph_store: KuzuGraphStore,
        chunk_store: ChunkStore,
    ):
        self.search = search_service
        self.graph = graph_store
        self.chunks = chunk_store

    async def build_bug_context(
        self,
        error_message: str,
        stack_trace: str | None = None
    ) -> ContextBundle:
        """
        버그 수정 Context 생성.

        알고리즘:
        1. Stack trace 파싱 → symbol 추출
        2. Symbol search → 관련 파일 식별
        3. Graph traversal → callers/callees 확장
        4. 관련 테스트 코드 검색
        """
        # 1. Symbol 추출
        symbols = parse_stack_trace(stack_trace)

        # 2. 관련 파일 수집
        files = []
        for sym in symbols:
            chunk = await self.chunks.get_chunk(sym.chunk_id)
            files.append(chunk.file_path)

        # 3. Call graph 확장
        callers = []
        callees = []
        for sym in symbols:
            callers.extend(await self.graph.query_called_by(sym.symbol_id))
            callees.extend(await self.graph.query_calls(sym.symbol_id))

        # 4. 테스트 검색
        tests = await self.search.search(
            query=f"test {symbols[0].name}",
            filters={"kind": "function", "path": "*test*"}
        )

        return ContextBundle(
            files=files,
            symbols=symbols + callers + callees,
            call_chains=self._build_call_chains(symbols, callers, callees),
            tests=tests,
            error_message=error_message,
        )

    async def build_refactor_context(
        self,
        target: str,  # file or module
        intent: str   # simplify, extract, rename
    ) -> ContextBundle:
        """리팩토링 Context 생성"""
        pass

    async def build_feature_context(
        self,
        feature_description: str,
        reference_files: list[str]
    ) -> ContextBundle:
        """새 기능 추가 Context 생성"""
        pass

# src/agent/context/models.py
class ContextBundle:
    """Context 패키지 (Agent에 전달)"""
    files: list[str]
    symbols: list[Symbol]
    call_chains: list[CallChain]
    tests: list[Chunk]
    metadata: dict[str, Any]
```

**핵심 알고리즘**:
```python
# Call Chain 생성 알고리즘
def build_call_chains(
    symbols: list[Symbol],
    callers: list[Symbol],
    callees: list[Symbol]
) -> list[CallChain]:
    """
    Symbol → Callers/Callees 관계를 Chain으로 시각화.

    예시:
    main() → authenticate() → check_password() → ERROR
    """
    chains = []

    for sym in symbols:
        # 역방향 chain (callers)
        caller_chain = []
        current = sym
        while current:
            caller_chain.insert(0, current)
            parents = [c for c in callers if c.calls(current)]
            current = parents[0] if parents else None

        # 정방향 chain (callees)
        callee_chain = [sym]
        current = sym
        while current:
            children = [c for c in callees if current.calls(c)]
            current = children[0] if children else None
            if current:
                callee_chain.append(current)

        chains.append(CallChain(
            root=sym,
            callers=caller_chain,
            callees=callee_chain
        ))

    return chains
```

---

#### Phase 4: Multi-step Patch Engine (1-2주)

**구현 예정**:
```python
# src/agent/patch/engine.py
class PatchEngine:
    """
    Multi-step patch 생성 엔진.

    워크플로우:
    1. propose_patch (dry-run)
    2. Syntax validation
    3. run_tests
    4. Review 승인
    5. apply_patch (실제 적용)
    6. 실패 시 rollback → revise
    """

    async def execute_patch_workflow(
        self,
        patches: list[Patch],
        test_scope: str = "affected"
    ) -> WorkflowResult:
        """
        패치 적용 워크플로우 실행.

        알고리즘:
        1. 각 patch를 dry-run으로 검증
        2. 모든 patch가 valid하면 테스트 실행
        3. 테스트 통과 시 순차 적용
        4. 실패 시 rollback + 재시도
        """
        # 1. Validation
        for patch in patches:
            valid = await self._validate_patch(patch)
            if not valid:
                return WorkflowResult(
                    status="failed",
                    reason="syntax_error",
                    failed_patch=patch
                )

        # 2. Apply patches (transaction)
        try:
            for patch in patches:
                await apply_patch(patch)

            # 3. Run tests
            test_result = await run_tests(scope=test_scope)

            if test_result.passed:
                return WorkflowResult(status="success")
            else:
                # Rollback
                await self._rollback_patches(patches)
                return WorkflowResult(
                    status="test_failed",
                    test_failures=test_result.failures
                )

        except Exception as e:
            await self._rollback_patches(patches)
            return WorkflowResult(status="error", error=str(e))
```

---

#### Phase 5: 안전성 + 엣지 케이스 (지속적)

**구현 예정**:
```python
# src/agent/safety/validators.py
class SafetyValidator:
    """Agent 안전성 검증"""

    async def validate_tool_call(
        self,
        tool_name: str,
        params: dict
    ) -> ValidationResult:
        """
        툴 호출 검증.

        체크:
        1. JSON 스키마 일치
        2. 파라미터 타입 검증
        3. 파일 경로 존재 여부
        4. 권한 체크 (side-effect 툴)
        """
        pass

    def detect_loop(self, state: AgentState) -> bool:
        """
        루프 감지.

        알고리즘:
        1. Plan hash 계산
        2. 최근 5개 plan hash 비교
        3. 동일 plan 반복 시 경고
        """
        pass

    def check_max_calls(self, state: AgentState) -> bool:
        """
        동일 툴 반복 호출 체크.

        정책: 동일 툴 최대 3번
        """
        tool_counts = defaultdict(int)
        for result in state.tool_results.values():
            tool_counts[result["tool"]] += 1

        return max(tool_counts.values()) <= 3

# src/agent/safety/hallucination_detector.py
class HallucinationDetector:
    """LLM Hallucination 감지"""

    async def detect_in_patch(self, patch: Patch) -> bool:
        """
        Patch에서 hallucination 감지.

        체크:
        1. 변경되지 않은 라인 포함 여부
        2. 존재하지 않는 함수 호출
        3. Context와 무관한 변경
        """
        pass
```

---

### 2. Index Layer Phase 3 (2%)

#### Symbol Index (Kuzu Graph)

**위치**: `src/index/symbol/adapter_kuzu.py` (미완성)

**구현 예정**:
```python
class KuzuSymbolIndex:
    """
    Kuzu Graph 기반 Symbol Index.

    기능:
    - Go-to-definition
    - Find-references
    - Call graph 탐색
    """

    async def index_graph(self, graph_doc: GraphDocument) -> None:
        """GraphDocument를 Kuzu에 저장"""
        pass

    async def search(
        self,
        query: str,
        kind: str | None = None
    ) -> list[SearchHit]:
        """
        Symbol 이름 검색.

        쿼리 예시:
        MATCH (s:Symbol {name: $query})
        WHERE s.kind = $kind
        RETURN s
        """
        pass

    async def go_to_definition(self, symbol_id: str) -> SearchHit:
        """Definition 조회"""
        pass

    async def find_references(self, symbol_id: str) -> list[SearchHit]:
        """
        References 검색.

        쿼리 예시:
        MATCH (caller)-[:CALLS]->(target:Symbol {id: $symbol_id})
        RETURN caller
        """
        pass
```

---

#### Fuzzy Index (PostgreSQL pg_trgm)

**위치**: `src/index/fuzzy/adapter_postgres.py` (미완성)

**구현 예정**:
```python
class PostgresFuzzyIndex:
    """
    PostgreSQL pg_trgm 기반 Fuzzy Index.

    기능:
    - 오타 허용 identifier 검색
    - Trigram similarity 매칭
    """

    async def index(self, docs: list[IndexDocument]) -> None:
        """
        Identifier 추출 및 인덱싱.

        SQL:
        INSERT INTO fuzzy_identifiers (chunk_id, identifier)
        VALUES ...
        ON CONFLICT DO NOTHING
        """
        pass

    async def search(
        self,
        query: str,
        threshold: float = 0.3
    ) -> list[SearchHit]:
        """
        Fuzzy 검색.

        SQL:
        SELECT chunk_id, identifier,
               similarity(identifier, $query) AS score
        FROM fuzzy_identifiers
        WHERE identifier % $query  -- Trigram match
        ORDER BY score DESC
        """
        pass
```

---

#### Domain Index (PostgreSQL Full-text)

**위치**: `src/index/domain_meta/adapter.py` (미완성)

**구현 예정**:
```python
class DomainMetaIndex:
    """
    문서 전용 검색 (README, ADR, API docs).

    기능:
    - Full-text search (tsvector/tsquery)
    - 문서 타입 분류
    """

    async def index(self, docs: list[IndexDocument]) -> None:
        """
        문서 인덱싱.

        SQL:
        INSERT INTO domain_documents (chunk_id, title, content, doc_type)
        VALUES ...
        """
        pass

    async def search(
        self,
        query: str,
        doc_type: str | None = None
    ) -> list[SearchHit]:
        """
        Full-text 검색.

        SQL:
        SELECT chunk_id,
               ts_rank(search_vector, plainto_tsquery($query)) AS score
        FROM domain_documents
        WHERE search_vector @@ plainto_tsquery($query)
        ORDER BY score DESC
        """
        pass
```

---

## 📋 구현 우선순위

### Critical (즉시 시작 가능)
1. **Agent Tool Layer** (1주)
   - Semantica 기반 tool 구현
   - 가장 먼저 완성해야 LLM에 노출 가능

### High (Tool Layer 완성 후)
2. **Agent Orchestration** (1-2주)
   - LangGraph 기반 워크플로우
   - Tool과 연결되어야 동작

3. **Context Builder** (1주)
   - Tool과 동시 진행 가능
   - Agent의 "네비게이션" 역할

### Medium (Agent 완성 후)
4. **Symbol Index** (1주)
   - Kuzu Graph 활용
   - go-to-def, find-refs 핵심 기능

5. **Fuzzy/Domain Index** (1주)
   - 검색 정확도 향상
   - 선택적 구현

---

## 🎯 최종 목표

### 3개월 완성 계획
- **Month 1**: Agent Tool Layer + Orchestration (Phase 1-2)
- **Month 2**: Context Builder + Multi-step Patch (Phase 3-4)
- **Month 3**: 안전성 + Index Phase 3 (Phase 5)

### 예상 최종 구성
```
전체 진행도: 100%
├── Foundation Layer (✅ 100%)
├── Chunk Layer (✅ 100%)
├── RepoMap Layer (✅ 100%)
├── Index Layer (✅ 100%)
│   ├── Lexical (✅)
│   ├── Vector (✅)
│   ├── Symbol (🔜)
│   ├── Fuzzy (🔜)
│   └── Domain (🔜)
├── Retriever Layer (✅ 100%)
├── Server Layer (✅ 100%)
└── Agent Layer (🔜 0%)
    ├── Tool Layer (🔜)
    ├── Orchestration (🔜)
    ├── Context Builder (🔜)
    ├── Patch Engine (🔜)
    └── Safety (🔜)
```

**최종 목표**: Cursor를 능가하는 Graph-based 코드 에이전트! 🚀

---

**작성 완료일**: 2024-11-24
**다음 업데이트**: Agent Layer Phase 1 완료 후
