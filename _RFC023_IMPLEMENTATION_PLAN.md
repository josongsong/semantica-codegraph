# RFC-023: Pyright Semantic Daemon 통합 - 상세 구현 계획

**Date:** 2024-11-25
**Status:** 📋 Planning Phase
**RFC:** RFC-023 - Pyright Semantic Daemon 통합 (High-Performance Mode)

---

## 📋 목차

1. [개요](#개요)
2. [현재 상태 분석](#현재-상태-분석)
3. [Phase 1: Semantic Daemon Core](#phase-1-semantic-daemon-core)
4. [Phase 2: Storage & Integration](#phase-2-storage--integration)
5. [Phase 3: Production Ready](#phase-3-production-ready)
6. [파일 구조](#파일-구조)
7. [API 스펙](#api-스펙)
8. [테스트 전략](#테스트-전략)
9. [마이그레이션 계획](#마이그레이션-계획)
10. [성능 목표](#성능-목표)

---

## 개요

### 목표

Python 코드베이스에 대해 **최대 성능(SOTA)**의 의미론적 분석을 확보하기 위해 Pyright를 **프로젝트 단위 증분 분석 + 장기 실행 데몬** 형태로 통합한다.

### 핵심 원칙

1. **분석은 항상 프로젝트 전체를 단위로 한다**
2. **비용은 Pyright 내부의 증분 분석에 의해 Δ에 비례한다**
3. **런타임 검색 시 Pyright 호출은 절대 금지한다**
4. **Semantic Snapshot은 "분석 시점의 단일 truth source"로 취급한다**

### 기대 효과

- CLI 호출 대비 **20~100배** 빠른 타입/심볼 분석
- 파일 Δ만 분석하므로 선형 증가가 아닌 Δ 증가
- Semantic Snapshot을 그대로 인덱싱하므로 **런타임 비용 0**
- SOTA IDE 수준 semantic 품질 확보 (VSCode Pyright와 동일)

---

## 현재 상태 분석

### ✅ 이미 구현된 것

| 구성요소 | 파일 | 상태 |
|---------|------|------|
| **Pyright LSP Client** | `src/foundation/ir/external_analyzers/pyright_lsp.py` | ✅ 완료 |
| **LSP 프로토콜** | - initialize/initialized | ✅ |
| **LSP API** | - textDocument/hover | ✅ |
| **LSP API** | - textDocument/definition | ✅ |
| **LSP API** | - textDocument/references | ✅ |
| **Document 관리** | - didOpen/didChange | ✅ 기본 구현 |
| **SemanticIrSnapshot** | `src/foundation/semantic_ir/context.py` | ⚠️ 다른 용도 |

### ❌ 구현 필요

| 구성요소 | 필요성 | Priority |
|---------|--------|----------|
| **update_files() API** | 증분 업데이트 | P0 |
| **analyze() API** | 프로젝트 분석 → snapshot_id | P0 |
| **export_semantic() API** | Snapshot export | P0 |
| **PyrightSemanticSnapshot** | RFC-023 스키마 | P0 |
| **SemanticSnapshotStore** | 저장/로드 | P0 |
| **Indexing 통합** | Pipeline 연결 | P0 |
| **Retriever 통합** | Snapshot 사용 | P1 |
| **증분 업데이트 최적화** | Δ만 재분석 | P1 |
| **Multi-project 지원** | 여러 repo 관리 | P2 |

### 🔄 재사용 가능한 코드

1. **PyrightLSPClient** (565 lines)
   - LSP 통신 인프라 완성
   - 백그라운드 스레드 응답 처리
   - Document 관리 (`_opened_documents`)
   - 캐싱 (`_hover_cache`)

2. **TypeResolver**
   - 타입 정규화 로직
   - Generic parameter parsing

3. **SemanticIrSnapshot** (context.py)
   - 구조는 재사용 가능
   - Pyright 특화 필드 추가 필요

---

## M0: Minimal Daemon (MVP)

**목표:** 최소 기능으로 동작하는 Daemon + Snapshot (1 file, in-memory only)

**기간:** 1-2일

**범위 제한:**
- ✅ 1개 파일만 지원
- ✅ In-memory snapshot (DB 없음)
- ✅ Indexing 시점에만 사용 (Retrieval 제외)
- ✅ IR에서 추출한 위치만 쿼리 (blind scan 금지)
- ❌ 증분 업데이트 제외
- ❌ Multi-file 제외
- ❌ PostgreSQL 제외

### M0.1 PyrightSemanticDaemon (Minimal)

**위치:** `src/foundation/ir/external_analyzers/pyright_daemon.py`

**책임:**
- PyrightLSPClient 재사용 (확장 안 함)
- 1개 파일에 대한 Snapshot 생성
- IR에서 제공한 위치만 쿼리 (N^2 방지)

**구현 작업:**

```python
class PyrightSemanticDaemon:
    """
    RFC-023 M0: Minimal Semantic Daemon

    제약:
    - 1 file만 지원
    - In-memory snapshot만
    - IR 제공 위치만 쿼리
    """

    def __init__(self, project_root: Path):
        self._lsp_client = PyrightLSPClient(project_root)
        self._current_snapshot: PyrightSemanticSnapshot | None = None

    # ✅ Task M0.1.1: open_file() - 단순화
    def open_file(self, file_path: Path, content: str) -> None:
        """
        1개 파일 열기

        Args:
            file_path: 파일 경로
            content: 파일 내용
        """
        # LSP: textDocument/didOpen
        # (PyrightLSPClient._ensure_document_opened 재사용)
        pass

    # ✅ Task M0.1.2: export_semantic_for_locations() - 핵심
    def export_semantic_for_locations(
        self,
        file_path: Path,
        locations: list[tuple[int, int]],  # [(line, col), ...]
    ) -> PyrightSemanticSnapshot:
        """
        특정 위치들에 대해서만 Semantic 정보 추출

        ⚠️ 중요: 전체 파일을 blind scan하지 않음!
        IR Generator가 제공한 위치(함수/클래스/변수)만 쿼리

        Args:
            file_path: 파일 경로
            locations: [(line, col), ...] ← IR에서 추출한 위치만!

        Returns:
            PyrightSemanticSnapshot (1 file, N locations)
        """
        snapshot = PyrightSemanticSnapshot(
            snapshot_id=f"snapshot-{time.time()}",
            project_id=self._lsp_client.project_root.name,
            files=[str(file_path)],
        )

        # 각 위치에 대해 hover 쿼리 (N회, not N^2)
        for line, col in locations:
            hover_result = self._lsp_client.hover(file_path, line, col)
            if hover_result:
                span = Span(line, col, line, col)  # 간단히 point로
                snapshot.typing_info[(str(file_path), span)] = hover_result["type"]

        return snapshot

    # ✅ Task M0.1.3: shutdown()
    def shutdown(self):
        """LSP 클라이언트 종료"""
        self._lsp_client.shutdown()
```

**세부 작업:**

- [ ] **Task M0.1.1**: `open_file()` 구현
  - PyrightLSPClient의 `_ensure_document_opened()` 재사용
  - 1개 파일만 관리

- [ ] **Task M0.1.2**: `export_semantic_for_locations()` 구현 (핵심)
  - IR에서 제공한 위치만 쿼리 (N회)
  - Blind scan 금지 (N^2 방지)
  - In-memory snapshot 생성

- [ ] **Task M0.1.3**: `shutdown()` 구현
  - LSP 클라이언트 정리

### M0.2 PyrightSemanticSnapshot (Minimal)

**위치:** `src/foundation/ir/external_analyzers/snapshot.py`

**M0 범위:**
- ✅ TypingInfo만 (SignatureInfo, SymbolInfo, FlowFacts 제외)
- ✅ 간단한 Span (point만)
- ❌ JSON 직렬화 제외 (in-memory만)
- ❌ 검증 로직 제외

**구현 작업:**

```python
@dataclass
class Span:
    """코드 위치 (line/column 기반) - M0: 간단한 point"""
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def __hash__(self):
        return hash((self.start_line, self.start_col, self.end_line, self.end_col))

    def __eq__(self, other):
        if not isinstance(other, Span):
            return False
        return (
            self.start_line == other.start_line
            and self.start_col == other.start_col
            and self.end_line == other.end_line
            and self.end_col == other.end_col
        )


@dataclass
class PyrightSemanticSnapshot:
    """
    RFC-023 M0: Minimal Semantic Snapshot

    제약:
    - TypingInfo만 지원
    - In-memory only (직렬화 없음)
    - 1 file만
    """
    snapshot_id: str
    project_id: str
    files: list[str]  # M0: 1개만

    # M0: TypingInfo만
    typing_info: dict[tuple[str, Span], str] = field(default_factory=dict)
    # 예: {("main.py", Span(10, 5, 10, 5)): "list[User]"}

    # M1+: 나중에 추가
    # signature_info: dict[tuple[str, Span], PyrightSignature] = field(default_factory=dict)
    # symbol_info: dict[str, PyrightSymbol] = field(default_factory=dict)
    # flow_facts: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)

    def get_type_at(self, file_path: str, span: Span) -> str | None:
        """타입 조회 (O(1) lookup)"""
        return self.typing_info.get((file_path, span))
```

**세부 작업:**

- [ ] **Task M0.2.1**: `Span` dataclass 정의 (해싱 포함)
- [ ] **Task M0.2.2**: `PyrightSemanticSnapshot` 정의 (TypingInfo만)
- [ ] **Task M0.2.3**: `get_type_at()` 조회 메서드

### M0.3 통합 테스트 (Minimal)

**위치:** `tests/foundation/test_pyright_daemon_m0.py`

**M0 테스트 범위:**
- ✅ 1 file만
- ✅ TypingInfo만
- ❌ 증분 업데이트 제외
- ❌ 직렬화 제외

**테스트 케이스:**

- [ ] **Test M0.3.1**: `test_daemon_open_file`
  - 1개 파일 열기 + LSP 초기화 확인

- [ ] **Test M0.3.2**: `test_export_semantic_for_locations`
  - 특정 위치들에 대한 typing 정보 추출
  - 5개 위치 → 5개 hover 쿼리 → Snapshot 생성

- [ ] **Test M0.3.3**: `test_typing_info_basic_types`
  - builtin types (int, str, list, dict)

- [ ] **Test M0.3.4**: `test_typing_info_generic_types`
  - List[User], Dict[str, int], Optional[T]

- [ ] **Test M0.3.5**: `test_snapshot_lookup`
  - `get_type_at()` 조회 성능 (O(1))

---

### M0.4 Indexing 통합 (Proof of Concept)

**목표:** 1개 파일 인덱싱에 Pyright Daemon 적용

**위치:** `examples/m0_pyright_indexing_poc.py`

**구현 작업:**

```python
# M0 PoC: 1개 파일에 대한 Pyright 통합

from pathlib import Path
from src.foundation.ir.external_analyzers import PyrightSemanticDaemon
from src.foundation.parsing import SourceFile, get_registry
from src.foundation.generators import PythonIRGenerator

# 1. Parse
parser = get_registry().get_parser("python")
source = SourceFile("example.py", code, "python")
ast_tree = parser.parse(source)

# 2. Generate IR
ir_generator = PythonIRGenerator("demo-repo")
ir_doc = ir_generator.generate(source, "snapshot-1")

# 3. Extract locations from IR (함수/클래스/변수만)
locations = []
for node in ir_doc.nodes:
    if node.kind in ["FUNCTION", "CLASS", "VARIABLE"]:
        locations.append((node.span.start_line, node.span.start_col))

# 4. Pyright Daemon: Export semantic for locations
daemon = PyrightSemanticDaemon(Path.cwd())
daemon.open_file(Path("example.py"), code)
snapshot = daemon.export_semantic_for_locations(
    Path("example.py"),
    locations  # ← IR에서 추출한 위치만!
)

# 5. Augment IR with Pyright types
for node in ir_doc.nodes:
    span = Span(node.span.start_line, node.span.start_col, ...)
    pyright_type = snapshot.get_type_at("example.py", span)
    if pyright_type:
        node.attrs["pyright_type"] = pyright_type

# 6. Cleanup
daemon.shutdown()

print(f"✅ Augmented {len(locations)} nodes with Pyright types")
```

**세부 작업:**

- [ ] **Task M0.4.1**: PoC 스크립트 작성
- [ ] **Task M0.4.2**: IR → locations 추출 로직
- [ ] **Task M0.4.3**: Snapshot → IR augmentation
- [ ] **Task M0.4.4**: 성능 측정 (1 file, N nodes)

---

## M1: Multi-file + Storage

**목표:** 여러 파일 지원 + PostgreSQL 저장

**기간:** 2-3일

**M1 추가 기능:**
- ✅ 여러 파일 동시 처리
- ✅ PostgreSQL에 Snapshot 저장
- ✅ Snapshot 로드/조회
- ❌ 증분 업데이트 제외 (M2)

### M1.1 Multi-file 지원

**구현 작업:**

```python
class PyrightSemanticDaemon:
    # M1: 여러 파일 지원
    def open_files(self, files: list[tuple[Path, str]]) -> None:
        """여러 파일 동시 열기"""
        pass

    def export_semantic_for_files(
        self,
        file_locations: dict[Path, list[tuple[int, int]]],
    ) -> PyrightSemanticSnapshot:
        """
        여러 파일에 대한 Semantic 정보 추출

        Args:
            file_locations: {file_path: [(line, col), ...]}
        """
        pass
```

**세부 작업:**

- [ ] **Task M1.1.1**: `open_files()` 구현 (여러 파일)
- [ ] **Task M1.1.2**: `export_semantic_for_files()` 구현
- [ ] **Task M1.1.3**: 성능 측정 (10 files, 100 locations)

### M1.2 SemanticSnapshotStore (PostgreSQL)

**위치:** `src/foundation/ir/external_analyzers/snapshot_store.py`

**책임:**
- Semantic Snapshot 영구 저장 (PostgreSQL)
- 간단한 조회 (프로젝트별 최신 snapshot)

**M1 범위:**
- ✅ 저장/로드
- ❌ 버전 비교 제외 (M2)
- ❌ 롤백 제외 (M2)

**구현 작업:**

```python
class SemanticSnapshotStore:
    """
    Semantic Snapshot 영구 저장소

    PostgreSQL에 JSON 형태로 저장
    """

    def __init__(self, postgres_store: PostgresStore):
        self.postgres = postgres_store
        self._cache: dict[str, PyrightSemanticSnapshot] = {}

    # ✅ Task M1.2.1: save_snapshot()
    async def save_snapshot(self, snapshot: PyrightSemanticSnapshot) -> None:
        """
        Snapshot 저장

        M1: 간단한 저장만 (JSONB)
        """
        pass

    # ✅ Task M1.2.2: load_latest_snapshot()
    async def load_latest_snapshot(self, project_id: str) -> PyrightSemanticSnapshot | None:
        """최신 snapshot 로드"""
        pass
```

**세부 작업:**

- [ ] **Task M1.2.1**: PostgreSQL 테이블 마이그레이션
  ```sql
  CREATE TABLE pyright_semantic_snapshots (
      snapshot_id TEXT PRIMARY KEY,
      project_id TEXT NOT NULL,
      timestamp TIMESTAMP NOT NULL,
      data JSONB NOT NULL,
      created_at TIMESTAMP DEFAULT NOW()
  );
  CREATE INDEX idx_snapshots_project ON pyright_semantic_snapshots(project_id, timestamp DESC);
  ```

- [ ] **Task M1.2.2**: `save_snapshot()` 구현 (JSON 직렬화 추가)
- [ ] **Task M1.2.3**: `load_latest_snapshot()` 구현
- [ ] **Task M1.2.4**: 통합 테스트 (저장 → 로드 → 검증)

### 2.2 IndexingOrchestrator 통합

**위치:** `src/indexing/orchestrator.py` (수정)

**목표:** Pyright Daemon을 파이프라인에 통합

**구현 작업:**

```python
class IndexingOrchestrator:
    def __init__(
        self,
        pyright_daemon: PyrightSemanticDaemon | None = None,  # ← 추가
        snapshot_store: SemanticSnapshotStore | None = None,  # ← 추가
        ...
    ):
        self.pyright_daemon = pyright_daemon
        self.snapshot_store = snapshot_store

    # ✅ Task 2.2.1: index_repo_full() 수정
    async def index_repo_full(
        self,
        repo_id: str,
        files: list[Path],
        enable_pyright: bool = True,  # ← 추가
    ) -> dict:
        """
        전체 repo 인덱싱 (Pyright Semantic Snapshot 생성 포함)
        """
        # 1. Pyright 분석 (optional)
        semantic_snapshot = None
        if enable_pyright and self.pyright_daemon:
            semantic_snapshot = await self._run_pyright_analysis(repo_id, files)

        # 2. 기존 파이프라인 (Parsing → IR → Semantic IR → Graph → Chunk)
        # ... (기존 코드)

        # 3. Semantic augmentation (snapshot 활용)
        if semantic_snapshot:
            graph = self._augment_graph_with_semantics(graph, semantic_snapshot)
            chunks = self._augment_chunks_with_semantics(chunks, semantic_snapshot)

        # 4. Indexing
        # ... (기존 코드)

        return {"snapshot_id": semantic_snapshot.snapshot_id if semantic_snapshot else None}

    # ✅ Task 2.2.2: _run_pyright_analysis() 헬퍼
    async def _run_pyright_analysis(
        self,
        repo_id: str,
        files: list[Path],
    ) -> PyrightSemanticSnapshot:
        """Pyright Daemon으로 전체 프로젝트 분석"""
        pass

    # ✅ Task 2.2.3: _augment_graph_with_semantics()
    async def _augment_graph_with_semantics(
        self,
        graph: GraphDocument,
        snapshot: PyrightSemanticSnapshot,
    ) -> GraphDocument:
        """Graph에 semantic 정보 추가"""
        pass

    # ✅ Task 2.2.4: _augment_chunks_with_semantics()
    async def _augment_chunks_with_semantics(
        self,
        chunks: list[Chunk],
        snapshot: PyrightSemanticSnapshot,
    ) -> list[Chunk]:
        """Chunk에 semantic 정보 추가"""
        pass
```

**세부 작업:**

- [ ] **Task 2.2.1**: `index_repo_full()` 수정 (Pyright 통합)
- [ ] **Task 2.2.2**: `_run_pyright_analysis()` 구현
- [ ] **Task 2.2.3**: Graph augmentation 로직
- [ ] **Task 2.2.4**: Chunk augmentation 로직
- [ ] **Task 2.2.5**: Snapshot 저장 로직

### 2.3 Container 통합

**위치:** `src/container.py` (수정)

**구현 작업:**

```python
class Container:
    @cached_property
    def pyright_daemon(self) -> PyrightSemanticDaemon | None:
        """Pyright Semantic Daemon (선택적)"""
        if not settings.enable_pyright:
            return None

        from src.foundation.ir.external_analyzers import PyrightSemanticDaemon

        return PyrightSemanticDaemon(
            project_root=settings.project_root or Path.cwd(),
        )

    @cached_property
    def snapshot_store(self) -> SemanticSnapshotStore:
        """Semantic Snapshot Store"""
        from src.foundation.ir.external_analyzers import SemanticSnapshotStore

        return SemanticSnapshotStore(
            postgres_store=self.postgres,
        )

    @cached_property
    def indexing_orchestrator_new(self):
        from src.indexing import IndexingConfig, IndexingOrchestrator

        return IndexingOrchestrator(
            # ... 기존 params
            pyright_daemon=self.pyright_daemon,  # ← 추가
            snapshot_store=self.snapshot_store,  # ← 추가
            config=IndexingConfig(),
        )
```

**세부 작업:**

- [ ] **Task 2.3.1**: Settings에 `enable_pyright` 추가
- [ ] **Task 2.3.2**: `pyright_daemon` 의존성 추가
- [ ] **Task 2.3.3**: `snapshot_store` 의존성 추가

### 2.4 통합 테스트

**위치:** `tests/integration/test_pyright_pipeline.py`

**테스트 케이스:**

- [ ] **Test 2.4.1**: `test_full_indexing_with_pyright`
  - 전체 파이프라인 (Pyright 포함)

- [ ] **Test 2.4.2**: `test_snapshot_persistence`
  - Snapshot 저장 → 로드 → 검증

- [ ] **Test 2.4.3**: `test_graph_augmentation`
  - Graph에 semantic 정보 추가 확인

- [ ] **Test 2.4.4**: `test_chunk_augmentation`
  - Chunk에 semantic 정보 추가 확인

---

---

## M2: 증분 업데이트

**목표:** Δ 파일만 재분석하여 성능 향상

**기간:** 2-3일

**M2 추가 기능:**
- ✅ 변경된 파일만 재분석
- ✅ Snapshot delta 계산
- ✅ 선택적 재인덱싱

---

## M3: Production Ready

**목표:** 모니터링, Health Check, Multi-project

**기간:** 2-3일

### M3.1 Monitoring & Health Check

**구현 작업:**

```python
class PyrightSemanticDaemon:
    # ✅ Task M3.1.1: Health check
    def health_check(self) -> dict:
        """Daemon 상태 확인"""
        return {
            "status": "healthy" if self._lsp_client._initialized else "unhealthy",
            "files_opened": len(self._lsp_client._opened_documents),
            "cache_size": len(self._lsp_client._hover_cache),
        }
```

**세부 작업:**

- [ ] **Task M3.1.1**: Health check 구현
- [ ] **Task M3.1.2**: 메트릭 수집 (hover query count, cache hit rate)
- [ ] **Task M3.1.3**: 로깅 강화

---

## 파일 구조

```
src/foundation/ir/external_analyzers/
├── __init__.py                      # 기존
├── base.py                          # 기존
├── pyright_adapter.py               # 기존 (deprecated)
├── pyright_lsp.py                   # 기존 (재사용)
├── pyright_daemon.py                # ⭐ NEW (Phase 1)
├── snapshot.py                      # ⭐ NEW (Phase 1)
└── snapshot_store.py                # ⭐ NEW (Phase 2)

migrations/
└── 005_create_pyright_snapshots.sql # ⭐ NEW (Phase 2)

tests/foundation/
├── test_pyright_daemon.py           # ⭐ NEW (Phase 1)
└── test_snapshot_store.py           # ⭐ NEW (Phase 2)

tests/integration/
└── test_pyright_pipeline.py         # ⭐ NEW (Phase 2)

examples/
└── pyright_daemon_example.py        # ⭐ NEW (Phase 1)

_docs/
└── RFC023_IMPLEMENTATION_PLAN.md    # 이 문서
```

---

## API 스펙

### PyrightSemanticDaemon

```python
class PyrightSemanticDaemon:
    # Lifecycle
    def __init__(project_root: Path)
    def shutdown()
    def health_check() -> dict

    # Core API (RFC-023)
    def update_files(files: list[tuple[Path, str]], mode: str) -> None
    def analyze() -> str  # → snapshot_id
    def export_semantic(snapshot_id: str) -> PyrightSemanticSnapshot

    # Helper
    def _collect_all_symbols(file_path: Path) -> list[SymbolInfo]
    def _batch_hover_queries(queries: list) -> dict
```

### SemanticSnapshotStore

```python
class SemanticSnapshotStore:
    # CRUD
    async def save_snapshot(snapshot: PyrightSemanticSnapshot) -> None
    async def load_latest_snapshot(project_id: str) -> PyrightSemanticSnapshot | None
    async def load_snapshot_by_id(snapshot_id: str) -> PyrightSemanticSnapshot | None
    async def list_snapshots(project_id: str, limit: int) -> list[dict]
    async def delete_old_snapshots(project_id: str, keep_count: int) -> int

    # Advanced
    async def compare_snapshots(id1: str, id2: str) -> dict
    async def rollback_to_snapshot(project_id: str, snapshot_id: str) -> None
```

### IndexingOrchestrator (수정)

```python
class IndexingOrchestrator:
    # Full indexing (with Pyright)
    async def index_repo_full(
        repo_id: str,
        files: list[Path],
        enable_pyright: bool = True,
    ) -> dict

    # Incremental indexing (Δ only)
    async def index_repo_incremental(
        repo_id: str,
        changed_files: list[Path],
        deleted_files: list[Path],
    ) -> dict
```

---

## 테스트 전략

### Unit Tests

| 파일 | 테스트 수 | Coverage 목표 |
|------|----------|---------------|
| `test_pyright_daemon.py` | 6 | 90%+ |
| `test_snapshot_store.py` | 5 | 90%+ |
| `test_snapshot.py` | 4 | 95%+ |

### Integration Tests

| 파일 | 테스트 수 | 설명 |
|------|----------|------|
| `test_pyright_pipeline.py` | 4 | 전체 파이프라인 E2E |

### Performance Tests

| 벤치마크 | 목표 | 측정 항목 |
|---------|------|----------|
| `benchmark_daemon_analysis.py` | 2-5초 | 213 files 전체 분석 |
| `benchmark_incremental_update.py` | <500ms | 1 file 변경 시 재분석 |
| `benchmark_snapshot_export.py` | <1초 | Snapshot export 시간 |

---

## 마이그레이션 계획

### 기존 코드와의 호환성

**Old (Per-Query 패턴):**
```python
# 검색할 때마다 Pyright 호출 (느림)
type_info = pyright_client.hover(file, line, col)
```

**New (Snapshot 패턴):**
```python
# Snapshot에서 lookup (instant)
snapshot = snapshot_store.load_latest(project_id)
type_info = snapshot.typing_info.get((file, span))
```

### 단계적 마이그레이션

1. **Phase 1-2**: New 패턴 구현 (Old 패턴 유지)
2. **Phase 3**: Old 패턴 deprecated 경고 추가
3. **Phase 4**: Old 패턴 제거 (breaking change)

### 설정 관리

```python
# settings.py
ENABLE_PYRIGHT = os.getenv("ENABLE_PYRIGHT", "false").lower() == "true"
PYRIGHT_SNAPSHOT_RETENTION = int(os.getenv("PYRIGHT_SNAPSHOT_RETENTION", "5"))
```

---

## 성능 목표 (수정)

### M0: 1 file

| Metric | Target |
|--------|--------|
| 1 file (10 nodes) | **<500ms** |
| Hover queries (N) | **<50ms × N** |
| Snapshot lookup | **<1ms** |

### M1: Multi-file

| Metric | Target |
|--------|--------|
| 10 files (100 nodes) | **<5초** |
| Snapshot 저장 (PostgreSQL) | **<200ms** |
| Snapshot 로드 | **<100ms** |

### M2: 증분 업데이트

| Metric | Target |
|--------|--------|
| Δ 1 file 재분석 | **<1초** |
| Snapshot delta 계산 | **<50ms** |

### M3: Production

| Metric | Target |
|--------|--------|
| Health check | **<10ms** |
| Daemon uptime | **>24h** |

---

## 체크리스트 (수정)

### M0: Minimal Daemon (1-2일) ⭐ START HERE

- [ ] Task M0.1.1: `open_file()` 구현
- [ ] Task M0.1.2: `export_semantic_for_locations()` 구현 (핵심)
- [ ] Task M0.1.3: `shutdown()` 구현
- [ ] Task M0.2.1: `Span` dataclass
- [ ] Task M0.2.2: `PyrightSemanticSnapshot` (TypingInfo만)
- [ ] Task M0.2.3: `get_type_at()` 조회
- [ ] Test M0.3.1-M0.3.5: 통합 테스트 (5개)
- [ ] Task M0.4.1-M0.4.4: Indexing PoC

### M1: Multi-file + Storage (2-3일)

- [ ] Task M1.1.1-M1.1.3: Multi-file 지원
- [ ] Task M1.2.1: PostgreSQL 마이그레이션
- [ ] Task M1.2.2-M1.2.4: SemanticSnapshotStore 구현
- [ ] JSON 직렬화/역직렬화 추가

### M2: 증분 업데이트 (2-3일)

- [ ] Δ 파일만 재분석
- [ ] Snapshot delta 계산
- [ ] 성능 벤치마크

### M3: Production (2-3일)

- [ ] Task M3.1.1-M3.1.3: Monitoring
- [ ] Health check API
- [ ] 자동 재시작 (optional)

---

## 다음 단계

1. ✅ 이 계획 문서 리뷰 및 승인
2. Phase 1 시작: `PyrightSemanticDaemon` 구현
3. 각 Phase 완료 후 성능 측정 및 문서화
4. Production 배포 및 모니터링

---

**End of Implementation Plan**
