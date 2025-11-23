"""
FastAPI Application Entry Point

Main FastAPI application with all routers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import chunks, graph, index, nodes, repos, search

# Create FastAPI app
app = FastAPI(
    title="Semantica Codegraph API",
    description="SOTA Code RAG API for LLM agents",
    version="4.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(index.router, prefix="/api/index", tags=["index"])
app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
app.include_router(chunks.router, prefix="/api/chunks", tags=["chunks"])
app.include_router(nodes.router, prefix="/api/nodes", tags=["nodes"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Semantica Codegraph API",
        "version": "4.0.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}
