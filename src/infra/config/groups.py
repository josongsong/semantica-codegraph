"""
설정 그룹 정의.

Settings를 논리적 그룹으로 분리하여 관리합니다.
각 그룹은 독립적으로 사용 가능하며, Settings에서 통합됩니다.
"""

from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """PostgreSQL 데이터베이스 설정."""

    url: str = Field(
        default="postgresql://codegraph:codegraph_dev@localhost:5432/codegraph",
        description="PostgreSQL 연결 URL",
    )
    min_pool_size: int = Field(default=5, ge=1, le=50, description="최소 커넥션 풀 크기")
    max_pool_size: int = Field(default=20, ge=1, le=100, description="최대 커넥션 풀 크기")
    command_timeout: float = Field(default=30.0, ge=1.0, description="명령 타임아웃 (초)")
    max_idle_time: float = Field(default=300.0, ge=60.0, description="최대 유휴 시간 (초)")


class VectorConfig(BaseModel):
    """Qdrant 벡터 검색 설정."""

    url: str = Field(default="http://localhost:6333", description="Qdrant URL")
    host: str = Field(default="localhost", description="Qdrant 호스트")
    port: int = Field(default=6333, ge=1, le=65535, description="Qdrant HTTP 포트")
    grpc_port: int = Field(default=6334, ge=1, le=65535, description="Qdrant gRPC 포트")
    prefer_grpc: bool = Field(default=True, description="gRPC 사용 여부 (2-5x 빠름)")
    collection_name: str = Field(default="codegraph", description="컬렉션 이름")
    vector_size: int = Field(default=1024, description="벡터 차원 (bge-m3)")
    upsert_concurrency: int = Field(default=4, ge=1, le=16, description="동시 upsert 배치 수")


class LexicalConfig(BaseModel):
    """Zoekt 렉시컬 검색 설정."""

    host: str = Field(default="localhost", description="Zoekt 호스트")
    port: int = Field(default=6070, ge=1, le=65535, description="Zoekt 포트")
    url: str = Field(default="http://localhost:6070", description="Zoekt URL")
    repos_root: str = Field(default="./repos", description="레포지토리 루트 경로")
    index_dir: str = Field(default="./data/zoekt-index", description="인덱스 디렉토리")
    index_cmd: str = Field(default="zoekt-index", description="인덱싱 명령어")


class GraphConfig(BaseModel):
    """Memgraph 그래프 데이터베이스 설정."""

    uri: str = Field(default="bolt://localhost:7208", description="Memgraph Bolt URI")
    username: str = Field(default="", description="사용자명")
    password: str = Field(default="", description="비밀번호")
    node_batch_size: int = Field(default=2000, description="노드 배치 사이즈 (UNWIND 연산)")
    edge_batch_size: int = Field(default=2000, description="엣지 배치 사이즈 (UNWIND 연산)")
    delete_batch_size: int = Field(default=3000, description="삭제 배치 사이즈")


class CacheConfig(BaseModel):
    """Redis 및 3-tier 캐시 설정."""

    # Redis 연결
    host: str = Field(default="localhost", description="Redis 호스트")
    port: int = Field(default=6379, ge=1, le=65535, description="Redis 포트")
    db: int = Field(default=0, ge=0, le=15, description="Redis DB 번호")
    password: str | None = Field(default=None, description="Redis 비밀번호")

    # 3-tier cache 활성화
    enable_three_tier: bool = Field(default=True, description="3-tier 캐싱 활성화")

    # L1 (In-Memory) 설정
    l1_chunk_maxsize: int = Field(default=1000, ge=100, description="L1 Chunk 캐시 최대 크기")
    l1_graph_node_maxsize: int = Field(default=5000, ge=500, description="L1 Graph 노드 캐시 최대 크기")
    l1_graph_relation_maxsize: int = Field(default=2000, ge=200, description="L1 Graph 관계 캐시 최대 크기")
    l1_ir_maxsize: int = Field(default=500, ge=50, description="L1 IR 캐시 최대 크기")

    # TTL 설정
    chunk_ttl: int = Field(default=300, ge=60, description="Chunk 캐시 TTL (초)")
    graph_ttl: int = Field(default=600, ge=60, description="Graph 캐시 TTL (초)")
    ir_ttl: int = Field(default=600, ge=60, description="IR 캐시 TTL (초)")


