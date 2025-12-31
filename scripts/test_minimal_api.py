"""Minimal FastAPI for Granian testing"""

from fastapi import FastAPI

app = FastAPI(title="Granian Test")


@app.get("/health")
async def health():
    return {"status": "healthy", "server": "granian"}


@app.get("/")
async def root():
    return {"message": "Granian test server"}
