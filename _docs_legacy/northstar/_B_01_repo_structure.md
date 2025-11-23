Semantica Codegraph Repository Structure
0. Architectural Overview
This project follows a Modern Hexagonal Architecture (Clean Architecture). The primary goal is to decouple Business Logic (Core) from External Interfaces (API/MCP) and Infrastructure (DB/Git).

Dependency Rules (Strict)
Interfaces depends on Core

Infra depends on Core

Core depends on Nothing (Pure Python & Pydantic)

Core MUST NOT import from Infra or Interfaces


1. Directory Tree Map
codegraph/
  config.py                       # 전역 설정 (Pydantic Settings)
  container.py                    # DI 컨테이너 (포트↔어댑터 바인딩)

  interfaces/                     # [Presentation Layer] 외부 인터페이스
    __init__.py
    api/                          # HTTP (FastAPI)
      __init__.py
      main.py                     # FastAPI app 엔트리포인트
      dependencies.py             # FastAPI Depends() → core.services 주입
      routers/
        __init__.py
        search.py                 # /api/search/...
        index.py                  # /api/index/...
        graph.py                  # /api/graph/...
        repos.py                  # /api/repos/...
        chunks.py                 # /api/chunks/...
        nodes.py                  # /api/nodes/...
      schemas/                    # HTTP용 Request/Response DTO
        __init__.py
        search_schema.py
        index_schema.py
        graph_schema.py
        repo_schema.py
        node_schema.py
        chunk_schema.py

    mcp/                          # MCP Server (Claude/Agent 등)
      __init__.py
      server.py                   # MCP 엔트리포인트
      tools/                      # MCP 툴 구현 (code search / graph / index 등)
        __init__.py
        code_search_tool.py
        graph_tool.py
        index_tool.py

  core/                           # [Business Logic Layer] Codegraph 엔진
    __init__.py

    domain/                       # 1) 순수 도메인 모델 (로직 없음)
      __init__.py
      nodes.py                    # BaseNode, Repo/Project/File/Symbol 노드
      chunks.py                   # CanonicalLeafChunk, LeafChunk, VectorPayload 등
      graph.py                    # RelationshipType, Relationship
      context.py                  # GitContext, SecurityContext, RuntimeStats
      events.py                   # RepoIndexed, BranchSynced, SearchExecuted 등

    ports/                        # 2) Ports (추상 인터페이스)
      __init__.py
      vector_store.py             # Vector DB 인터페이스
      graph_store.py              # Graph/관계 저장 인터페이스
      relational_store.py         # RDB (Node/Chunk 메타) 인터페이스
      git_provider.py             # Git (diff/log/blame/branch) 인터페이스
      llm_provider.py             # LLM/Embedding 인터페이스
      lexical_search_port.py      # Meili/ES 등 텍스트 검색 인터페이스

    services/                     # 3) Application Services (유즈케이스 오케스트레이션)
      __init__.py
      ingestion/                  # 파싱 + 청킹 파이프라인
        __init__.py
        parser.py                 # Tree-sitter 기반 파서
        chunker.py                # 코드 청킹 전략 (SOTA LeafChunk 생성)
      indexing_service.py         # 리포/브랜치 인덱싱 유즈케이스
      search_service.py           # Hybrid Code Search + Rerank 유즈케이스
      graph_service.py            # GraphRAG 탐색/이웃 찾기 유즈케이스
      git_service.py              # Git 히스토리/브랜치/PR 뷰 유즈케이스

  infra/                          # [Infrastructure Layer] Port 구현체 (Adapters)
    __init__.py

    vector/                       # VectorStore 포트 구현
      __init__.py
      qdrant.py                   # Qdrant 어댑터
      mock.py                     # 테스트용 인메모리/목 구현

    storage/                      # RDB / Graph 저장소 구현
      __init__.py
      postgres.py                 # SQLAlchemy/SQLModel 기반 RDB 구현
      neo4j.py                    # (옵션) 그래프 DB 구현

    git/
      __init__.py
      git_cli.py                  # Git CLI/Lib 기반 git_provider 구현

    search/
      __init__.py
      meilisearch.py              # Meilisearch 기반 lexical_search_port 구현

    llm/
      __init__.py
      openai.py                   # OpenAI 기반 llm_provider 구현

  scripts/                        # 유틸/운영 스크립트
    __init__.py
    reindex_all.py                # 모든 리포 재인덱싱
    debug_search.py               # 검색 디버깅/프로파일링

  tests/                          # 테스트
    __init__.py
    interfaces/
      __init__.py
      test_search_api.py
      test_index_api.py
    core/
      __init__.py
      test_search_service.py
      test_indexing_service.py
      test_graph_service.py
      test_chunk_model.py
    infra/
      __init__.py
      test_qdrant_adapter.py
      test_postgres_adapter.py