class ObservabilityConfig(BaseModel):
    """관측성 (Observability) 설정."""

    # OpenTelemetry
    otel_enabled: bool = Field(default=True, description="OpenTelemetry 활성화")
    otel_endpoint: str = Field(default="http://localhost:4317", description="OTLP 엔드포인트")
    otel_service_name: str = Field(default="codegraph", description="서비스 이름")
    otel_service_version: str = Field(default="0.1.0", description="서비스 버전")
    deployment_environment: str = Field(
        default="development", description="배포 환경 (development, staging, production)"
    )

    # TLS/Security
    otel_insecure: bool = Field(default=True, description="OTLP insecure 연결 (개발용, production에서는 False)")
    otel_tls_cert_path: str | None = Field(default=None, description="OTLP TLS 인증서 경로 (production용)")

    # Exporters
    enable_prometheus: bool = Field(default=True, description="Prometheus exporter 활성화")
    enable_otlp: bool = Field(default=False, description="OTLP exporter 활성화")
    enable_tracing: bool = Field(default=False, description="분산 트레이싱 활성화")

    # Auto-instrumentation
    enable_auto_instrumentation: bool = Field(default=True, description="자동 계측 활성화")
    enable_cost_tracking: bool = Field(default=True, description="LLM 비용 추적 활성화")

    # Metrics
    metrics_port: int = Field(default=9090, ge=1, le=65535, description="Prometheus 메트릭 포트")


class LLMConfig(BaseModel):
    """LLM 및 임베딩 설정."""

    # OpenAI / LiteLLM (Cloud)
    litellm_model: str = Field(default="gpt-4", description="LiteLLM 모델")
    litellm_api_key: str = Field(default="", description="LiteLLM API 키")
    openai_api_key: str = Field(default="", description="OpenAI API 키")

    # Local LLM (Provider-agnostic: Ollama, vLLM, LocalAI, etc.)
    local_llm_base_url: str = Field(default="http://127.0.0.1:8000", description="로컬 LLM 게이트웨이 URL")
    local_llm_gateway_port: int = Field(default=8000, description="게이트웨이 포트")
    local_llm_native_port: int = Field(default=11434, description="네이티브 API 포트")
    local_result_model: str = Field(default="qwen2.5-coder-32b", description="결과 생성 모델")
    local_intent_model: str = Field(default="qwen2.5-coder-7b", description="인텐트 분석 모델")

    # Cloud Embeddings (OpenAI, etc.)
    embedding_model: str = Field(default="text-embedding-3-small", description="클라우드 임베딩 모델")
    embedding_dimension: int = Field(default=1536, description="클라우드 임베딩 차원")
    embedding_concurrency: int = Field(default=4, ge=1, le=16, description="동시 임베딩 호출 수")

    # Local Embeddings (BGE-M3, etc.)
    local_embedding_model: str = Field(default="bge-m3:latest", description="로컬 임베딩 모델")
    local_embedding_dimension: int = Field(default=1024, description="로컬 임베딩 차원")
    local_embedding_concurrency: int = Field(default=8, ge=1, le=32, description="동시 호출 수")

    # Reranking
    local_reranker_model: str = Field(default="bge-reranker-large", description="리랭커 모델")
    reranker_batch_size: int = Field(default=10, ge=1, le=100, description="리랭커 배치 크기")
    reranker_max_length: int = Field(default=512, ge=128, le=2048, description="리랭커 최대 길이")

    # Embedding Cache (Phase 3 Day 24-25)
    enable_embedding_cache: bool = Field(default=True, description="임베딩 캐시 사용 (벤치마킹 시 False)")
    embedding_cache_ttl_days: int = Field(default=7, ge=1, le=30, description="임베딩 캐시 TTL (일)")


class SearchConfig(BaseModel):
    """검색 가중치 설정."""

    weight_lexical: float = Field(default=0.3, ge=0.0, le=1.0, description="렉시컬 가중치")
    weight_vector: float = Field(default=0.3, ge=0.0, le=1.0, description="벡터 가중치")
    weight_symbol: float = Field(default=0.2, ge=0.0, le=1.0, description="심볼 가중치")
    weight_fuzzy: float = Field(default=0.1, ge=0.0, le=1.0, description="퍼지 가중치")
    weight_domain: float = Field(default=0.1, ge=0.0, le=1.0, description="도메인 가중치")


