from datetime import datetime
from typing import Optional, Literal
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from app.core.datetime_utils import get_current_time

FuelLevel = Literal["Empty", "Quarter", "Half", "Full"]
JobStatus = Literal["In Progress", "Completed", "Pending Delivery", "Pending Payment"]

class JobCardBase(BaseModel):
    customer_id: PydanticObjectId = Field(..., description="Linked customer account ID")
    vehicle_id: PydanticObjectId = Field(..., description="Linked registered vehicle ID")
    mechanic_id: PydanticObjectId = Field(..., description="Assigned mechanic user ID")
    customer_complaint: str = Field(..., description="Description of customer complaints/requests")
    technician_observation: Optional[str] = Field(default=None, description="Observations from the technician")
    repair_notes: Optional[str] = Field(default=None, description="Notes about repairs performed")
    
    # Exterior checklist
    scratches_present: bool = Field(default=False, description="Scratches present on exterior")
    dents_present: bool = Field(default=False, description="Dents present on exterior")
    broken_glass_lights: bool = Field(default=False, description="Broken glass or lights present")
    
    # Interior checklist
    seat_cover_condition_ok: bool = Field(default=False, description="Seat cover condition is OK")
    dashboard_trim_ok: bool = Field(default=False, description="Dashboard and trim condition is OK")
    floor_mats_present: bool = Field(default=False, description="Floor mats are present")
    
    # Fuel status
    fuel_level: FuelLevel = Field(..., description="Current fuel gauge level")

class JobCard(Document, JobCardBase):
    job_no: str = Field(..., unique=True, description="Unique human-readable job number (e.g. JOB-2401)")
    status: JobStatus = Field(default="In Progress", description="Status of the job")
    created_at: datetime = Field(default_factory=get_current_time)
    updated_at: datetime = Field(default_factory=get_current_time)
    created_by: str = Field(..., description="Username of the user who registered this job card")

    class Settings:
        name = "job_cards"
        indexes = [
            "job_no",
            "customer_id",
            "vehicle_id",
            "mechanic_id",
            "status",
        ]

class JobCardCreate(JobCardBase):
    pass

class JobCardUpdate(BaseModel):
    customer_id: Optional[PydanticObjectId] = None
    vehicle_id: Optional[PydanticObjectId] = None
    mechanic_id: Optional[PydanticObjectId] = None
    status: Optional[JobStatus] = None
    customer_complaint: Optional[str] = None
    technician_observation: Optional[str] = None
    repair_notes: Optional[str] = None
    
    scratches_present: Optional[bool] = None
    dents_present: Optional[bool] = None
    broken_glass_lights: Optional[bool] = None
    
    seat_cover_condition_ok: Optional[bool] = None
    dashboard_trim_ok: Optional[bool] = None
    floor_mats_present: Optional[bool] = None
    
    fuel_level: Optional[FuelLevel] = None

class JobCardOut(JobCardBase):
    id: PydanticObjectId
    job_no: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    created_by: str
    mechanic_name: Optional[str] = None
    vehicle_number: str = ""
    customer_name: str = ""
    payment_status: str = "Unpaid"
    is_invoice_created: bool = False
    invoice_id: Optional[str] = None
