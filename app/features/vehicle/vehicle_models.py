from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, field_validator, StringConstraints
from typing_extensions import Annotated
from app.core.datetime_utils import get_current_time

class VehicleBase(BaseModel):
    customer_id: PydanticObjectId = Field(..., description="ID of the customer who owns this vehicle")
    registration_number: str = Field(..., description="Unique vehicle registration number (e.g. MH12AA1234)")
    brand_make: str = Field(..., min_length=1, description="Brand or make of the vehicle (e.g. Porsche)")
    model: Optional[str] = Field(default=None, description="Model of the vehicle (e.g. 911 GT3)")
    variant: Optional[str] = Field(default=None, description="Variant of the vehicle (e.g. Touring)")
    mfg_year: Optional[int] = Field(default=None, ge=1900, description="Manufacturing year")
    fuel_type: str = Field(..., min_length=1, description="Fuel type (e.g. Petrol, Diesel, Electric, Hybrid, CNG)")
    color: Optional[str] = Field(default=None, description="Color of the vehicle")
    odometer_reading: Optional[float] = Field(default=None, ge=0.0, description="Current odometer reading in km")
    chassis_number: Optional[str] = Field(default=None, description="Optional chassis number")
    engine_number: Optional[str] = Field(default=None, description="Optional engine number")
    insurance_expiry_date: Optional[datetime] = Field(default=None, description="Optional Insurance expiry date (ISO 8601 format)")
    rc_details: Optional[Annotated[str, StringConstraints(max_length=50)]] = Field(default=None, description="Optional Registration Card (RC) details, max 50 chars")

class Vehicle(Document, VehicleBase):
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)
    created_by: str = Field(..., description="Username of the user who registered this vehicle")

    class Settings:
        name = "vehicles"
        indexes = [
            "registration_number",
            "customer_id",
        ]

class VehicleCreate(VehicleBase):
    @field_validator('registration_number')
    @classmethod
    def clean_registration_number(cls, v: str) -> str:
        cleaned = v.strip().upper().replace(" ", "").replace("-", "")
        if not cleaned:
            raise ValueError("Registration number cannot be empty")
        return cleaned

    @field_validator('mfg_year')
    @classmethod
    def validate_mfg_year(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        current_year = datetime.now().year
        if v > current_year + 1:
            raise ValueError(f"Manufacturing year cannot be in the future (max {current_year + 1})")
        return v

class VehicleUpdate(BaseModel):
    customer_id: Optional[PydanticObjectId] = None
    registration_number: Optional[str] = None
    brand_make: Optional[str] = None
    model: Optional[str] = None
    variant: Optional[str] = None
    mfg_year: Optional[int] = None
    fuel_type: Optional[str] = None
    color: Optional[str] = None
    odometer_reading: Optional[float] = None
    chassis_number: Optional[str] = None
    engine_number: Optional[str] = None
    insurance_expiry_date: Optional[datetime] = None
    rc_details: Optional[str] = None

    @field_validator('registration_number')
    @classmethod
    def clean_registration_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        cleaned = v.strip().upper().replace(" ", "").replace("-", "")
        if not cleaned:
            raise ValueError("Registration number cannot be empty")
        return cleaned

    @field_validator('mfg_year')
    @classmethod
    def validate_mfg_year(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return v
        current_year = datetime.now().year
        if v > current_year + 1:
            raise ValueError(f"Manufacturing year cannot be in the future (max {current_year + 1})")
        return v

class VehicleOut(VehicleBase):
    id: PydanticObjectId
    created_at: datetime
    updated_at: datetime
    created_by: str
    customer_name: str = ""
