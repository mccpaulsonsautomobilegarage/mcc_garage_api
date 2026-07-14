from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from app.core.datetime_utils import get_current_time

class ExpenseBase(BaseModel):
    description: Optional[str] = Field(default=None, description="Description of the expense")
    category: str = Field(..., min_length=1, description="Category of the expense")
    amount: float = Field(..., gt=0.0, description="Amount spent")
    date: datetime = Field(..., description="Date of the expense in ISO8601")
    job_card_id: Optional[PydanticObjectId] = Field(default=None, description="Associated job card ID")

class Expense(Document, ExpenseBase):
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)
    created_by: str = Field(..., description="User who recorded the expense")

    class Settings:
        name = "expenses"
        indexes = [
            "category",
            "date",
            "job_card_id",
        ]

class ExpenseCreate(ExpenseBase):
    pass

class ExpenseUpdate(BaseModel):
    description: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[datetime] = None
    job_card_id: Optional[PydanticObjectId] = None

class ExpenseOut(ExpenseBase):
    id: PydanticObjectId
    created_at: datetime
    updated_at: datetime
    created_by: str
