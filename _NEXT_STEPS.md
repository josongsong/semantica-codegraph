# Semantica CodeGraph v2 - 다음 단계 🚀

**현재 상태 요약일**: 2025-11-24
**전체 완성도**: ~95%

---

## ✅ 완료된 주요 컴포넌트

### Foundation Layer (100% 완료)
- ✅ Parsing (Tree-sitter)
- ✅ IR (Intermediate Representation)
- ✅ Semantic IR (CFG, DFG, Type System, Signature)
- ✅ Graph Construction
- ✅ Chunk Layer (90% - 증분 업데이트 포함)

### Index Layer (98% 완료)
- ✅ Lexical Index (Zoekt adapter)
- ✅ Vector Index (Qdrant adapter)
- ✅ Symbol Index (Kuzu adapter)
- ✅ Fuzzy Index (pg_trgm)
- ✅ Domain Metadata Index
- ⚠️ Runtime Index (구조만 있음, 실제 trace 수집 미구현)

### Retriever Layer (100% 완료)
- ✅ Phase 1: MVP (Intent, Scope, Multi-index, Fusion, Context)
- ✅ Phase 2: Enhanced SOTA (Late Interaction, Cross-encoder, Correlation, Hard Negatives)
- ✅ Phase 3: Advanced SOTA (Multi-hop, Reasoning, Observability, Code Reranking, Adaptive Embeddings)
- ✅ Production Adapters (Kuzu, OpenAI)
- ✅ Integration Tests (43 tests)

### RepoMap Layer (100% 완료)
- ✅ Tree Builder
- ✅ PageRank Engine
- ✅ LLM Summarizer
- ✅ Incremental Updates
- ✅ Storage (Postgres)

### Infrastructure (100% 완료)
- ✅ Kuzu Graph Store
- ✅ Qdrant Vector Store
- ✅ Postgres Storage
- ✅ Redis Cache
- ✅ OpenAI/LiteLLM Integration

### Servers (100% 완료)
- ✅ API Server (FastAPI)
- ✅ MCP Server (Model Context Protocol)

---

## 🎯 다음 단계 우선순위

### Priority 1: Indexing Orchestration (핵심!)
**현재 상태**: 각 컴포넌트는 완성되었지만, **전체 인덱싱 파이프라인 오케스트레이션**이 없음

**필요한 작업**:

1. **Indexing Orchestrator 구현**
   - 위치: `src/indexing/orchestrator.py`
   - 역할:
     ```
     Repo Clone/Fetch
       ↓
     Parse (Tree-sitter)
       ↓
     Generate IR + Semantic IR
       ↓
     Build Graph
       ↓
     Generate Chunks
       ↓
     Build RepoMap (with PageRank & Summarization)
       ↓
     Index All (Lexical + Vector + Symbol + Fuzzy + Domain)
       ↓
     Complete!
     ```

2. **Incremental Indexing Pipeline**
   - Git diff 감지
   - 변경된 파일만 재파싱
   - Affected chunks 재생성
   - Graph 증분 업데이트
   - RepoMap 증분 업데이트
   - Index 증분 업데이트

3. **CLI Interface**
   ```bash
   # Full indexing
   semantica index --repo /path/to/repo

   # Incremental indexing
   semantica index --repo /path/to/repo --incremental

   # Status check
   semantica status --repo /path/to/repo
   ```

**예상 작업량**: 2-3일

---

### Priority 2: End-to-End Integration Tests
**현재 상태**: 각 레이어별 테스트는 있지만, **전체 파이프라인 E2E 테스트**가 없음

**필요한 작업**:

1. **Full Pipeline Test**
   ```python
   # tests/integration/test_full_pipeline.py

   async def test_end_to_end_indexing():
       # 1. Index 샘플 레포
       await orchestrator.index_repo(repo_path)

       # 2. 검색 테스트 (모든 index)
       lexical_results = await retriever.search(query="auth", source="lexical")
       vector_results = await retriever.search(query="authentication", source="vector")
       symbol_results = await retriever.search(query="def authenticate", source="symbol")

       # 3. Multi-hop 검색
       result = await multi_hop.retrieve_multi_hop(...)

       # 4. 결과 검증
       assert len(result.all_results) > 0
   ```

2. **Real Repository Tests**
   - Small repo (50-100 files): 빠른 테스트용
   - Medium repo (1000+ files): 실제 성능 측정
   - 여러 언어 지원 검증 (Python, TypeScript, JavaScript)

