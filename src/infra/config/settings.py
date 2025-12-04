from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.infra.config.groups import (
    AgentConfig,
    ApplicationConfig,
    CacheConfig,
    DatabaseConfig,
    FileWatcherConfig,
    GraphConfig,
    IndexingConfig,
    LexicalConfig,
    LLMConfig,
    ObservabilityConfig,
    RetrieverConfig,
    SearchConfig,
    VectorConfig,
)


class Settings(BaseSettings):
    """
    Semantica Codegraph Application Settings

    Environment variables should use SEMANTICA_ prefix.
    Example: SEMANTICA_DATABASE_URL, SEMANTICA_QDRANT_URL

    그룹화된 설정 접근:
        settings.db          # DatabaseConfig
        settings.vector      # VectorConfig
        settings.lexical     # LexicalConfig
        settings.graph       # GraphConfig
        settings.cache       # CacheConfig
        settings.llm         # LLMConfig
        settings.observability # ObservabilityConfig
        settings.search      # SearchConfig
        settings.indexing    # IndexingConfig
        settings.retriever   # RetrieverConfig
        settings.agent       # AgentConfig
        settings.app         # ApplicationConfig
        settings.file_watcher # FileWatcherConfig
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SEMANTICA_",
        extra="ignore",  # 알 수 없는 환경 변수 무시
    )

    # ========================================================================
    # Grouped Config Accessors (New API)
    # ========================================================================

    @cached_property
    def db(self) -> DatabaseConfig:
        """데이터베이스 설정 그룹."""
        return DatabaseConfig(
            url=self.database_url,
            min_pool_size=self.postgres_min_pool_size,
            max_pool_size=self.postgres_max_pool_size,
        )

    @cached_property
    def vector(self) -> VectorConfig:
        """벡터 검색 설정 그룹."""
        return VectorConfig(
            url=self.qdrant_url,
            host=self.qdrant_host,
            port=self.qdrant_port,
            grpc_port=self.qdrant_grpc_port,
            prefer_grpc=self.qdrant_prefer_grpc,
            collection_name=self.qdrant_collection_name,
            vector_size=self.qdrant_vector_size,
            upsert_concurrency=self.qdrant_upsert_concurrency,
        )

    @cached_property
    def lexical(self) -> LexicalConfig:
        """렉시컬 검색 설정 그룹."""
        return LexicalConfig(
            host=self.zoekt_host,
            port=self.zoekt_port,
            url=self.zoekt_url,
            repos_root=self.zoekt_repos_root,
            index_dir=self.zoekt_index_dir,
            index_cmd=self.zoekt_index_cmd,
        )

    @cached_property
    def graph(self) -> GraphConfig:
        """그래프 DB 설정 그룹."""
        return GraphConfig(
            uri=self.memgraph_uri,
            username=self.memgraph_username,
            password=self.memgraph_password,
            node_batch_size=self.memgraph_node_batch_size,
            edge_batch_size=self.memgraph_edge_batch_size,
            delete_batch_size=self.memgraph_delete_batch_size,
        )

    @cached_property
    def cache(self) -> CacheConfig:
        """캐시 설정 그룹."""
        return CacheConfig(
            host=self.redis_host,
            port=self.redis_port,
            db=self.redis_db,
            password=self.redis_password,
        )

    @cached_property
    def llm(self) -> LLMConfig:
        """LLM 설정 그룹."""
        return LLMConfig(
            litellm_model=self.litellm_model,
            litellm_api_key=self.litellm_api_key,
            openai_api_key=self.openai_api_key,
            local_llm_base_url=self.local_llm_base_url,
            local_llm_gateway_port=self.local_llm_gateway_port,
            local_llm_native_port=self.local_llm_native_port,
            local_result_model=self.local_result_model,
            local_intent_model=self.local_intent_model,
            embedding_model=self.embedding_model,
            embedding_dimension=self.embedding_dimension,
            embedding_concurrency=self.embedding_concurrency,
            local_embedding_model=self.local_embedding_model,
            local_embedding_dimension=self.local_embedding_dimension,
            local_embedding_concurrency=self.local_embedding_concurrency,
            local_reranker_model=self.local_reranker_model,
            reranker_batch_size=self.reranker_batch_size,
            reranker_max_length=self.reranker_max_length,
        )

    @cached_property
    def search(self) -> SearchConfig:
        """검색 가중치 설정 그룹."""
        return SearchConfig(
            weight_lexical=self.search_weight_lexical,
            weight_vector=self.search_weight_vector,
            weight_symbol=self.search_weight_symbol,
            weight_fuzzy=self.search_weight_fuzzy,
            weight_domain=self.search_weight_domain,
        )

    @cached_property
    def indexing(self) -> IndexingConfig:
        """인덱싱 설정 그룹."""
        return IndexingConfig(
            enable_lexical=self.indexing_enable_lexical,
            enable_vector=self.indexing_enable_vector,
            enable_symbol=self.indexing_enable_symbol,
            enable_symbol_embedding=self.indexing_enable_symbol_embedding,
            enable_fuzzy=self.indexing_enable_fuzzy,
            enable_domain=self.indexing_enable_domain,
            chunk_batch_size=self.indexing_chunk_batch_size,
            vector_batch_size=self.indexing_vector_batch_size,
            use_partial_updates=self.indexing_use_partial_updates,
            enable_pyright=self.enable_pyright,
        )

    @cached_property
    def retriever(self) -> RetrieverConfig:
        """Retriever 설정 그룹."""
        return RetrieverConfig(
            enable_cache=self.retriever_enable_cache,
            cache_ttl=self.retriever_cache_ttl,
            l1_cache_size=self.retriever_l1_cache_size,
            intent_cache_size=self.retriever_intent_cache_size,
            rrf_k_vector=self.retriever_rrf_k_vector,
            rrf_k_lexical=self.retriever_rrf_k_lexical,
            rrf_k_symbol=self.retriever_rrf_k_symbol,
            rrf_k_graph=self.retriever_rrf_k_graph,
            consensus_beta=self.retriever_consensus_beta,
            consensus_max_factor=self.retriever_consensus_max_factor,
            consensus_quality_q0=self.retriever_consensus_quality_q0,
            enable_query_expansion=self.retriever_enable_query_expansion,
        )

    @cached_property
    def agent(self) -> AgentConfig:
        """에이전트 설정 그룹."""
        return AgentConfig(
            workspace_path=self.workspace_path,
            max_transitions=self.agent_max_transitions,
            timeout_seconds=self.agent_timeout_seconds,
            enable_auto_approve=self.agent_enable_auto_approve,
        )

    @cached_property
    def app(self) -> ApplicationConfig:
        """애플리케이션 설정 그룹."""
        return ApplicationConfig(
            log_level=self.log_level,
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            repos_base_path=self.repos_base_path,
        )

    @cached_property
    def file_watcher(self) -> FileWatcherConfig:
        """파일 감시 설정 그룹."""
        return FileWatcherConfig(
            enabled=self.file_watcher_enabled,
            debounce_ms=self.file_watcher_debounce_ms,
            max_batch_window_ms=self.file_watcher_max_batch_window_ms,
            exclude_patterns=self.file_watcher_exclude_patterns,
            supported_extensions=self.file_watcher_supported_extensions,
        )

    @cached_property
    def observability(self) -> ObservabilityConfig:
        """관측성 설정 그룹."""
        return ObservabilityConfig(
            otel_enabled=self.otel_enabled,
            otel_endpoint=self.otel_endpoint,
            otel_service_name=self.otel_service_name,
            otel_service_version=self.otel_service_version,
            deployment_environment=self.deployment_environment,
            otel_insecure=self.otel_insecure,
            otel_tls_cert_path=self.otel_tls_cert_path,
            enable_prometheus=self.enable_prometheus,
            enable_otlp=self.enable_otlp,
            enable_tracing=self.enable_tracing,
            enable_auto_instrumentation=self.enable_auto_instrumentation,
            enable_cost_tracking=self.enable_cost_tracking,
            metrics_port=self.metrics_port,
        )

    # ========================================================================
    # Database (PostgreSQL)
    # ========================================================================
    database_url: str = "postgresql://codegraph:codegraph_dev@localhost:5432/codegraph"
    postgres_min_pool_size: int = 2
    postgres_max_pool_size: int = 10

    # ========================================================================
    # Vector Search (Qdrant)
    # ========================================================================
    qdrant_url: str = "http://localhost:6333"
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334  # gRPC port for faster operations
    qdrant_prefer_grpc: bool = True  # Use gRPC for 2-5x faster latency
    qdrant_collection_name: str = "codegraph"
    qdrant_vector_size: int = 1024  # Ollama bge-m3 embedding dimension
    qdrant_upsert_concurrency: int = 4  # Max concurrent upsert batches

    # ========================================================================
    # Lexical Search (Zoekt)
    # ========================================================================
    zoekt_host: str = "localhost"
    zoekt_port: int = 6070
    zoekt_url: str = "http://localhost:6070"
    zoekt_repos_root: str = "./repos"
    zoekt_index_dir: str = "./data/zoekt-index"  # Local directory for Zoekt index files
    zoekt_index_cmd: str = "zoekt-index"  # Expects zoekt-index in PATH or set via env

    # ========================================================================
    # Graph Database (Memgraph)
    # ========================================================================
    memgraph_uri: str = "bolt://localhost:7208"
    memgraph_username: str = ""
    memgraph_password: str = ""
    memgraph_node_batch_size: int = 2000  # UNWIND batch size for nodes
    memgraph_edge_batch_size: int = 2000  # UNWIND batch size for edges
    memgraph_delete_batch_size: int = 3000  # Batch size for deletes

    # ========================================================================
    # Cache (Redis)
    # ========================================================================
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    # ========================================================================
    # LLM (OpenAI / LiteLLM)
    # ========================================================================
    litellm_model: str = "gpt-4"
    litellm_api_key: str = ""
    openai_api_key: str = ""

    # ========================================================================
    # Local LLM Configuration (Provider-agnostic: Ollama, vLLM, LocalAI, etc.)
    # ========================================================================
    # Base endpoint for OpenAI-compatible API gateway server
    # Gateway server provides OpenAI-compatible endpoints (/v1/embeddings, /v1/chat/completions)
    local_llm_base_url: str = "http://127.0.0.1:8000"
    local_llm_gateway_port: int = 8000  # OpenAI-compatible gateway port
    local_llm_native_port: int = 11434  # Native API port (e.g., Ollama native)

    # LLM for result generation (Korean + Code optimized)
    # qwen2.5-coder-32b: Top coding model with Llama 3.1 70B-level general/Korean perf
    local_result_model: str = "qwen2.5-coder-32b"

    # LLM for intent analysis (Fast JSON output)
    # qwen2.5-coder-7b: Strategic choice - Speed + Format compliance
    # Coding model excels at JSON output, saves memory for main model (32B)
    local_intent_model: str = "qwen2.5-coder-7b"

    # ========================================================================
    # Embeddings (Multi-provider support)
    # ========================================================================
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    embedding_concurrency: int = 4  # Max concurrent embedding API calls (OpenAI)
    cohere_api_key: str = ""
    mistral_api_key: str = ""
    voyage_code_api_key: str = ""

    # Local Embedding Model
    # bge-m3: Best Korean support, multilingual, long context (8k)
    local_embedding_model: str = "bge-m3:latest"
    local_embedding_dimension: int = 1024  # BGE-M3 output dimension
    local_embedding_concurrency: int = 8  # Max concurrent local embedding calls

    # ========================================================================
    # Reranking (Cross-encoder)
    # ========================================================================
    # bge-reranker-large: Significantly improves retrieval accuracy, excellent Korean understanding
    local_reranker_model: str = "bge-reranker-large"
    reranker_batch_size: int = 10
    reranker_max_length: int = 512

    # ========================================================================
    # Search Weights
    # ========================================================================
    search_weight_lexical: float = 0.3
    search_weight_vector: float = 0.3
    search_weight_symbol: float = 0.2
    search_weight_fuzzy: float = 0.1
    search_weight_domain: float = 0.1
    search_weight_runtime: float = 0.0  # Phase 3

    # ========================================================================
    # Indexing Configuration
    # ========================================================================
    # Enable/disable index types
    indexing_enable_lexical: bool = True
    indexing_enable_vector: bool = True
    indexing_enable_symbol: bool = True  # Enabled: Memgraph-based Symbol Index
    indexing_enable_symbol_embedding: bool = True  # Enable semantic symbol search via embeddings
    indexing_enable_fuzzy: bool = True
    indexing_enable_domain: bool = True

    # Batch sizes
    indexing_chunk_batch_size: int = 500
    # OpenAI embedding API supports up to 2048 texts per request
    # Increased from 100 to 1024 for better throughput (reduces API calls by 10x)
    indexing_vector_batch_size: int = 1024

    # Incremental updates
    indexing_use_partial_updates: bool = False

    # Pyright integration (RFC-023)
    # Enables cross-file type inference for accurate incremental indexing
    enable_pyright: bool = True

    # ========================================================================
    # Agent System Configuration
    # ========================================================================
    workspace_path: str = "."  # Base path for agent file operations
    agent_max_transitions: int = 20  # Maximum workflow transitions
    agent_timeout_seconds: int = 300  # Workflow timeout (5 minutes)
    agent_enable_auto_approve: bool = False  # Auto-approve changes (dev only)

    # ========================================================================
    # Retriever V3 Configuration
    # ========================================================================
    # Cache settings
    retriever_enable_cache: bool = True
    retriever_cache_ttl: int = 300  # seconds
    retriever_l1_cache_size: int = 1000  # query results
    retriever_intent_cache_size: int = 500  # intent classifications

    # RRF k values (strategy-specific, tunable for different dataset sizes)
    retriever_rrf_k_vector: int = 70
    retriever_rrf_k_lexical: int = 70
    retriever_rrf_k_symbol: int = 50
    retriever_rrf_k_graph: int = 50

    # Consensus parameters
    retriever_consensus_beta: float = 0.3
    retriever_consensus_max_factor: float = 1.5
    retriever_consensus_quality_q0: float = 10.0

    # Query expansion
    retriever_enable_query_expansion: bool = True

    # ========================================================================
    # Application
    # ========================================================================
    log_level: str = "INFO"
    chunk_size: int = 512
    chunk_overlap: int = 50
    repos_base_path: str = "./repos"
    index_batch_size: int = 100
    # Increased from 50 to 1024 for OpenAI embedding API optimization
    vector_batch_size: int = 1024

    # ========================================================================
    # Document Indexing
    # ========================================================================
    doc_index_profile: str = "ADVANCED"  # OFF | BASIC | ADVANCED | SOTA
    doc_max_pdf_size_mb: int = 50
    doc_enable_pdf_ocr: bool = False
    doc_max_tokens_per_chunk: int = 1024
    doc_enable_drift_detection: bool = False
    doc_enable_quality_scoring: bool = False

    # ========================================================================
    # RepoMap Configuration
    # ========================================================================
    repomap_storage_dir: str = "./data/repomap"
    repomap_enable_pagerank: bool = True
    repomap_enable_summaries: bool = False
    repomap_include_tests: bool = False

    # ========================================================================
    # File Watcher Configuration
    # ========================================================================
    file_watcher_enabled: bool = True
    file_watcher_debounce_ms: int = 300  # 디바운스 시간 (ms)
    file_watcher_max_batch_window_ms: int = 5000  # 최대 배치 윈도우 (ms)
    file_watcher_exclude_patterns: str = (
        ".git,node_modules,__pycache__,.venv,venv,*.pyc,*.pyo,.DS_Store,"
        ".idea,.vscode,dist,build,.pytest_cache,.mypy_cache,.ruff_cache"
    )
    file_watcher_supported_extensions: str = ".py,.pyi,.ts,.tsx,.js,.jsx,.java,.go,.rs,.c,.cpp,.h,.hpp,.cs,.rb,.php"

    # ========================================================================
    # Observability (OpenTelemetry)
    # ========================================================================
    otel_enabled: bool = True
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "codegraph"
    otel_service_version: str = "0.1.0"
    deployment_environment: str = "development"
    otel_insecure: bool = True
    otel_tls_cert_path: str | None = None
    enable_prometheus: bool = True
    enable_otlp: bool = False
    enable_tracing: bool = False
    enable_auto_instrumentation: bool = True
    enable_cost_tracking: bool = True
    metrics_port: int = 9090

    # ========================================================================
    # Embedding Cache (Phase 3)
    # ========================================================================
    enable_embedding_cache: bool = True  # 벤치마킹 시 False
    embedding_cache_ttl_days: int = 7


# Eager loading (module-level instantiation)
settings = Settings()
