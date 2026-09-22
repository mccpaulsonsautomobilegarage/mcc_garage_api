from datetime import datetime
from typing import Optional, List
from beanie import Document
from pydantic import BaseModel, Field
from app.core.datetime_utils import get_current_time

class DeviceToken(Document):
    token: str = Field(unique=True, description="FCM device registration token")
    role: str = Field(default="admin", description="Role of user (admin or mechanic)")
    user_id: Optional[str] = Field(default=None, description="Username or User ID")
    device_type: str = Field(default="android", description="android or ios")
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)

    class Settings:
        name = "device_tokens"
        indexes = [
            "token",
            "role",
            "user_id"
        ]

class RegisterTokenRequest(BaseModel):
    token: str = Field(..., description="FCM registration token")
    role: Optional[str] = Field(default="admin")
    device_type: Optional[str] = Field(default="android")

class NotificationResponse(BaseModel):
    success: bool
    message: str
    sent_count: int = 0
    failure_count: int = 0
