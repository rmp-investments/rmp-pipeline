"""
Pipeline status API endpoints.

Provides endpoints for managing the deal pipeline - status updates, filtering,
and pipeline overview functionality.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.property import Property, PipelineStatus, BrokerInfo


router = APIRouter()


# ----- Pydantic Schemas -----


class PipelineStatusUpdate(BaseModel):
    """Schema for updating pipeline status."""

    phase: Optional[str] = None
    priority: Optional[str] = None
    on_off_market: Optional[str] = None
    offer_due: Optional[datetime] = None
    asking_price: Optional[float] = None
    unit_count: Optional[int] = None
    vintage: Optional[int] = None
    price_per_unit: Optional[float] = None
    pass_reason: Optional[str] = None
    screener_link: Optional[str] = None
    uw_model_link: Optional[str] = None
    offer_submitted: Optional[datetime] = None
    loi_submitted: Optional[datetime] = None
    notes: Optional[str] = None


class BrokerInfoUpdate(BaseModel):
    """Schema for updating broker info."""

    source: Optional[str] = None
    broker_name: Optional[str] = None
    broker_phone: Optional[str] = None
    broker_email: Optional[str] = None
    om_link: Optional[str] = None
    seller_story: Optional[str] = None


class PipelineItemResponse(BaseModel):
    """Schema for a single pipeline item (property with status)."""

    model_config = ConfigDict(from_attributes=True)

    # Property fields
    id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zone: Optional[str] = None

    # Pipeline status fields (flattened for convenience)
    phase: Optional[str] = None
    priority: Optional[str] = None
    on_off_market: Optional[str] = None
    date_added: Optional[datetime] = None
    offer_due: Optional[datetime] = None
    asking_price: Optional[float] = None
    unit_count: Optional[int] = None
    vintage: Optional[int] = None
    price_per_unit: Optional[float] = None
    pass_reason: Optional[str] = None
    screener_link: Optional[str] = None
    notes: Optional[str] = None

    # Broker info fields (flattened)
    source: Optional[str] = None
    broker_name: Optional[str] = None


class PipelineStatsResponse(BaseModel):
    """Schema for pipeline statistics."""

    total_properties: int
    by_phase: dict
    by_zone: dict
    by_priority: dict


# ----- API Endpoints -----


@router.get("/", response_model=List[PipelineItemResponse])
async def get_pipeline(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    phase: Optional[str] = None,
    zone: Optional[str] = None,
    priority: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get pipeline view with all properties and their status.

    This is the main pipeline dashboard data endpoint.

    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **phase**: Filter by pipeline phase
    - **zone**: Filter by geographic zone
    - **priority**: Filter by priority level
    """
    query = (
        select(Property)
        .options(
            selectinload(Property.pipeline_status),
            selectinload(Property.broker_info),
        )
    )

    # Apply filters via joins
    if phase or priority:
        query = query.join(Property.pipeline_status)
        if phase:
            query = query.where(PipelineStatus.phase == phase)
        if priority:
            query = query.where(PipelineStatus.priority == priority)

    if zone:
        query = query.where(Property.zone == zone)

    query = query.offset(skip).limit(limit).order_by(Property.created_at.desc())

    result = await db.execute(query)
    properties = result.scalars().all()

    # Transform to flattened response format
    pipeline_items = []
    for prop in properties:
        status = prop.pipeline_status
        broker = prop.broker_info

        item = PipelineItemResponse(
            id=prop.id,
            name=prop.name,
            address=prop.address,
            city=prop.city,
            state=prop.state,
            zone=prop.zone,
            phase=status.phase if status else None,
            priority=status.priority if status else None,
            on_off_market=status.on_off_market if status else None,
            date_added=status.date_added if status else None,
            offer_due=status.offer_due if status else None,
            asking_price=status.asking_price if status else None,
            unit_count=status.unit_count if status else None,
            vintage=status.vintage if status else None,
            price_per_unit=status.price_per_unit if status else None,
            pass_reason=status.pass_reason if status else None,
            screener_link=status.screener_link if status else None,
            notes=status.notes if status else None,
            source=broker.source if broker else None,
            broker_name=broker.broker_name if broker else None,
        )
        pipeline_items.append(item)

    return pipeline_items


