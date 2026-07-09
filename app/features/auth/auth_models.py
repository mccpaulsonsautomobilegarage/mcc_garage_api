from pydantic import BaseModel, Field, model_validator, field_validator
from typing import Optional
import re

def clean_and_format_phone(v: str) -> str:
    cleaned = re.sub(r'[^\d+]', '', v)
    if cleaned.startswith('+'):
        if len(cleaned) >= 8:
            return cleaned
        raise ValueError('Invalid phone number format')
    if len(cleaned) == 10 and cleaned.isdigit():
        return f"+91{cleaned}"
    if len(cleaned) == 12 and cleaned.startswith('91'):
        return f"+{cleaned}"
    raise ValueError('Phone number must be a 10-digit number or include a country code')

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str

class UserRegister(BaseModel):
    full_name: str
    phone_number: str
    salary_monthly: Optional[str] = None
    experience: Optional[str] = None
    specialization: Optional[str] = None
    username: str
    password: str
    confirm_password: str

    @field_validator('phone_number')
    @classmethod
    def format_phone_number(cls, v: str) -> str:
        try:
            return clean_and_format_phone(v)
        except ValueError as e:
            raise ValueError(str(e))

    @model_validator(mode='after')
    def check_passwords_match(self) -> 'UserRegister':
        if self.password != self.confirm_password:
            raise ValueError('Passwords do not match')
        return self

class UserLogin(BaseModel):
    username: str
    password: str

from beanie import PydanticObjectId
from datetime import datetime

class UserOut(BaseModel):
    id: PydanticObjectId
    full_name: str
    phone_number: str
    salary_monthly: Optional[str] = None
    experience: Optional[str] = None
    specialization: Optional[str] = None
    username: str
    role: str
    is_active: bool
    created_at: datetime

