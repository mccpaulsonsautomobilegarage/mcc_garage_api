from pydantic import BaseModel, Field, model_validator, field_validator
from typing import Optional
from beanie import PydanticObjectId
from datetime import datetime
from app.features.customer.customer_models import clean_phone_code, clean_phone_number

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str

class UserRegister(BaseModel):
    full_name: str
    phone_code: str = Field(default="+91", description="Country code (e.g. +91)")
    phone_number: str = Field(..., description="Mobile number")
    salary_monthly: Optional[str] = None
    experience: Optional[str] = None
    specialization: Optional[str] = None
    username: str
    password: str
    confirm_password: str

    @field_validator('phone_code')
    @classmethod
    def format_phone_code(cls, v: str) -> str:
        try:
            return clean_phone_code(v)
        except ValueError as e:
            raise ValueError(str(e))

    @field_validator('phone_number')
    @classmethod
    def format_phone_number(cls, v: str) -> str:
        try:
            return clean_phone_number(v)
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

class UserOut(BaseModel):
    id: PydanticObjectId
    full_name: str
    phone_code: str
    phone_number: str
    salary_monthly: Optional[str] = None
    experience: Optional[str] = None
    specialization: Optional[str] = None
    username: str
    role: str
    is_active: bool
    created_at: datetime
