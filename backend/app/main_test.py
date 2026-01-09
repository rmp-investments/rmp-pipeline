"""Test FastAPI app - incrementally adding features to find failure point."""

import sys
print(f"Python version: {sys.version}")

# Step 1: Basic FastAPI
print("Step 1: Importing FastAPI...")
from fastapi import FastAPI
print("Step 1: OK")

# Step 2: Settings
print("Step 2: Importing config/settings...")
try:
    from app.config import settings
    print(f"Step 2: OK - database_url={settings.database_url}")
except Exception as e:
    print(f"Step 2: FAILED - {e}")
    import traceback
    traceback.print_exc()

# Step 3: Database
print("Step 3: Importing database...")
try:
    from app.database import Base, engine
    print("Step 3: OK")
except Exception as e:
    print(f"Step 3: FAILED - {e}")
    import traceback
    traceback.print_exc()

# Step 4: Models
print("Step 4: Importing models...")
try:
    from app.models import property
    print("Step 4: OK")
except Exception as e:
    print(f"Step 4: FAILED - {e}")
    import traceback
    traceback.print_exc()

# Step 5: Box service (this might be the culprit)
print("Step 5: Importing box_service...")
try:
    from app.services.box_service import get_box_service
    print("Step 5: OK")
except Exception as e:
    print(f"Step 5: FAILED - {e}")
    import traceback
    traceback.print_exc()

# Step 6: Screener service
print("Step 6: Importing screener_service...")
try:
    from app.services.screener_service import ScreenerService
    print("Step 6: OK")
except Exception as e:
    print(f"Step 6: FAILED - {e}")
    import traceback
    traceback.print_exc()

# Step 7: API routers
print("Step 7: Importing API routers...")
try:
    from app.api import properties, pipeline, screener, auth
    print("Step 7: OK")
except Exception as e:
    print(f"Step 7: FAILED - {e}")
    import traceback
    traceback.print_exc()

print("\n=== Import tests complete ===\n")

# Create minimal app
app = FastAPI(title="RMP Pipeline API - Test")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Test app running - check logs for import results"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
