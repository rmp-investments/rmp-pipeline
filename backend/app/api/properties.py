"""
Property CRUD API endpoints.

Provides basic Create, Read, Update, Delete operations for properties.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.property import Property, PipelineStatus, BrokerInfo


router = APIRouter()


# ----- Pydantic Schemas -----


class PipelineStatusSchema(BaseModel):
    """Schema for pipeline status data."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    phase: Optional[str] = "Initial Review"
    priority: Optional[str] = "Medium"
    on_off_market: Optional[str] = None
    date_added: Optional[datetime] = None
    offer_due: Optional[datetime] = None
    asking_price: Optional[float] = None
    unit_count: Optional[int] = None
    vintage: Optional[int] = None
    price_per_unit: Optional[float] = None
    pass_reason: Optional[str] = None
    screener_link: Optional[str] = None
    uw_model_link: Optional[str] = None
    notes: Optional[str] = None


class BrokerInfoSchema(BaseModel):
    """Schema for broker information."""

    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    source: Optional[str] = None
    broker_name: Optional[str] = None
    broker_phone: Optional[str] = None
    broker_email: Optional[str] = None
    om_link: Optional[str] = None
    seller_story: Optional[str] = None


class PropertyCreate(BaseModel):
    """Schema for creating a new property."""

    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    zone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    # Optional nested data
    pipeline_status: Optional[PipelineStatusSchema] = None
    broker_info: Optional[BrokerInfoSchema] = None


class PropertyUpdate(BaseModel):
    """Schema for updating a property."""

    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    zone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class PropertyResponse(BaseModel):
    """Schema for property response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    zone: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    pipeline_status: Optional[PipelineStatusSchema] = None
    broker_info: Optional[BrokerInfoSchema] = None


# ----- API Endpoints -----


@router.get("/", response_model=List[PropertyResponse])
async def list_properties(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    zone: Optional[str] = None,
    state: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List all properties with optional filtering.

    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum number of records to return
    - **zone**: Filter by zone
    - **state**: Filter by state
    - **search**: Search by property name
    """
    query = select(Property).options(
        selectinload(Property.pipeline_status),
        selectinload(Property.broker_info),
    )

    # Apply filters
    if zone:
        query = query.where(Property.zone == zone)
    if state:
        query = query.where(Property.state == state)
    if search:
        query = query.where(Property.name.ilike(f"%{search}%"))

    query = query.offset(skip).limit(limit).order_by(Property.created_at.desc())

    result = await db.execute(query)
    properties = result.scalars().all()
    return properties


@router.post("/", response_model=PropertyResponse, status_code=201)
async def create_property(
    property_data: PropertyCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new property.

    Optionally include pipeline_status and broker_info in the request body.
    """
    # Create property
    property = Property(
        name=property_data.name,
        address=property_data.address,
        city=property_data.city,
        state=property_data.state,
        zip_code=property_data.zip_code,
        zone=property_data.zone,
        latitude=property_data.latitude,
        longitude=property_data.longitude,
    )
    db.add(property)
    await db.flush()  # Get the ID

    # Create pipeline status if provided (or create default)
    status_data = property_data.pipeline_status or PipelineStatusSchema()
    pipeline_status = PipelineStatus(
        property_id=property.id,
        phase=status_data.phase,
        priority=status_data.priority,
        on_off_market=status_data.on_off_market,
        date_added=status_data.date_added or datetime.utcnow(),
        asking_price=status_data.asking_price,
        unit_count=status_data.unit_count,
        vintage=status_data.vintage,
        price_per_unit=status_data.price_per_unit,
        notes=status_data.notes,
    )
    db.add(pipeline_status)

    # Create broker info if provided
    if property_data.broker_info:
        broker_info = BrokerInfo(
            property_id=property.id,
            source=property_data.broker_info.source,
            broker_name=property_data.broker_info.broker_name,
            broker_phone=property_data.broker_info.broker_phone,
            broker_email=property_data.broker_info.broker_email,
            om_link=property_data.broker_info.om_link,
            seller_story=property_data.broker_info.seller_story,
        )
        db.add(broker_info)

    await db.commit()
    await db.refresh(property)

    # Reload with relationships
    result = await db.execute(
        select(Property)
        .options(
            selectinload(Property.pipeline_status),
            selectinload(Property.broker_info),
        )
        .where(Property.id == property.id)
    )
    return result.scalar_one()


@router.get("/{property_id}", response_model=PropertyResponse)
async def get_property(
    property_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single property by ID.
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

    return property


@router.put("/{property_id}", response_model=PropertyResponse)
async def update_property(
    property_id: int,
    property_data: PropertyUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a property's basic information.

    Use /api/pipeline/{id}/status for updating pipeline status.
    """
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    # Update fields that were provided
    update_data = property_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(property, field, value)

    await db.commit()
    await db.refresh(property)

    # Reload with relationships
    result = await db.execute(
        select(Property)
        .options(
            selectinload(Property.pipeline_status),
            selectinload(Property.broker_info),
        )
        .where(Property.id == property_id)
    )
    return result.scalar_one()


@router.delete("/{property_id}", status_code=204)
async def delete_property(
    property_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a property and all related data.

    This is a hard delete. Consider implementing soft delete for production.
    """
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    property = result.scalar_one_or_none()

    if not property:
        raise HTTPException(status_code=404, detail="Property not found")

    await db.delete(property)
    await db.commit()

    return None


# TODO: Add batch operations
# @router.post("/batch", response_model=List[PropertyResponse])
# async def create_properties_batch(...)

# TODO: Add export endpoint
# @router.get("/export/excel")
# async def export_properties_to_excel(...)

# TODO: Add import from Excel endpoint
# @router.post("/import/excel")
# async def import_properties_from_excel(...)