@router.put("/{property_id}/status", response_model=PipelineItemResponse)
async def update_pipeline_status(
    property_id: int,
    status_data: PipelineStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update pipeline status for a property.

    Use this to update phase, priority, notes, pass reason, etc.
    """
    result = await db.execute(
        select(Property)
        .options(
            selectinload(Property.pipeline_status),
            selectinload(Property.broker_info),
        )
        .where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Create pipeline status if it doesn't exist
    if not property.pipeline_status:
        property.pipeline_status = PipelineStatus(property_id=property_id)
        db.add(property.pipeline_status)

    # Update fields that were provided
    update_data = status_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(property.pipeline_status, field, value)

    await db.commit()
    await db.refresh(property)

    # Return flattened response
    status = property.pipeline_status
    broker = property.broker_info

    return PipelineItemResponse(
        id=property.id,
        name=property.name,
        address=property.address,
        city=property.city,
        state=property.state,
        zone=property.zone,
        phase=status.phase if status else None,
        priority=status.priority if status else None,
        on_off_market=status.on_off_market if status else None,
        date_added=status.date_added if status else None,
        offer_due=status.offer_due if status else None,
        asking_price=status.asking_price if status else None,
        unit_count=status.unit_count if status else None,
        vintage=status.vintage if status else None,
        price_per_unit=status.price_per_unit if status else None,
        pass_reason=status.pass_reason if status else None,
        screener_link=status.screener_link if status else None,
        notes=status.notes if status else None,
        source=broker.source if broker else None,
        broker_name=broker.broker_name if broker else None,
    )


@router.put("/{property_id}/phase")
async def update_phase(
    property_id: int,
    phase: str = Query(..., description="New phase value"),
    db: AsyncSession = Depends(get_db),
):
    """
    Quick endpoint to update just the pipeline phase.

    Valid phases: Initial Review, Screener, LOI, Under Contract, Closed, Passed
    """
    valid_phases = [
        "Initial Review",
        "Screener",
        "LOI",
        "Under Contract",
        "Closed",
        "Passed",
    ]

    if phase not in valid_phases:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phase. Must be one of: {valid_phases}",
        )

    result = await db.execute(
        select(PipelineStatus).where(PipelineStatus.property_id == property_id)
    )
    status = result.scalar_one_or_none()

    if not status:
        raise HTTPException(status_code=404, detail="Property not found")

    status.phase = phase
    await db.commit()

    return {"status": "updated", "property_id": property_id, "phase": phase}


@router.put("/{property_id}/broker", response_model=dict)
async def update_broker_info(
    property_id: int,
    broker_data: BrokerInfoUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update broker information for a property.
    """
    result = await db.execute(
        select(Property)
        .options(selectinload(Property.broker_info))
        .where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Create broker info if it doesn't exist
    if not property.broker_info:
        property.broker_info = BrokerInfo(property_id=property_id)
        db.add(property.broker_info)

    # Update fields that were provided
    update_data = broker_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(property.broker_info, field, value)

    await db.commit()

    return {"status": "updated", "property_id": property_id}


@router.get("/stats", response_model=PipelineStatsResponse)
async def get_pipeline_stats(
    db: AsyncSession = Depends(get_db),
):
    """
    Get pipeline statistics - counts by phase, zone, priority.
    """
    # Total count
    total_result = await db.execute(select(func.count(Property.id)))
    total = total_result.scalar()

    # Count by phase
    phase_result = await db.execute(
        select(PipelineStatus.phase, func.count(PipelineStatus.id))
        .group_by(PipelineStatus.phase)
    )
    by_phase = {row[0] or "Unknown": row[1] for row in phase_result.all()}

    # Count by zone
    zone_result = await db.execute(
        select(Property.zone, func.count(Property.id))
        .group_by(Property.zone)
    )
    by_zone = {row[0] or "Unknown": row[1] for row in zone_result.all()}

    # Count by priority
    priority_result = await db.execute(
        select(PipelineStatus.priority, func.count(PipelineStatus.id))
        .group_by(PipelineStatus.priority)
    )
    by_priority = {row[0] or "Unknown": row[1] for row in priority_result.all()}

    return PipelineStatsResponse(
        total_properties=total,
        by_phase=by_phase,
        by_zone=by_zone,
        by_priority=by_priority,
    )


# TODO: Add bulk status update endpoint
# @router.put("/bulk/phase")
# async def bulk_update_phase(property_ids: List[int], phase: str, ...)

# TODO: Add export to Excel endpoint
# @router.get("/export/excel")
# async def export_pipeline_to_excel(...)