3. **Performance Benchmarks**
   - Indexing 속도: files/sec
   - Query latency: P50, P95, P99
   - Memory usage
   - Storage size

**예상 작업량**: 1-2일

---

### Priority 3: CLI & User Interface
**현재 상태**: API는 있지만 사용하기 쉬운 **CLI 인터페이스**가 부족

**필요한 작업**:

1. **CLI 명령어 구현**
   ```bash
   # Indexing
   semantica index <repo_path> [--incremental] [--force]

   # Search
   semantica search <query> --repo <repo_id> [--source lexical|vector|symbol]

   # RepoMap
   semantica map <repo_id> [--depth 2] [--importance-threshold 0.5]

   # Status & Diagnostics
   semantica status <repo_id>
   semantica stats <repo_id>  # Show index sizes, chunk counts, etc.

   # Server
   semantica serve [--host 0.0.0.0] [--port 8000]
   ```

2. **Interactive REPL Mode** (선택사항)
   ```bash
   semantica shell <repo_id>
   > search: authentication function
   > map: backend/auth
   > explain: why chunk_123 ranked high?
   ```

3. **Configuration Management**
   ```yaml
   # semantica.yaml
   repos:
     - path: /path/to/repo1
       id: repo1
       languages: [python, typescript]

   indexing:
     parallel: true
     max_workers: 4

   retriever:
     default_sources: [lexical, vector, symbol]
     fusion_weights:
       lexical: 0.25
       vector: 0.25
       symbol: 0.25
   ```

**예상 작업량**: 2-3일

---

### Priority 4: Documentation & Examples
**현재 상태**: 코드 문서는 있지만 **사용자 가이드**가 부족

**필요한 작업**:

1. **Getting Started Guide**
   - Installation
   - First indexing
   - First search
   - Configuration

2. **API Documentation**
   - REST API reference
   - MCP protocol guide
   - Python SDK examples

3. **Architecture Documentation**
   - System overview
   - Data flow diagrams
   - Performance tuning guide

4. **Example Projects**
   - `examples/simple_search/`
   - `examples/multi_hop_query/`
   - `examples/custom_reranker/`

**예상 작업량**: 2-3일

---

## 🚧 선택적 개선 사항 (Optional)

### Agent Layer (Phase 4)
LLM Agent가 검색 결과를 바탕으로 코드 이해/생성/수정하는 레이어

**Features**:
- Code Understanding Agent (코드 설명)
- Code Generation Agent (코드 생성)
- Code Modification Agent (코드 수정)
- Testing Agent (테스트 생성)

**예상 작업량**: 1-2주

---

### Web UI Dashboard
Observability 시각화를 위한 웹 인터페이스

**Features**:
- Indexing status monitor
- Search result explorer
- RepoMap tree visualizer
- Performance metrics dashboard
- Query analyzer (explain why results ranked)

**Tech Stack**: React + FastAPI
**예상 작업량**: 1주

---

### Advanced Features

1. **Multi-Repo Support**
   - Cross-repo symbol resolution
   - Monorepo support
   - Dependency graph across repos

2. **Language Support Expansion**
   - Java
   - Go
   - Rust
   - C/C++

3. **Runtime Analysis Integration**
   - APM trace ingestion
   - Hot path detection
   - Error correlation

4. **Team Collaboration Features**
   - Shared annotations
   - Code review integration
   - Knowledge base building

---

## 📋 구현 순서 제안

### 빠른 MVP (1주):
```
Day 1-2: Indexing Orchestrator 구현
Day 3-4: E2E Integration Tests
Day 5-6: CLI 기본 명령어
Day 7: Documentation & Examples
```

### 완성형 (2-3주):
```
Week 1: Indexing Orchestrator + E2E Tests + CLI
Week 2: Documentation + Performance Tuning + Bug Fixes
Week 3: Web UI Dashboard (선택사항)
```

---

## 🎯 즉시 시작 가능한 작업

### 1. Indexing Orchestrator (최우선!)

