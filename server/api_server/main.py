from fastapi import FastAPI

from apps.api_server.routes import graph, health, search
from infra.config.logging import setup_logging

setup_logging()

app = FastAPI(
    title="CodeGraph API",
    description="LLM을 위한 코드 저장소 분석 API",
    version="0.1.0",
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(graph.router, prefix="/graph", tags=["graph"])


@app.on_event("startup")
async def startup():
    """애플리케이션 시작 시 초기화"""
    pass


@app.on_event("shutdown")
async def shutdown():
    """애플리케이션 종료 시 정리"""
    pass
