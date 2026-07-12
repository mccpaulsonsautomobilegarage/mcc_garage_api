from datetime import datetime
from typing import Optional
from beanie import Document
from pydantic import Field
from app.core.datetime_utils import get_current_time

class User(Document):
    full_name: str
    phone_code: str
    phone_number: str
    salary_monthly: Optional[str] = None
    experience: Optional[str] = None
    specialization: Optional[str] = None
    username: str = Field(unique=True)
    password_hash: str
    password: Optional[str] = None
    role: str = "mechanic"
    is_active: bool = True
    created_at: datetime = Field(default_factory=get_current_time)

    class Settings:
        name = "users"