```python
# src/indexing/orchestrator.py

class IndexingOrchestrator:
    """Orchestrates the entire indexing pipeline."""

    def __init__(
        self,
        parser_registry,
        ir_builder,
        semantic_ir_builder,
        graph_builder,
        chunk_builder,
        repomap_builder,
        index_service,
    ):
        self.parser_registry = parser_registry
        self.ir_builder = ir_builder
        # ... all builders

    async def index_repository(
        self,
        repo_path: str,
        repo_id: str,
        snapshot_id: str = "main",
        incremental: bool = False,
    ) -> IndexingResult:
        """Full indexing pipeline."""

        # 1. Git operations
        if not incremental:
            await self._clone_or_fetch(repo_path)

        # 2. Determine files to process
        if incremental:
            files = await self._get_changed_files(repo_path, snapshot_id)
        else:
            files = await self._get_all_source_files(repo_path)

        # 3. Parse files
        ast_results = await self._parse_files(files)

        # 4. Generate IR
        ir_doc = await self.ir_builder.build(ast_results)

        # 5. Generate Semantic IR
        semantic_ir = await self.semantic_ir_builder.build(ir_doc)

        # 6. Build Graph
        graph_doc = await self.graph_builder.build(semantic_ir)

        # 7. Generate Chunks
        chunks = await self.chunk_builder.build(graph_doc, ir_doc)

        # 8. Build RepoMap
        repomap = await self.repomap_builder.build(
            repo_id, snapshot_id, chunks, graph_doc
        )

        # 9. Index everything
        await self.index_service.index_all(
            repo_id, snapshot_id, chunks, repomap
        )

        return IndexingResult(
            repo_id=repo_id,
            snapshot_id=snapshot_id,
            files_processed=len(files),
            chunks_created=len(chunks),
            graph_nodes=len(graph_doc.nodes),
            duration_seconds=elapsed,
        )
```

### 2. CLI Entry Point

```python
# src/cli/main.py

import typer
from rich.console import Console

app = typer.Typer()
console = Console()

@app.command()
def index(
    repo_path: str,
    incremental: bool = False,
    force: bool = False,
):
    """Index a repository."""
    console.print(f"[bold]Indexing repository:[/bold] {repo_path}")

    orchestrator = IndexingOrchestrator(...)
    result = asyncio.run(
        orchestrator.index_repository(
            repo_path=repo_path,
            repo_id=generate_repo_id(repo_path),
            incremental=incremental,
        )
    )

    console.print(f"[green]✓[/green] Indexed {result.files_processed} files")
    console.print(f"[green]✓[/green] Created {result.chunks_created} chunks")

@app.command()
def search(
    query: str,
    repo_id: str,
    source: str = "all",
):
    """Search in a repository."""
    # ... search implementation

if __name__ == "__main__":
    app()
```

### 3. E2E Test

```python
# tests/integration/test_full_pipeline.py

import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_full_indexing_and_search():
    """Test complete pipeline from indexing to search."""

    # Setup test repo
    test_repo = Path("tests/fixtures/sample_repo")

    # 1. Index
    orchestrator = IndexingOrchestrator(...)
    result = await orchestrator.index_repository(
        repo_path=str(test_repo),
        repo_id="test_repo",
        snapshot_id="main",
    )

    assert result.files_processed > 0
    assert result.chunks_created > 0

    # 2. Search (Lexical)
    retriever = RetrieverService(...)
    lexical_results = await retriever.retrieve(
        repo_id="test_repo",
        snapshot_id="main",
        query="authentication function",
        sources=["lexical"],
    )

    assert len(lexical_results.chunks) > 0

    # 3. Search (Vector)
    vector_results = await retriever.retrieve(
        repo_id="test_repo",
        snapshot_id="main",
        query="how does authentication work?",
        sources=["vector"],
    )

    assert len(vector_results.chunks) > 0

    # 4. Multi-hop
    multi_hop = MultiHopRetriever(...)
    decomposed = await decomposer.decompose(
        "Find authentication function and show all its usages"
    )
    multi_hop_result = await multi_hop.retrieve_multi_hop(
        repo_id="test_repo",
        snapshot_id="main",
        decomposed=decomposed,
    )

    assert len(multi_hop_result.step_results) == 2
```

---

## 🎯 권장 시작 포인트

**1단계: Indexing Orchestrator** (가장 중요!)
- 모든 컴포넌트가 완성되었지만 이를 연결하는 파이프라인이 없음
- 이것이 완성되면 실제로 사용 가능한 시스템이 됨

**2단계: CLI**
- 사용자가 쉽게 사용할 수 있는 인터페이스 제공
- `semantica index /path/to/repo` 한 줄로 전체 파이프라인 실행

**3단계: E2E Tests**
- 전체 시스템이 제대로 동작하는지 검증
- 리그레션 방지

---

**지금 바로 시작할 작업**:
1️⃣ **Indexing Orchestrator** 구현을 추천합니다!

이것만 완성하면 Semantica CodeGraph v2가 실제로 동작하는 완전한 시스템이 됩니다. 🚀
