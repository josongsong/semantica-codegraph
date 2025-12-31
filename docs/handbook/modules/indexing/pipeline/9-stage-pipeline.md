# 9단계 인덱싱 파이프라인 상세

> 각 Stage의 역할, 입출력, 성능 특성

---

## 목차

1. [파이프라인 개요](#1-파이프라인-개요)
2. [Stage 1: GitStage](#stage-1-gitstage)
3. [Stage 2: DiscoveryStage](#stage-2-discoverystage)
4. [Stage 3: ParsingStage](#stage-3-parsingstage)
5. [Stage 4: IRStage](#stage-4-irstage)
6. [Stage 5: SemanticIRStage](#stage-5-semanticirstage)
7. [Stage 6: GraphStage](#stage-6-graphstage)
8. [Stage 7: ChunkStage](#stage-7-chunkstage)
9. [Stage 8: RepoMapStage](#stage-8-repomapstage)
10. [Stage 9: IndexingStage](#stage-9-indexingstage)
11. [협력적 취소 (Graceful Stop)](#협력적-취소)

---

## 1. 파이프라인 개요

### 전체 플로우

```
Git → Discovery → Parsing → IR → Semantic IR → Graph → Chunk → RepoMap → Indexing
 ↓        ↓         ↓        ↓       ↓          ↓       ↓        ↓         ↓
메타    파일 목록    AST    구조 IR  의미 IR    그래프  청크   RepoMap   다중 인덱스
```

### 레이어 매핑

| Stage | 레이어 | 설명 |
|-------|--------|------|
| GitStage | L0 | 변경 감지 |
| DiscoveryStage | L0 | 파일 탐색 |
| ParsingStage | L1 | AST 파싱 |
| IRStage | L2 | 구조 IR |
| SemanticIRStage | L3 | 의미 IR |
| GraphStage | L3 | 그래프 빌딩 |
| ChunkStage | L2 | 청크 생성 |
| RepoMapStage | - | RepoMap |
| IndexingStage | - | 저장 |

---

## Stage 1: GitStage

### 역할
Git 메타데이터 수집 (commit, branch, author)

### 입력
- `repo_path: Path`
- `snapshot_id: str`

### 출력
```python
@dataclass
class GitMetadata:
    commit_hash: str
    branch: str
    author: str
    commit_date: datetime
    remote_url: str | None
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/git_stage.py
class GitStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        git_helper = GitHelper(ctx.repo_path)

        metadata = GitMetadata(
            commit_hash=git_helper.get_head_commit(),
            branch=git_helper.get_current_branch(),
            author=git_helper.get_last_author(),
            commit_date=git_helper.get_commit_date(),
            remote_url=git_helper.get_remote_url(),
        )

        return StageResult(success=True, data=metadata)
```

### 성능
- **시간:** <
- **메모리:** <1MB
- **의존성:** git CLI

### 실패 케이스
- Git repo 아님 → WARNING, 계속 진행
- Detached HEAD → branch="HEAD"
- No remote → remote_url=None

---

## Stage 2: DiscoveryStage

### 역할
소스 파일 탐색 (extensions 기반)

### 입력
- `repo_path: Path`
- `exclude_patterns: list[str]`
- `supported_extensions: list[str]`

### 출력
```python
@dataclass
class DiscoveryResult:
    files: list[Path]           # 발견된 파일들
    total_size: int             # 총 크기 (bytes)
    by_language: dict[str, int] # 언어별 개수
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/discovery_stage.py
class DiscoveryStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        files = []

        for ext in SUPPORTED_EXTENSIONS:
            pattern = f"**/*{ext}"
            found = repo_path.glob(pattern)
            files.extend([f for f in found if not self._is_excluded(f)])

        # 언어 분류
        by_language = defaultdict(int)
        for file in files:
            lang = self._detect_language(file.suffix)
            by_language[lang] += 1

        return StageResult(
            success=True,
            data=DiscoveryResult(
                files=files,
                total_size=sum(f.stat().st_size for f in files),
                by_language=dict(by_language),
            )
        )
```

### 성능
- **시간:** ~1초 (10K 파일)
- **메모리:** ~10MB
- **병렬화:** 가능 (언어별)

### 제외 패턴 (기본값)
```python
DEFAULT_EXCLUDE = [
    ".git", "node_modules", "__pycache__", ".venv",
    "*.pyc", "*.log", ".DS_Store"
]
```

---

## Stage 3: ParsingStage

### 역할
Tree-sitter AST 파싱

### 입력
- `files: list[Path]`
- `languages: dict[str, Language]`

### 출력
```python
@dataclass
class ParseResult:
    file_path: str
    language: str
    ast_root: Node          # Tree-sitter Node
    parse_time_ms: float
    success: bool
    error: str | None
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/parsing_stage.py
class ParsingStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        results = []

        for file_path in ctx.files:
            lang = detect_language(file_path)
            parser = self._get_parser(lang)

            with open(file_path, 'rb') as f:
                content = f.read()

            tree = parser.parse(content)

            results.append(ParseResult(
                file_path=str(file_path),
                language=lang,
                ast_root=tree.root_node,
                success=True,
            ))

        return StageResult(success=True, data=results)
```

### 성능
- **시간:** ~/파일 (평균)
- **메모리:** ~2MB/파일 (AST)
- **병렬화:** 필수 (언어별 파서 재사용)

### 지원 언어
```python
SUPPORTED_LANGUAGES = [
    "python", "typescript", "javascript", "java",
    "go", "rust", "c", "cpp", "kotlin"
]
```

### 실패 처리
```python
# Syntax error → ParseResult(success=False, error=str(e))
# 파일 읽기 실패 → Skip, WARNING 로그
```

---

## Stage 4: IRStage

### 역할
구조 IR 생성 (L2)

### 입력
- `parse_results: list[ParseResult]`

### 출력
```python
@dataclass
class IRDocument:
    file_path: str
    language: str
    imports: list[Import]
    symbols: list[Symbol]     # classes, functions, variables
    occurrences: list[Occurrence]
    diagnostics: list[Diagnostic]
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/ir_stage.py
class IRStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        ir_builder = LayeredIRBuilder()
        results = []

        for parse_result in ctx.parse_results:
            ir_doc = await ir_builder.build(
                file_path=parse_result.file_path,
                ast_root=parse_result.ast_root,
                language=parse_result.language,
            )
            results.append(ir_doc)

        return StageResult(success=True, data=results)
```

### 성능
- **시간:** ~/파일
- **메모리:** ~5MB/파일
- **병렬화:** 언어별

### 생성 정보
- **Imports:** 모듈, 클래스, 함수 import
- **Symbols:** FQN, kind (class/func/var), location
- **Occurrences:** Symbol usage 추적
- **Diagnostics:** 타입 에러, unused imports

---

## Stage 5: SemanticIRStage

### 역할
의미 IR 생성 (L3 - CFG/DFG)

### 입력
- `ir_documents: list[IRDocument]`

### 출력
```python
@dataclass
class SemanticIR:
    cfg: ControlFlowGraph
    dfg: DataFlowGraph
    type_info: TypeInfo
    signatures: dict[str, Signature]
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/semantic_ir_stage.py
class SemanticIRStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        semantic_builder = SemanticIRBuilder()
        results = []

        for ir_doc in ctx.ir_documents:
            sem_ir = await semantic_builder.build(ir_doc)
            results.append(sem_ir)

        return StageResult(success=True, data=results)
```

### 성능
- **시간:** ~/파일 (L3), ~ (L4)
- **메모리:** ~10MB/파일
- **제한:** BALANCED는 CFG 노드 100개까지

### L3 vs L4

| 항목 | L3 (BALANCED) | L4 (DEEP) |
|------|--------------|-----------|
| CFG | 100 노드 | Unlimited |
| DFG | Single function | Cross-function |
| Git History | 10 commits | All |

---

## Stage 6: GraphStage

### 역할
코드 그래프 빌딩 (Node, Edge)

### 입력
- `ir_documents: list[IRDocument]`
- `semantic_irs: list[SemanticIR]`

### 출력
```python
@dataclass
class CodeGraph:
    nodes: list[GraphNode]    # Files, Symbols
    edges: list[GraphEdge]    # IMPORTS, CALLS, INHERITS
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/graph_stage.py
class GraphStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        graph_builder = GraphBuilder()

        # 1. Add nodes
        for ir_doc in ctx.ir_documents:
            graph_builder.add_file_node(ir_doc.file_path)
            for symbol in ir_doc.symbols:
                graph_builder.add_symbol_node(symbol)

        # 2. Add edges
        for ir_doc in ctx.ir_documents:
            for imp in ir_doc.imports:
                graph_builder.add_import_edge(
                    from_file=ir_doc.file_path,
                    to_module=imp.module,
                )

        graph = graph_builder.build()
        return StageResult(success=True, data=graph)
```

### 성능
- **시간:** ~ (1000 파일)
- **메모리:** ~50MB
- **병렬화:** 불가 (global state)

### Edge 타입
```python
class EdgeType(Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    DEFINES = "defines"
    REFERENCES = "references"
```

---

## Stage 7: ChunkStage

### 역할
LLM-friendly 청크 생성

### 입력
- `ir_documents: list[IRDocument]`
- `code_graph: CodeGraph`

### 출력
```python
@dataclass
class Chunk:
    id: str
    level: ChunkLevel    # REPO/MODULE/FILE/CLASS/FUNCTION
    content: str
    metadata: ChunkMetadata
    embeddings: list[float] | None
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/chunk_stage.py
class ChunkStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        chunk_builder = ChunkBuilder()
        chunks = []

        for ir_doc in ctx.ir_documents:
            # File-level chunk
            file_chunk = chunk_builder.create_file_chunk(ir_doc)
            chunks.append(file_chunk)

            # Symbol-level chunks
            for symbol in ir_doc.symbols:
                if symbol.kind in (SymbolKind.CLASS, SymbolKind.FUNCTION):
                    chunk = chunk_builder.create_symbol_chunk(symbol)
                    chunks.append(chunk)

        return StageResult(success=True, data=chunks)
```

### 성능
- **시간:** ~/파일
- **메모리:** ~20MB
- **병렬화:** 가능

### Chunk 계층
```
Repo
 ├─ Module (src/core/)
 │   ├─ File (main.py)
 │   │   ├─ Class (MyClass)
 │   │   │   └─ Function (method)
 │   │   └─ Function (top_level_func)
```

---

## Stage 8: RepoMapStage

### 역할
RepoMap 빌딩 (트리 + PageRank)

### 입력
- `code_graph: CodeGraph`
- `chunks: list[Chunk]`

### 출력
```python
@dataclass
class RepoMap:
    tree: RepoTree          # 디렉토리 구조
    pagerank: dict[str, float]  # 파일 중요도
    summaries: dict[str, str]   # LLM 요약
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/repomap_stage.py
class RepoMapStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        # 1. Build tree
        tree = RepoTree.from_graph(ctx.code_graph)

        # 2. PageRank (rustworkx 400x faster)
        pagerank = self._compute_pagerank(ctx.code_graph)

        # 3. LLM summaries (optional, expensive)
        summaries = {}
        if ctx.enable_summaries:
            summaries = await self._generate_summaries(ctx.chunks)

        return StageResult(
            success=True,
            data=RepoMap(tree, pagerank, summaries)
        )
```

### 성능
- **시간:** ~1초 (tree + pagerank)
- **LLM 요약:** ~10초 (expensive)
- **메모리:** ~30MB

### PageRank 알고리즘
- **Library:** rustworkx (400x faster than NetworkX)
- **Damping:** 0.85
- **Iterations:** 100

---

## Stage 9: IndexingStage

### 역할
다중 인덱스 저장

### 입력
- 모든 이전 Stage 결과

### 출력
```python
@dataclass
class IndexingResult:
    indexed_files: int
    lexical_indexed: bool
    vector_indexed: bool
    symbol_indexed: bool
    duration_ms: float
```

### 구현
```python
# src/contexts/analysis_indexing/infrastructure/stages/indexing_stage.py
class IndexingStage(IndexingStage):
    async def execute(self, ctx: StageContext) -> StageResult:
        # 병렬 인덱싱
        tasks = [
            self._index_lexical(ctx),    # Zoekt/Tantivy
            self._index_vector(ctx),     # Qdrant
            self._index_symbol(ctx),     # PostgreSQL/Memgraph
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return StageResult(success=True, data=results)
```

### 인덱스 타입

| 인덱스 | 기술 | 용도 |
|--------|------|------|
| Lexical (Base) | Zoekt | 전문 검색 |
| Lexical (Delta) | Tantivy | 증분 변경 |
| Vector | Qdrant | 의미 검색 |
| Symbol | PostgreSQL | 심볼 조회 |

### 성능
- **시간:** ~5초 (10K 파일)
- **병렬화:** 3개 인덱스 동시
- **메모리:** ~100MB

---

## 협력적 취소 (Graceful Stop)

### 메커니즘

```python
# IndexingOrchestratorSlim
async def execute_with_stop(
    self,
    repo_path: Path,
    stop_event: asyncio.Event,
    progress: JobProgress,
) -> IndexingResult:
    for file_path in files:
        # 🔥 Cooperative cancellation check
        if stop_event.is_set():
            logger.info("Stop requested, saving progress")
            progress.save()
            return IndexingResult(partial=True)

        # 파일 처리
        progress.processing_file = str(file_path)
        await self._process_file(file_path)
        progress.completed_files.add(str(file_path))
```

### 사용 예
```python
# BackgroundScheduler에서
stop_event = asyncio.Event()
progress = JobProgress(job_id="job-123")

# BALANCED 시작
task = orchestrator.execute_with_stop(repo_path, stop_event, progress)

# 사용자 활동 감지
stop_event.set()  # Graceful stop 요청

# 현재 파일 완료 대기 (최대 30초)
await asyncio.wait_for(task, timeout=30.0)

# progress.completed_files로 재개 가능
```

---

## 전체 파이프라인 실행

### 코드 예제

```python
from src.contexts.analysis_indexing.infrastructure.orchestrator import IndexingOrchestrator

# 초기화
orchestrator = IndexingOrchestrator(
    parser_service=parser,
    ir_builder=ir_builder,
    graph_builder=graph_builder,
    # ... 기타 컴포넌트
)

# 실행
result = await orchestrator.execute(
    repo_path=Path("/path/to/repo"),
    repo_id="my-repo",
    snapshot_id="snapshot-123",
    mode=IndexingMode.BALANCED,
)

# 결과
print(f"Indexed {result.indexed_files} files in {result.duration_ms}ms")
```

### 실행 시간 (10K 파일)

| Stage | FAST | BALANCED | DEEP |
|-------|------|----------|------|
| Git | < | < | < |
| Discovery | ~1s | ~1s | ~1s |
| Parsing | ~20s | ~20s | ~20s |
| IR | ~50s | ~50s | ~50s |
| Semantic IR | Skip | ~200s | ~1000s |
| Graph | ~ | ~ | ~ |
| Chunk | ~100s | ~100s | ~100s |
| RepoMap | ~1s | ~1s | ~1s |
| Indexing | ~5s | ~5s | ~5s |
| **Total** | **~3min** | **~6min** | **~20min** |

---

## 실패 처리

### Stage 실패 정책

```python
@dataclass
class StageResult:
    success: bool
    data: Any
    error: str | None
    partial: bool = False  # 부분 성공
```

### 전략

| Stage | 실패 시 | 계속 진행? |
|-------|---------|----------|
| GitStage | WARNING | ✅ Yes |
| DiscoveryStage | ERROR | ❌ No (파일 없음) |
| ParsingStage | Skip 파일 | ✅ Yes (나머지 계속) |
| IRStage | Skip 파일 | ✅ Yes |
| SemanticIRStage | Skip 파일 | ✅ Yes |
| GraphStage | ERROR | ❌ No (critical) |
| ChunkStage | Skip 파일 | ✅ Yes |
| RepoMapStage | WARNING | ✅ Yes |
| IndexingStage | Retry 3회 | ❌ No (저장 실패) |

---

## 참고

### 구현 파일
```
src/contexts/analysis_indexing/infrastructure/stages/
├── base.py              # BaseStage 인터페이스
├── git_stage.py
├── discovery_stage.py
├── parsing_stage.py
├── ir_stage.py
├── graph_stage.py
├── chunk_stage.py
├── repomap_stage.py
└── indexing_stage.py
```

### 관련 문서
- `pipelines-detailed.md` - 파이프라인 엣지케이스
- `job-orchestrator.md` - Job 시스템
- `configuration.md` - Stage별 설정

---

**Last 