class IndexingConfig(BaseModel):
    """인덱싱 설정."""

    # 인덱스 타입 활성화
    enable_lexical: bool = Field(default=True, description="렉시컬 인덱스 활성화")
    enable_vector: bool = Field(default=True, description="벡터 인덱스 활성화")
    enable_symbol: bool = Field(default=True, description="심볼 인덱스 활성화")
    enable_symbol_embedding: bool = Field(default=True, description="심볼 임베딩 활성화")
    enable_fuzzy: bool = Field(default=True, description="퍼지 인덱스 활성화")
    enable_domain: bool = Field(default=True, description="도메인 인덱스 활성화")

    # 배치 크기
    chunk_batch_size: int = Field(default=500, ge=10, le=5000, description="청크 배치 크기")
    vector_batch_size: int = Field(default=1024, ge=10, le=2048, description="벡터 배치 크기")

    # 기타
    use_partial_updates: bool = Field(default=False, description="부분 업데이트 사용")
    enable_pyright: bool = Field(default=True, description="Pyright 통합 활성화")


class RetrieverConfig(BaseModel):
    """Retriever v3 설정."""

    # 캐시
    enable_cache: bool = Field(default=True, description="캐시 활성화")
    cache_ttl: int = Field(default=300, ge=60, le=3600, description="캐시 TTL (초)")
    l1_cache_size: int = Field(default=1000, ge=100, le=10000, description="L1 캐시 크기")
    intent_cache_size: int = Field(default=500, ge=50, le=5000, description="인텐트 캐시 크기")

    # RRF k values
    rrf_k_vector: int = Field(default=70, ge=10, le=200, description="벡터 RRF k")
    rrf_k_lexical: int = Field(default=70, ge=10, le=200, description="렉시컬 RRF k")
    rrf_k_symbol: int = Field(default=50, ge=10, le=200, description="심볼 RRF k")
    rrf_k_graph: int = Field(default=50, ge=10, le=200, description="그래프 RRF k")

    # Consensus
    consensus_beta: float = Field(default=0.3, ge=0.0, le=1.0, description="합의 베타")
    consensus_max_factor: float = Field(default=1.5, ge=1.0, le=3.0, description="최대 합의 팩터")
    consensus_quality_q0: float = Field(default=10.0, ge=1.0, le=100.0, description="품질 정규화")

    # 기능
    enable_query_expansion: bool = Field(default=True, description="쿼리 확장 활성화")


class AgentConfig(BaseModel):
    """에이전트 시스템 설정."""

    workspace_path: str = Field(default=".", description="작업 경로")
    max_transitions: int = Field(default=20, ge=1, le=100, description="최대 전이 수")
    timeout_seconds: int = Field(default=300, ge=60, le=3600, description="타임아웃 (초)")
    enable_auto_approve: bool = Field(default=False, description="자동 승인 (개발용)")


class ApplicationConfig(BaseModel):
    """애플리케이션 일반 설정."""

    log_level: str = Field(default="INFO", description="로그 레벨")
    chunk_size: int = Field(default=512, ge=128, le=2048, description="청크 크기")
    chunk_overlap: int = Field(default=50, ge=0, le=256, description="청크 오버랩")
    repos_base_path: str = Field(default="./repos", description="레포 베이스 경로")


class FileWatcherConfig(BaseModel):
    """파일 감시 설정."""

    enabled: bool = Field(default=True, description="파일 감시 활성화")
    debounce_ms: int = Field(default=300, ge=100, le=5000, description="디바운스 (ms)")
    max_batch_window_ms: int = Field(default=5000, ge=1000, le=30000, description="최대 배치 윈도우 (ms)")
    exclude_patterns: str = Field(
        default=".git,node_modules,__pycache__,.venv,venv,*.pyc,*.pyo,.DS_Store,"
        ".idea,.vscode,dist,build,.pytest_cache,.mypy_cache,.ruff_cache",
        description="제외 패턴",
    )
    supported_extensions: str = Field(
        default=".py,.pyi,.ts,.tsx,.js,.jsx,.java,.go,.rs,.c,.cpp,.h,.hpp,.cs,.rb,.php",
        description="지원 확장자",
    )
