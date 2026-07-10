from datetime import datetime
from typing import Optional
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field

class ExpenseBase(BaseModel):
    description: str = Field(..., min_length=1, description="Description of the expense")
    category: str = Field(..., min_length=1, description="Category of the expense")
    amount: float = Field(..., gt=0.0, description="Amount spent")
    date: datetime = Field(..., description="Date of the expense in ISO8601")

class Expense(Document, ExpenseBase):
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str = Field(..., description="User who recorded the expense")

    class Settings:
        name = "expenses"
        indexes = [
            "category",
            "date",
        ]

class ExpenseCreate(ExpenseBase):
    pass

class ExpenseUpdate(BaseModel):
    description: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    date: Optional[datetime] = None

class ExpenseOut(ExpenseBase):
    id: PydanticObjectId
    created_at: datetime
    updated_at: datetime
    created_by: str
