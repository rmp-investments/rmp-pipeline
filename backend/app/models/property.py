"""
SQLAlchemy models for the Pipeline Web App.

Based on data model from WEB_APP_ARCHITECTURE.md Section 4.
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Integer, Float, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Property(Base):
    """
    Core property entity - the central object everything links to.

    Represents a real estate property in the underwriting pipeline.
    """

    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[Optional[str]] = mapped_column(String(500))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    zip_code: Mapped[Optional[str]] = mapped_column(String(20))
    zone: Mapped[Optional[str]] = mapped_column(String(50), index=True)

    # Geolocation
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    parcel_polygon: Mapped[Optional[str]] = mapped_column(Text)  # GeoJSON stored as text

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    pipeline_status: Mapped[Optional["PipelineStatus"]] = relationship(
        back_populates="property", uselist=False, cascade="all, delete-orphan"
    )
    broker_info: Mapped[Optional["BrokerInfo"]] = relationship(
        back_populates="property", uselist=False, cascade="all, delete-orphan"
    )
    screener_runs: Mapped[List["ScreenerRun"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )
    screener_data: Mapped[List["ScreenerData"]] = relationship(
        back_populates="property", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Property(id={self.id}, name='{self.name}')>"


class PipelineStatus(Base):
    """
    Pipeline tracking status for a property.

    Tracks deal progression through the underwriting pipeline.
    """

    __tablename__ = "pipeline_status"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id"), unique=True, index=True
    )

    # Deal Status
    phase: Mapped[Optional[str]] = mapped_column(
        String(50), default="Initial Review"
    )  # "Initial Review", "Screener", "LOI", "Under Contract", "Closed", "Passed"
    priority: Mapped[Optional[str]] = mapped_column(
        String(20), default="Medium"
    )  # "High", "Medium", "Low"
    on_off_market: Mapped[Optional[str]] = mapped_column(String(20))  # "On", "Off"

    # Key Dates
    date_added: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)
    offer_due: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Deal Metrics
    asking_price: Mapped[Optional[float]] = mapped_column(Float)
    unit_count: Mapped[Optional[int]] = mapped_column(Integer)
    vintage: Mapped[Optional[int]] = mapped_column(Integer)  # Year built
    price_per_unit: Mapped[Optional[float]] = mapped_column(Float)

    # Pass/Reject Info
    pass_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Document Links
    screener_link: Mapped[Optional[str]] = mapped_column(String(500))
    uw_model_link: Mapped[Optional[str]] = mapped_column(String(500))

    # Deal Progression
    offer_submitted: Mapped[Optional[datetime]] = mapped_column(DateTime)
    loi_submitted: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship back to property
    property: Mapped["Property"] = relationship(back_populates="pipeline_status")

    def __repr__(self) -> str:
        return f"<PipelineStatus(property_id={self.property_id}, phase='{self.phase}')>"


class BrokerInfo(Base):
    """
    Broker and source information for a property.
    """

    __tablename__ = "broker_info"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id"), unique=True, index=True
    )

    # Source Information
    source: Mapped[Optional[str]] = mapped_column(String(255))  # Brokerage name
    broker_name: Mapped[Optional[str]] = mapped_column(String(255))
    broker_phone: Mapped[Optional[str]] = mapped_column(String(50))
    broker_email: Mapped[Optional[str]] = mapped_column(String(255))

    # Document Links
    om_link: Mapped[Optional[str]] = mapped_column(String(500))

    # Contact History
    last_contact: Mapped[Optional[datetime]] = mapped_column(DateTime)
    seller_story: Mapped[Optional[str]] = mapped_column(Text)

    # Relationship back to property
    property: Mapped["Property"] = relationship(back_populates="broker_info")

    def __repr__(self) -> str:
        return f"<BrokerInfo(property_id={self.property_id}, source='{self.source}')>"


class ScreenerRun(Base):
    """
    Logs each screener execution for a property.
    """

    __tablename__ = "screener_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)

    # Run Status
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # "pending", "running", "completed", "failed"
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # Output
    output_excel_path: Mapped[Optional[str]] = mapped_column(String(500))
    maps_generated: Mapped[Optional[str]] = mapped_column(
        JSON
    )  # List of map file paths

    # Progress tracking
    current_step: Mapped[Optional[str]] = mapped_column(String(100))
    progress_percent: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    # Relationship back to property
    property: Mapped["Property"] = relationship(back_populates="screener_runs")

    def __repr__(self) -> str:
        return f"<ScreenerRun(id={self.id}, property_id={self.property_id}, status='{self.status}')>"


class ScreenerData(Base):
    """
    Stores extracted screener data as key-value pairs.

    Flexible schema for storing various data types from CoStar PDFs,
    web demographics, validation results, etc.
    """

    __tablename__ = "screener_data"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)

    # Data Classification
    category: Mapped[str] = mapped_column(
        String(50)
    )  # "costar", "web_demographics", "validation", "calculated"
    field_name: Mapped[str] = mapped_column(String(100), index=True)
    field_value: Mapped[Optional[str]] = mapped_column(Text)

    # Source and Validation
    source: Mapped[Optional[str]] = mapped_column(String(100))
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship back to property
    property: Mapped["Property"] = relationship(back_populates="screener_data")

    def __repr__(self) -> str:
        return f"<ScreenerData(property_id={self.property_id}, field='{self.field_name}')>"


# TODO: Add Email model for email archive feature
# class Email(Base):
#     """Archives ingested broker emails."""
#     __tablename__ = "emails"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"))
#     subject: Mapped[str] = mapped_column(String(500))
#     from_addr: Mapped[str] = mapped_column(String(255))
#     body: Mapped[str] = mapped_column(Text)
#     received_at: Mapped[datetime] = mapped_column(DateTime)
#     html_path: Mapped[Optional[str]] = mapped_column(String(500))
#     hash: Mapped[str] = mapped_column(String(64), unique=True)  # For deduplication

class Zone(Base):
    """
    Dynamic zone definitions for geographic organization.

    Zones group properties by region for analysis and filtering.
    Managed through the web app settings.
    """

    __tablename__ = "zones"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # "Zone 1", "Zone 2", etc.
    display_name: Mapped[str] = mapped_column(String(100))  # "Zone 1 (CO, NM, WY)"
    states: Mapped[Optional[str]] = mapped_column(Text)  # Comma-separated: "CO,NM,WY"
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Zone(name='{self.name}', states='{self.states}')>"

    def get_states_list(self) -> List[str]:
        """Return states as a list."""
        if not self.states:
            return []
        return [s.strip() for s in self.states.split(",")]


# TODO: Add User model for multi-user authentication
# class User(Base):
#     """User accounts for authentication."""
#     __tablename__ = "users"
#     id: Mapped[int] = mapped_column(primary_key=True)
#     email: Mapped[str] = mapped_column(String(255), unique=True)
#     hashed_password: Mapped[str] = mapped_column(String(255))
#     role: Mapped[str] = mapped_column(String(20))  # "admin", "analyst", "viewer"
#     is_active: Mapped[bool] = mapped_column(Boolean, default=True)
#     created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
