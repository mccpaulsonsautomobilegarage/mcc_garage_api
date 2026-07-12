from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, field_validator
from app.core.datetime_utils import get_current_time
import re

def clean_phone_code(v: str) -> str:
    cleaned = re.sub(r'[^\d+]', '', v)
    if not cleaned.startswith('+'):
        cleaned = f"+{cleaned}"
    if len(cleaned) < 2:
        raise ValueError('Invalid phone country code format')
    return cleaned

def clean_phone_number(v: str) -> str:
    cleaned = re.sub(r'\D', '', v)
    if len(cleaned) < 4 or len(cleaned) > 15:
        raise ValueError('Phone number must be between 4 and 15 digits')
    return cleaned

class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, description="Customer's full name")
    phone_code: str = Field(default="+91", description="Customer's mobile country code")
    phone_number: str = Field(..., description="Customer's mobile number")
    whatsapp_code: str = Field(default="+91", description="Customer's WhatsApp country code")
    whatsapp_number: str = Field(..., description="Customer's WhatsApp number")
    email: Optional[str] = Field(default=None, description="Optional email address")
    address: Optional[str] = Field(default=None, description="Optional customer address")
    notes: Optional[str] = Field(default=None, description="Optional customer notes")

class Customer(Document, CustomerBase):
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)
    created_by: str = Field(..., description="Username of the user who registered this customer")

    class Settings:
        name = "customers"
        indexes = [
            "phone_number",
            "phone_code",
            "name",
        ]

class CustomerCreate(CustomerBase):
    @field_validator('phone_code', 'whatsapp_code')
    @classmethod
    def validate_phone_code(cls, v: str) -> str:
        try:
            return clean_phone_code(v)
        except ValueError as e:
            raise ValueError(str(e))

    @field_validator('phone_number', 'whatsapp_number')
    @classmethod
    def validate_phone_number(cls, v: str) -> str:
        try:
            return clean_phone_number(v)
        except ValueError as e:
            raise ValueError(str(e))

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone_code: Optional[str] = None
    phone_number: Optional[str] = None
    whatsapp_code: Optional[str] = None
    whatsapp_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None

    @field_validator('phone_code', 'whatsapp_code')
    @classmethod
    def validate_phone_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            return clean_phone_code(v)
        except ValueError as e:
            raise ValueError(str(e))

    @field_validator('phone_number', 'whatsapp_number')
    @classmethod
    def validate_phone_number(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            return clean_phone_number(v)
        except ValueError as e:
            raise ValueError(str(e))

class CustomerOut(CustomerBase):
    id: PydanticObjectId
    created_at: datetime
    updated_at: datetime
    created_by: str
    pending_payment_amount: float = 0.0
    total_paid_amount: float = 0.0
    total_visits: int = 0
