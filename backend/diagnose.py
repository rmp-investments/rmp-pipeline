#!/usr/bin/env python3
"""Diagnostic script to identify import/startup issues."""

import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")
print()

# Test imports one by one
imports = [
    ("fastapi", "from fastapi import FastAPI"),
    ("pydantic_settings", "from pydantic_settings import BaseSettings"),
    ("uvicorn", "import uvicorn"),
    ("sqlalchemy", "from sqlalchemy.ext.asyncio import AsyncSession"),
    ("aiosqlite", "import aiosqlite"),
    ("boxsdk", "from boxsdk import JWTAuth, Client"),
    ("app.config", "from app.config import settings"),
    ("app.database", "from app.database import Base"),
    ("app.models", "from app.models import property"),
    ("app.services.box_service", "from app.services.box_service import get_box_service"),
    ("app.services.screener_service", "from app.services.screener_service import ScreenerService"),
    ("app.api.auth", "from app.api import auth"),
    ("app.api.properties", "from app.api import properties"),
    ("app.api.pipeline", "from app.api import pipeline"),
    ("app.api.screener", "from app.api import screener"),
    ("app.main", "from app.main import app"),
]

for name, import_stmt in imports:
    try:
        exec(import_stmt)
        print(f"OK: {name}")
    except Exception as e:
        print(f"FAIL: {name} - {type(e).__name__}: {e}")
        # Don't break - continue to find all issues

print()
print("Diagnosis complete.")
