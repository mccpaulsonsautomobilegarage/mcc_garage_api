from datetime import datetime
from typing import List, Optional, Literal
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from app.core.datetime_utils import get_current_time

PaymentStatus = Literal["Pending", "Partial", "Paid"]
PaymentMethod = Literal["Cash", "Card", "UPI", "Bank Transfer", "Other"]

class SparePart(BaseModel):
    description: str = Field(..., description="Description of the spare part")
    qty: float = Field(..., ge=0, description="Quantity")
    unit_price: float = Field(..., ge=0, description="Unit price of the spare part")

class LaborCharge(BaseModel):
    name: str = Field(..., description="Name of the service or labor charge")
    cost: float = Field(..., ge=0, description="Cost of the service")

class InvoiceBase(BaseModel):
    job_card_id: PydanticObjectId = Field(..., description="Linked Job Card ID")
    spare_parts: List[SparePart] = Field(default=[], description="List of spare parts used")
    labor_charges: List[LaborCharge] = Field(default=[], description="List of labor services performed")
    payment_status: PaymentStatus = Field(default="Pending", description="Status of the payment")
    payment_method: PaymentMethod = Field(default="Cash", description="Method used for payment")
    paid_amount: float = Field(default=0.0, description="Amount paid so far (used for Partial/Paid)")

class Invoice(Document, InvoiceBase):
    invoice_no: str = Field(..., unique=True, description="Unique invoice number (e.g. INV-2401)")
    spare_parts_total: float = Field(default=0.0, description="Total cost of spare parts")
    labor_total: float = Field(default=0.0, description="Total cost of labor services")
    grand_total: float = Field(default=0.0, description="Grand total cost (spare parts + labor)")
    paid_amount: float = Field(default=0.0, description="Amount paid so far")
    pending_amount: float = Field(default=0.0, description="Amount pending")
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)
    created_by: str = Field(..., description="Username of the user who registered this invoice")

    def calculate_totals(self):
        self.spare_parts_total = sum(item.qty * item.unit_price for item in self.spare_parts)
        self.labor_total = sum(item.cost for item in self.labor_charges)
        self.grand_total = self.spare_parts_total + self.labor_total
        
        if self.payment_status == "Paid":
            self.paid_amount = self.grand_total
        elif self.payment_status == "Pending":
            self.paid_amount = 0.0
            
        self.paid_amount = min(self.paid_amount, self.grand_total)
        self.pending_amount = max(0.0, self.grand_total - self.paid_amount)

    class Settings:
        name = "invoices"
        indexes = [
            "invoice_no",
            "job_card_id",
            "payment_status",
        ]

class InvoiceCreate(InvoiceBase):
    pass

class InvoiceUpdate(BaseModel):
    job_card_id: Optional[PydanticObjectId] = None
    spare_parts: Optional[List[SparePart]] = None
    labor_charges: Optional[List[LaborCharge]] = None
    payment_status: Optional[PaymentStatus] = None
    payment_method: Optional[PaymentMethod] = None
    paid_amount: Optional[float] = None

class InvoiceOut(InvoiceBase):
    id: PydanticObjectId
    invoice_no: str
    spare_parts_total: float
    labor_total: float
    grand_total: float
    paid_amount: float
    pending_amount: float
    created_at: datetime
    updated_at: datetime
    created_by: str
    job_no: str = ""
    customer_name: str = ""
    customer_mobile_number: str = ""
    registration_number: str = ""
    brand_make: str = ""
    model: str = ""