2. Navigation Principles
When modifying the system, adhere to these layer responsibilities:

A. Core Layer (The Brain)
Contains logic agnostic of frameworks and databases.

core/domain/: Defines data shapes. No logic methods.

core/ports/: Defines contracts (ABCs). No implementation.

core/services/: Defines flow and rules. This is where "parsing", "indexing", and "searching" happen.

B. Infra Layer (The Tools)
Contains specific implementations of external tools.

infra/vector/: Implements core.ports.vector_store.

infra/git/: Implements core.ports.git_provider.

C. Interfaces Layer (The Doors)
Contains entry points for users or agents.

interfaces/api/: REST API controllers.

interfaces/mcp/: MCP tool handlers.

3. Workflow Scenarios & Touchpoints
Use this section to locate files based on your intent.

Scenario A: Modification of Data Structure
Intent: "I need to add a 'review_status' field to the Pull Request node."

Modify Domain: Update PullRequestNode in core/domain/nodes.py.

Check Ports: If graph_store.py port relies on specific fields, check if updates are needed.

Update Infra: If using a schemaless DB (like Mongo), no change. If SQL, update infra/storage/postgres.py models.

Scenario B: Parsing Logic Enhancement
Intent: "The parser is failing to extract functions from Rust files."

Go to: core/services/ingestion/parser.py.

Action: Implement or fix the _visit_rust_node method or Tree-sitter query logic.

Scenario C: Search Algorithm Tuning
Intent: "I want to change the weight of 'hybrid search' (Lexical vs Semantic)."

Go to: core/services/search_service.py.

Action: Modify the scoring logic in the search method where vector scores and BM25 scores are combined.

Scenario D: Adding a New Agent Tool
Intent: "I want to expose a tool that finds 'who modified this file last' to the AI Agent."

Create Service Method: Add get_file_authors to core/services/git_service.py.

Expose via MCP: Create a new tool function in interfaces/mcp/tools/git_tools.py that calls the service.

Register: Register the new tool in interfaces/mcp/server.py.

Scenario E: Vector DB Migration
Intent: "We are switching from Qdrant to Weaviate."

Create Adapter: Create infra/vector/weaviate.py implementing VectorStorePort.

Update Wiring: Modify container.py to initialize WeaviateAdapter instead of QdrantAdapter.

Validation: core logic remains untouched.

Scenario F: Improving Reranking
Intent: "The search results are good, but the ordering is bad. I want to use a Cross-Encoder reranker."

Define Interface: Check core/ports/llm_provider.py or create a specific RerankerPort.

Implement Infra: Add infra/llm/cohere_reranker.py or huggingface_reranker.py.

Integrate: Update core/services/search_service.py to call the reranker after initial retrieval.

Scenario G: Handling a New Relationship Type
Intent: "I want to link 'Test Codes' to their 'Target Codes'."

Update Enum: Add TESTS to RelationshipType in core/domain/graph.py.

Update Logic: Modify core/services/ingestion/parser.py to detect test file patterns and create the relationship edge.

Update Mapper: Ensure canonical_leaf_to_vector_payload in core/domain/chunks.py handles this new relationship type correctly for flattening.

4. Wiring & Dependency Injection
The file container.py is the central wiring hub. It uses a DI framework to initialize Infra classes and pass them into Core services.

Rule: If you create a new Service or Adapter, you MUST register it in container.py so it can be accessed by the API or MCP server.
