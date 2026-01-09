"""
Property CRUD API endpoints.

Provides basic Create, Read, Update, Delete operations for properties.

NEW: Also provides Box-based property reading as source of truth.
"""

from typing import List, Optional
from datetime import datetime
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.property import Property, PipelineStatus, BrokerInfo
from app.services.box_service import get_box_service

logger = logging.getLogger(__name__)

router = APIRouter()

# Box folder path for properties
BOX_PROPERTIES_PATH = "3. Underwriting Pipeline/Screener/Properties"


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


class BoxPropertyDetail(BaseModel):
    """Schema for property detail from Box folder."""

    id: str  # Box folder ID
    name: str  # Property name
    zone: Optional[str] = None
    folder_path: str
    contents: List[dict] = []  # List of files/folders in property folder
    has_screener_output: bool = False
    has_costar_reports: bool = False
    has_maps: bool = False
    has_logs: bool = False


class BoxPropertyListResponse(BaseModel):
    """Response for Box-based property listing."""

    properties: List[BoxPropertyDetail]
    box_connected: bool
    warning: Optional[str] = None
    total_count: int


# ----- Helper Functions -----


def clean_property_name(folder_name: str) -> str:
    """Convert folder name to readable property name."""
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', folder_name)
    spaced = spaced.replace('_', ' ')
    return spaced.strip()


async def get_property_from_box(folder_id: str) -> Optional[BoxPropertyDetail]:
    """
    Get property details from Box by folder ID.
    """
    box_service = get_box_service()

    if not box_service.is_connected():
        return None

    try:
        contents = box_service.list_folder(folder_id)

        # Analyze folder contents
        has_screener = any('screener' in item['name'].lower() or 'output' in item['name'].lower() for item in contents)
        has_costar = any('costar' in item['name'].lower() for item in contents)
        has_maps = any('map' in item['name'].lower() for item in contents)
        has_logs = any('log' in item['name'].lower() for item in contents)

        return BoxPropertyDetail(
            id=folder_id,
            name="",  # Will be set by caller
            zone=None,  # Will be set by caller
            folder_path="",  # Will be set by caller
            contents=contents,
            has_screener_output=has_screener,
            has_costar_reports=has_costar,
            has_maps=has_maps,
            has_logs=has_logs
        )
    except Exception as e:
        logger.error(f"Error getting property from Box: {e}")
        return None


async def list_properties_from_box(zone_filter: Optional[str] = None, search: Optional[str] = None) -> BoxPropertyListResponse:
    """
    List all properties from Box folder structure.
    """
    box_service = get_box_service()

    if not box_service.is_connected():
        return BoxPropertyListResponse(
            properties=[],
            box_connected=False,
            warning="Box not connected. Check BOX_CONFIG_JSON environment variable.",
            total_count=0
        )

    try:
        properties_folder_id = box_service.find_folder(BOX_PROPERTIES_PATH)

        if not properties_folder_id:
            return BoxPropertyListResponse(
                properties=[],
                box_connected=True,
                warning=f"Properties folder not found at: {BOX_PROPERTIES_PATH}",
                total_count=0
            )

        zone_folders = box_service.list_folder(properties_folder_id)
        properties = []

        for zone_folder in zone_folders:
            if zone_folder['type'] != 'folder':
                continue

            zone_name = zone_folder['name']

            # Apply zone filter if provided
            if zone_filter and zone_name != zone_filter:
                continue

            property_folders = box_service.list_folder(zone_folder['id'])

            for prop_folder in property_folders:
                if prop_folder['type'] != 'folder':
                    continue

                prop_name = clean_property_name(prop_folder['name'])

                # Apply search filter if provided
                if search and search.lower() not in prop_name.lower():
                    continue

                prop_contents = box_service.list_folder(prop_folder['id'])

                properties.append(BoxPropertyDetail(
                    id=prop_folder['id'],
                    name=prop_name,
                    zone=zone_name,
                    folder_path=f"{BOX_PROPERTIES_PATH}/{zone_name}/{prop_folder['name']}",
                    contents=prop_contents,
                    has_screener_output=any('screener' in item['name'].lower() or 'output' in item['name'].lower() for item in prop_contents),
                    has_costar_reports=any('costar' in item['name'].lower() for item in prop_contents),
                    has_maps=any('map' in item['name'].lower() for item in prop_contents),
                    has_logs=any('log' in item['name'].lower() for item in prop_contents)
                ))

        return BoxPropertyListResponse(
            properties=properties,
            box_connected=True,
            warning=None,
            total_count=len(properties)
        )

    except Exception as e:
        logger.error(f"Error listing properties from Box: {e}")
        return BoxPropertyListResponse(
            properties=[],
            box_connected=True,
            warning=f"Error reading from Box: {str(e)}",
            total_count=0
        )


# ----- API Endpoints -----


@router.get("/", response_model=BoxPropertyListResponse)
async def list_properties(
    zone: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    List all properties from Box folder structure (source of truth).

    Box Path: 3. Underwriting Pipeline/Screener/Properties/Zone*/[PropertyName]/

    - **zone**: Filter by zone folder name
    - **search**: Search by property name
    """
    return await list_properties_from_box(zone_filter=zone, search=search)


@router.get("/db", response_model=List[PropertyResponse])
async def list_properties_from_database(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    zone: Optional[str] = None,
    state: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    LEGACY: List all properties from database.

    Use GET /api/properties/ for Box-based data (source of truth).

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
