from datetime import datetime
from typing import Optional, Literal, List
from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from app.core.datetime_utils import get_current_time

FuelLevel = Literal["Empty", "Quarter", "Half", "Full"]
JobStatus = Literal["In Progress", "Delivered", "Pending Delivery", "Completed"]

JOB_TYPE_MAP = {
    "BD": "Breakdown",
    "PS": "Periodic Service",
    "RR": "Running Repair",
    "BW": "Body Work",
    "AC": "Accident / Insurance Claim",
    "GS": "General Service",
    "WC": "Washing / Cleaning",
    "TY": "Tyre / Wheel Service",
    "EM": "Electrical / Electronics",
    "RW": "Repeat Work",
}

NEXT_SERVICE_TYPES = [
    {"service_type": "General / Basic Service", "typical_work": "Engine oil, oil filter, inspection"},
    {"service_type": "Minor Service", "typical_work": "Oil, filters, fluid checks, inspection"},
    {"service_type": "Major Service", "typical_work": "Oil, filters, fluids, detailed inspection"},
    {"service_type": "Full Service", "typical_work": "Comprehensive vehicle inspection and maintenance"},
    {"service_type": "AC Service", "typical_work": "AC inspection, gas, filter, cooling check"},
    {"service_type": "Brake Service", "typical_work": "Brake inspection, cleaning, pad/disc check"},
    {"service_type": "Engine Service", "typical_work": "Engine inspection and related maintenance"},
    {"service_type": "Transmission Service", "typical_work": "Gearbox/transmission oil and inspection"},
    {"service_type": "Wheel / Tyre Service", "typical_work": "Alignment, balancing, tyre inspection"},
    {"service_type": "Electrical Service", "typical_work": "Battery, lights, wiring, electrical checks"},
    {"service_type": "Cooling System Service", "typical_work": "Coolant, radiator and hose inspection"},
    {"service_type": "Periodic Maintenance", "typical_work": "Manufacturer-scheduled maintenance"},
]

class JobCardBase(BaseModel):
    customer_id: PydanticObjectId = Field(..., description="Linked customer account ID")
    vehicle_id: PydanticObjectId = Field(..., description="Linked registered vehicle ID")
    mechanic_id: Optional[PydanticObjectId] = Field(default=None, description="Primary assigned mechanic user ID (legacy/compatibility)")
    mechanic_ids: List[PydanticObjectId] = Field(default=[], description="List of assigned mechanic user IDs")
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
    job_type: str = Field(default="GS", description="Job type code (BD, PS, RR, BW, AC, GS, WC, TY, EM, RW)")
    next_service_date: Optional[datetime] = Field(default=None, description="Recommended next service date")
    next_service_type: Optional[str] = Field(default=None, description="Recommended next service type")

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
            "mechanic_ids",
            "status",
            "job_type",
        ]

class JobCardCreate(JobCardBase):
    mechanic_id: Optional[PydanticObjectId] = None
    mechanic_ids: Optional[List[PydanticObjectId]] = None

class JobCardUpdate(BaseModel):
    customer_id: Optional[PydanticObjectId] = None
    vehicle_id: Optional[PydanticObjectId] = None
    mechanic_id: Optional[PydanticObjectId] = None
    mechanic_ids: Optional[List[PydanticObjectId]] = None
    status: Optional[JobStatus] = None
    job_type: Optional[str] = None
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
    next_service_date: Optional[datetime] = None
    next_service_type: Optional[str] = None

class JobCardOut(JobCardBase):
    id: PydanticObjectId
    job_no: str
    status: JobStatus
    job_type: str = "GS"
    job_type_name: str = "General Service"
    created_at: datetime
    updated_at: datetime
    created_by: str
    mechanic_id: Optional[PydanticObjectId] = None
    mechanic_name: Optional[str] = None
    mechanic_ids: List[PydanticObjectId] = []
    mechanic_names: List[str] = []
    vehicle_number: str = ""
    customer_name: str = ""
    payment_status: str = "Unpaid"
    is_invoice_created: bool = False
    is_invoice_draft: bool = False
    invoice_id: Optional[str] = None
