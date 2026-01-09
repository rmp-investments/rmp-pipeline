"""
RMP Pipeline Web App - FastAPI Entry Point

A unified pipeline management tool combining the Deal Tracker and Property Screener
into a single web-based interface.

Run with: uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api import properties, pipeline, screener, auth
from app.services.box_service import get_box_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager."""
    # Startup: Initialize database
    await init_db()

    # Check Box connection status
    box_service = get_box_service()
    if box_service.is_connected():
        logger.info("Box connection: CONNECTED")
    else:
        logger.warning("Box connection: NOT CONNECTED - Properties will be unavailable")
        logger.warning("Ensure BOX_CONFIG_JSON environment variable is set correctly")

    yield
    # Shutdown: Clean up resources (if needed)
    pass


app = FastAPI(
    title="RMP Pipeline Web App",
    description="Unified pipeline management tool for property underwriting",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware - allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])
app.include_router(screener.router, prefix="/api/screener", tags=["Screener"])


@app.get("/")
async def root():
    """Root endpoint - health check."""
    return {
        "status": "ok",
        "app": "RMP Pipeline Web App",
        "version": "0.1.0",
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    box_service = get_box_service()
    return {
        "status": "healthy",
        "database": "connected",
        "box_connected": box_service.is_connected(),
        "box_warning": None if box_service.is_connected() else "Box not connected. Check BOX_CONFIG_JSON environment variable.",
    }


# TODO: Add WebSocket/SSE endpoint for real-time progress updates
# @app.get("/api/screener/{property_id}/progress")
# async def screener_progress(property_id: int):
#     """SSE endpoint for screener progress updates."""
#     pass
