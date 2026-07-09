from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, field_validator
import re

def clean_and_format_phone(v: str) -> str:
    # Remove all non-digit and non-plus characters
    cleaned = re.sub(r'[^\d+]', '', v)
    
    # Check if it has a plus sign and seems like a full international number
    if cleaned.startswith('+'):
        if len(cleaned) >= 8:
            return cleaned
        raise ValueError('Invalid phone number format')
        
    # If it is exactly 10 digits, prepend +91
    if len(cleaned) == 10 and cleaned.isdigit():
        return f"+91{cleaned}"
        
    # If it already starts with 91 and has 12 digits (but no +), prepending + is also good
    if len(cleaned) == 12 and cleaned.startswith('91'):
        return f"+{cleaned}"
        
    raise ValueError('Phone number must be a 10-digit number or include a country code')

class CustomerBase(BaseModel):
    name: str = Field(..., min_length=1, description="Customer's full name")
    phone_number: str = Field(..., description="Customer's mobile number")
    whatsapp_number: str = Field(..., description="Customer's WhatsApp number")
    email: Optional[str] = Field(default=None, description="Optional email address")
    address: str = Field(..., min_length=1, description="Customer's address")
    gst_number: Optional[str] = Field(default=None, description="Optional GST number")
    notes: Optional[str] = Field(default=None, description="Optional customer notes")

class Customer(Document, CustomerBase):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(..., description="Username of the user who registered this customer")

    class Settings:
        name = "customers"
        indexes = [
            "phone_number",
            "name",
        ]

class CustomerCreate(CustomerBase):
    @field_validator('phone_number', 'whatsapp_number')
    @classmethod
    def format_phone_fields(cls, v: str) -> str:
        try:
            return clean_and_format_phone(v)
        except ValueError as e:
            raise ValueError(str(e))

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    whatsapp_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    notes: Optional[str] = None

    @field_validator('phone_number', 'whatsapp_number')
    @classmethod
    def format_phone_fields(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        try:
            return clean_and_format_phone(v)
        except ValueError as e:
            raise ValueError(str(e))

class CustomerOut(CustomerBase):
    id: PydanticObjectId
    created_at: datetime
    updated_at: datetime
    created_by: str
