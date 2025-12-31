from fastapi import FastAPI
from fastapi.responses import PlainTextResponse

from apps.api.api.routes import (
    agent,
    graph,
    graph_semantics,
    health,
    indexing,
    rfc,
    search,
    workspace,
)
from codegraph_shared.common.observability import get_logger
from codegraph_shared.infra.config.logging import setup_logging

# RFC-052: Import V2 routes (optional)
try:
    from apps.api.api.routes import graph_semantics_v2

    _has_v2_routes = True
except ImportError:
    _has_v2_routes = False

logger = get_logger(__name__)

setup_logging()

app = FastAPI(
    title="Semantica v2 - CodeGraph API",
    description="""
# Semantica v2 - SOTA급 코드 분석 & 에이전트 API

## 🚀 주요 기능

| 기능 | 설명 | 엔드포인트 |
|-----|------|-----------|
| **코드 분석** | Cost, Race, Taint 분석 | `/api/v1/agent/analyze` |
| **검색** | Hybrid Search (Semantic + Lexical) | `/api/v1/search` |
| **그래프** | Call Graph, 의존성 분석 | `/api/v1/graph` |
| **Job** | 비동기 분석 + SSE 스트리밍 | `/api/v1/jobs` |
| **Health** | Liveness/Readiness Probe | `/health` |

## 🔐 인증

```
Authorization: Bearer <your-api-key>
```

## ⏱️ Rate Limiting

| 티어 | 제한 | 헤더 |
|-----|-----|------|
| 기본 | 60 req/min | `X-RateLimit-Limit` |
| 프리미엄 | 600 req/min | `X-RateLimit-Remaining` |

## 📊 성능

- **P95 Latency**: < 500ms (캐시 히트 시 < 50ms)
- **Throughput**: 50+ QPS
- **Cache Hit Rate**: 95%+ (Redis 백엔드)

## 🔍 Observability

- **Tracing**: OpenTelemetry + W3C Trace Context
- **Metrics**: Prometheus `/metrics`
- **Health**: `/health/ready`, `/health/live`

## 📚 API 버전

현재 버전: **v1** (`/api/v1/*`)

## 🛠️ 지원 언어 (Verify)

Python, TypeScript, JavaScript, Go, Rust, Java, C#
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "health", "description": "Health check endpoints (liveness/readiness)"},
        {"name": "search", "description": "Hybrid code search (semantic + lexical)"},
        {"name": "graph", "description": "Call graph and dependency analysis"},
        {"name": "graph-semantics", "description": "Semantic graph queries"},
        {"name": "indexing", "description": "Repository indexing (incremental/full)"},
        {"name": "agent", "description": "AI agent for code analysis and modification"},
        {"name": "workspace", "description": "Workspace management"},
    ],
    contact={
        "name": "Semantica Team",
        "url": "https://github.com/your-repo",
        "email": "support@semantica.dev",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    servers=[
        {"url": "/", "description": "Current server"},
        {"url": "http://localhost:8000", "description": "Local development"},
    ],
)

# Middleware
from fastapi.middleware.cors import CORSMiddleware

from apps.api.api.middleware.rate_limit import RateLimitMiddleware
from apps.api.api.middleware.tracing import TracingMiddleware

# Tracing (RFC-SEM-022 SOTA) - Must be first!
app.add_middleware(TracingMiddleware)

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

# Routes - API v1
API_V1_PREFIX = "/api/v1"

app.include_router(health.router, prefix="/health", tags=["health"])  # /health (no version - standard)
app.include_router(search.router, prefix=f"{API_V1_PREFIX}/search", tags=["search"])
app.include_router(graph.router, prefix=f"{API_V1_PREFIX}/graph", tags=["graph"])
app.include_router(graph_semantics.router, prefix=f"{API_V1_PREFIX}/graph", tags=["graph-semantics"])
app.include_router(indexing.router, prefix=f"{API_V1_PREFIX}/index", tags=["indexing"])
app.include_router(agent.router, prefix=f"{API_V1_PREFIX}/agent", tags=["agent"])
app.include_router(rfc.router)  # Already versioned: /api/v1/*
app.include_router(workspace.router, prefix=f"{API_V1_PREFIX}/workspace", tags=["workspace"])

# RFC-052: V2 routes (Clean Architecture)
if _has_v2_routes:
    app.include_router(
        graph_semantics_v2.router,
        prefix=f"{API_V1_PREFIX}",  # /api/v1/graph/v2/*
        tags=["Graph Semantics V2 (RFC-052)"],
    )
    logger.info("rfc052_routes_registered", endpoints=["/graph/v2/slice", "/graph/v2/dataflow"])
