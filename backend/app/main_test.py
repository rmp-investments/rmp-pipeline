"""Test FastAPI app - incrementally adding features to find failure point."""

import sys
print(f"Python version: {sys.version}")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import all modules like main.py does
print("Importing app.config...")
from app.config import settings
print(f"OK - cors_origins={settings.cors_origins}")

print("Importing app.database...")
from app.database import init_db
print("OK")

print("Importing app.api routers...")
from app.api import properties, pipeline, screener, auth
print("OK")

print("\n=== All imports successful ===\n")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager - same as main.py."""
    print("Lifespan: Calling init_db()...")
    try:
        await init_db()
        print("Lifespan: init_db() completed successfully!")
    except Exception as e:
        print(f"Lifespan: init_db() FAILED - {e}")
        import traceback
        traceback.print_exc()
        # Re-raise to see if this is what kills the app
        raise
    yield
    print("Lifespan: Shutdown")

# Create app exactly like main.py
app = FastAPI(
    title="RMP Pipeline Web App - Test",
    description="Testing full app configuration",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware exactly like main.py
print(f"Adding CORS middleware with origins: {settings.cors_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers exactly like main.py
print("Including routers...")
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(properties.router, prefix="/api/properties", tags=["Properties"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["Pipeline"])
app.include_router(screener.router, prefix="/api/screener", tags=["Screener"])
print("Routers included successfully!")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Full test app running - check logs for details"}

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}
