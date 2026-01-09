"""Minimal FastAPI app for deployment testing."""

from fastapi import FastAPI

app = FastAPI(title="RMP Pipeline API - Minimal Test")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Minimal deployment working"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
