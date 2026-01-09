"""
Screener API endpoints.

Provides endpoints for running the property screener, tracking progress,
uploading PDFs, and retrieving results.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.property import Property, ScreenerRun, ScreenerData
from app.services.screener_service import ScreenerService


router = APIRouter()


# ----- Pydantic Schemas -----


class ScreenerRunResponse(BaseModel):
    """Schema for screener run response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    output_excel_path: Optional[str] = None
    maps_generated: Optional[List[str]] = None
    current_step: Optional[str] = None
    progress_percent: Optional[int] = None


class ScreenerDataResponse(BaseModel):
    """Schema for screener data response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    field_name: str
    field_value: Optional[str] = None
    source: Optional[str] = None
    validated: bool = False


class ScreenerStartResponse(BaseModel):
    """Response when starting a screener run."""

    status: str
    run_id: int
    property_id: int
    message: str


# ----- API Endpoints -----


@router.post("/{property_id}/run", response_model=ScreenerStartResponse)
async def start_screener(
    property_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Start a screener analysis for a property.

    This kicks off a background task that:
    1. Extracts data from CoStar PDFs
    2. Scrapes web demographics
    3. Generates maps
    4. Creates the Excel screener output

    Use GET /api/screener/{property_id}/status to track progress.
    """
    # Verify property exists
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check for existing running screener
    running_check = await db.execute(
        select(ScreenerRun).where(
            ScreenerRun.property_id == property_id,
            ScreenerRun.status == "running",
        )
    )
    if running_check.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Screener already running for this property",
        )

    # Create new screener run record
    screener_run = ScreenerRun(
        property_id=property_id,
        status="pending",
        started_at=datetime.utcnow(),
        current_step="Initializing",
        progress_percent=0,
    )
    db.add(screener_run)
    await db.commit()
    await db.refresh(screener_run)

    # Queue background task
    # TODO: Replace with actual screener service integration
    background_tasks.add_task(
        run_screener_task,
        run_id=screener_run.id,
        property_id=property_id,
        property_name=property.name,
    )

    return ScreenerStartResponse(
        status="started",
        run_id=screener_run.id,
        property_id=property_id,
        message=f"Screener started for property: {property.name}",
    )


async def run_screener_task(run_id: int, property_id: int, property_name: str):
    """
    Background task to run the screener.

    Integrates with the actual ScreenerService to run property analysis.
    """
    from app.database import async_session_maker
    from app.services.screener_service import get_screener_service

    async with async_session_maker() as db:
        # Get the run record
        result = await db.execute(
            select(ScreenerRun).where(ScreenerRun.id == run_id)
        )
        run = result.scalar_one()

        try:
            # Update status to running
            run.status = "running"
            run.current_step = "Starting screener analysis"
            run.progress_percent = 5
            await db.commit()

            # Progress callback to update database
            async def update_progress(progress):
                run.current_step = progress.step
                run.progress_percent = progress.percent
                await db.commit()

            # Run the actual screener
            service = get_screener_service()
            screener_result = await service.run_analysis(
                property_id=property_id,
                property_name=property_name,
            )

            if screener_result.success:
                run.status = "completed"
                run.completed_at = datetime.utcnow()
                run.current_step = "Complete"
                run.progress_percent = 100
                run.output_excel_path = screener_result.output_excel_path
                if screener_result.maps_generated:
                    run.maps_generated = screener_result.maps_generated
            else:
                run.status = "failed"
                run.error_message = screener_result.error_message
                run.completed_at = datetime.utcnow()

            await db.commit()

        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            await db.commit()


@router.get("/{property_id}/status", response_model=ScreenerRunResponse)
async def get_screener_status(
    property_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of the most recent screener run for a property.
    """
    result = await db.execute(
        select(ScreenerRun)
        .where(ScreenerRun.property_id == property_id)
        .order_by(ScreenerRun.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=404,
            detail="No screener runs found for this property",
        )

    return run


@router.get("/{property_id}/runs", response_model=List[ScreenerRunResponse])
async def list_screener_runs(
    property_id: int,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    List all screener runs for a property.
    """
    result = await db.execute(
        select(ScreenerRun)
        .where(ScreenerRun.property_id == property_id)
        .order_by(ScreenerRun.started_at.desc())
        .limit(limit)
    )
    runs = result.scalars().all()
    return runs


@router.get("/{property_id}/data", response_model=List[ScreenerDataResponse])
async def get_screener_data(
    property_id: int,
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get extracted screener data for a property.

    - **category**: Filter by data category (costar, web_demographics, validation, calculated)
    """
    query = select(ScreenerData).where(ScreenerData.property_id == property_id)

    if category:
        query = query.where(ScreenerData.category == category)

    result = await db.execute(query.order_by(ScreenerData.category, ScreenerData.field_name))
    data = result.scalars().all()
    return data


@router.post("/{property_id}/upload")
async def upload_pdf(
    property_id: int,
    file: UploadFile = File(...),
    pdf_type: str = Query(
        ...,
        description="Type of PDF",
        regex="^(demographic|property|rent_comp|asset_market)$",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a CoStar PDF for a property.

    - **file**: The PDF file to upload
    - **pdf_type**: Type of CoStar report (demographic, property, rent_comp, asset_market)

    The file will be stored in the property's CoStar Reports folder.
    """
    # Validate file type
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Check file size (50MB limit)
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    # Verify property exists
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # TODO: Save file to property folder
    # from app.config import settings
    # folder = settings.properties_path / property.name.replace(" ", "") / "CoStar Reports"
    # folder.mkdir(parents=True, exist_ok=True)
    # file_path = folder / file.filename
    # with open(file_path, "wb") as f:
    #     f.write(content)

    return {
        "status": "uploaded",
        "property_id": property_id,
        "filename": file.filename,
        "pdf_type": pdf_type,
        "size_bytes": len(content),
        # "path": str(file_path),  # TODO: Return actual path
    }


# TODO: Add SSE endpoint for real-time progress
# @router.get("/{property_id}/progress")
# async def screener_progress_stream(property_id: int):
#     """Server-Sent Events endpoint for real-time progress updates."""
#     async def event_generator():
#         while True:
#             # Get current status from database
#             # yield f"data: {json.dumps(status)}\n\n"
#             await asyncio.sleep(1)
#     return StreamingResponse(event_generator(), media_type="text/event-stream")

# TODO: Add map retrieval endpoint
# @router.get("/{property_id}/maps")
# async def get_maps(property_id: int):
#     """Get list of generated maps for a property."""
#     pass

# TODO: Add cancel screener endpoint
# @router.post("/{run_id}/cancel")
# async def cancel_screener(run_id: int):
#     """Cancel a running screener job."""
#     pass
