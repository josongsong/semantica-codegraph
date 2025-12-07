from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from infra.config.logging import setup_logging
from server.api_server.routes import agent, graph, health, indexing, search

setup_logging()

app = FastAPI(
    title="Semantica v2 - CodeGraph API",
    description="""
    # Semantica v2 - SOTA급 코드 분석 & 에이전트 API

    ## 주요 기능

    - **코드 분석**: 저장소 전체 또는 특정 파일 분석
    - **에이전트**: 자동 코딩 어시스턴트 (분석, 수정, 리팩토링)
    - **검색**: 의미론적 코드 검색 (Semantic + Lexical)
    - **그래프**: 코드 의존성 그래프 (Memgraph)
    - **인덱싱**: 저장소 인덱싱 (Incremental + Full)

    ## 인증

    일부 엔드포인트는 API 키가 필요합니다.

    ```
    Authorization: Bearer <your-api-key>
    ```

    ## Rate Limiting

    - **기본**: 60 req/min
    - **프리미엄**: 600 req/min

    ## 성능

    - **P95 Latency**: < 1초
    - **Throughput**: 10+ QPS
    - **Cache Hit Rate**: 95%+

    ## 문서

    - [GitHub](https://github.com/your-repo)
    - [문서](https://docs.example.com)
    """,
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Semantica Team",
        "url": "https://github.com/your-repo",
        "email": "support@semantica.dev",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Middleware
from fastapi.middleware.cors import CORSMiddleware

from server.api_server.middleware.rate_limit import RateLimitMiddleware

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting
app.add_middleware(
    RateLimitMiddleware,
    default_limit=60,  # 60 req/min
    window=60,  # 60초
)

# Routes
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(graph.router, prefix="/graph", tags=["graph"])
app.include_router(indexing.router, prefix="/index", tags=["indexing"])
app.include_router(agent.router, prefix="/agent", tags=["agent"])


# ========================================================================
# Prometheus Metrics Endpoint
# ========================================================================
@app.get("/metrics", response_class=PlainTextResponse, tags=["monitoring"])
async def metrics_endpoint():
    """
    Prometheus 메트릭 엔드포인트.

    Agent 메트릭 (Multi-Agent, LLM, HITL 등)을 Prometheus 형식으로 반환.
    """
    from src.container import container
    from src.infra.observability.metrics import OpenTelemetryExporter

    # Metrics Collector에서 메트릭 가져오기
    metrics_collector = container.v7_metrics_collector
    all_metrics = metrics_collector.get_all_metrics()

    # Prometheus 형식으로 변환
    exporter = OpenTelemetryExporter(backend="prometheus")
    prometheus_text = exporter.export_prometheus_format(all_metrics)

    return prometheus_text


@app.on_event("startup")
async def startup():
    """애플리케이션 시작 시 초기화"""
    pass


@app.on_event("shutdown")
async def shutdown():
    """애플리케이션 종료 시 정리"""
    pass
