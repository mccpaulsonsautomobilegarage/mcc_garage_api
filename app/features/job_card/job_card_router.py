from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.job_card.job_card_models import JobCard, JobCardCreate, JobCardUpdate, JobCardOut, JobStatus
from app.features.customer.customer_models import Customer
from app.features.vehicle.vehicle_models import Vehicle
from app.features.user.user_models import User
from app.core.security import get_current_user
from datetime import datetime

router = APIRouter(prefix="/job-cards", tags=["Job Cards"])

async def generate_next_job_no() -> str:
    # Find the latest registered job card sorted by creation time
    last_jobs = await JobCard.find_all().sort("-created_at").limit(1).to_list()
    if not last_jobs:
        return "JOB-2401"
    
    last_job_no = last_jobs[0].job_no
    try:
        parts = last_job_no.split("-")
        if len(parts) == 2:
            num = int(parts[1])
            return f"JOB-{num + 1}"
    except (ValueError, IndexError):
        pass
    
    # Fallback default
    return "JOB-2401"

@router.post("", response_model=JobCardOut, status_code=status.HTTP_201_CREATED)
async def create_job_card(job_card_data: JobCardCreate, current_user: dict = Depends(get_current_user)):
    # 1. Verify Customer exists
    customer = await Customer.get(job_card_data.customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The linked customer account does not exist"
        )
        
    # 2. Verify Vehicle exists and belongs to the customer
    vehicle = await Vehicle.get(job_card_data.vehicle_id)
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The linked vehicle does not exist"
        )
    if vehicle.customer_id != job_card_data.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selected vehicle does not belong to the selected customer"
        )
        
    # 3. Verify Mechanic exists and has the 'mechanic' role
    mechanic = await User.get(job_card_data.mechanic_id)
    if not mechanic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The assigned mechanic does not exist"
        )
    if mechanic.role != "mechanic":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The assigned user is not a mechanic"
        )
        
    # Generate sequential Job Number
    next_job_no = await generate_next_job_no()
    
    new_job_card = JobCard(
        job_no=next_job_no,
        customer_id=job_card_data.customer_id,
        vehicle_id=job_card_data.vehicle_id,
        mechanic_id=job_card_data.mechanic_id,
        status="In Progress", # Default initial status
        customer_complaint=job_card_data.customer_complaint,
        technician_observation=job_card_data.technician_observation,
        repair_notes=job_card_data.repair_notes,
        scratches_present=job_card_data.scratches_present,
        dents_present=job_card_data.dents_present,
        broken_glass_lights=job_card_data.broken_glass_lights,
        seat_cover_condition_ok=job_card_data.seat_cover_condition_ok,
        dashboard_trim_ok=job_card_data.dashboard_trim_ok,
        floor_mats_present=job_card_data.floor_mats_present,
        fuel_level=job_card_data.fuel_level,
        created_by=current_user["username"]
    )
    
    await new_job_card.insert()
    return JobCardOut(
        **new_job_card.model_dump(),
        mechanic_name=mechanic.full_name,
        vehicle_number=vehicle.registration_number,
        customer_name=customer.name
    )

@router.get("", response_model=List[JobCardOut])
async def list_job_cards(
    customer_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by customer ID"),
    vehicle_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by vehicle ID"),
    mechanic_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by assigned mechanic ID"),
    status: Optional[JobStatus] = Query(default=None, description="Filter by job status"),
    search: Optional[str] = Query(default=None, description="Search by Job Number (case-insensitive)"),
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if customer_id:
        query["customer_id"] = customer_id
    if vehicle_id:
        query["vehicle_id"] = vehicle_id
    if mechanic_id:
        query["mechanic_id"] = mechanic_id
    if status:
        query["status"] = status
    if search:
        query["job_no"] = {"$regex": search.strip().upper(), "$options": "i"}
        
    job_cards = await JobCard.find(query).to_list()
    if not job_cards:
        return []
        
    cust_ids = list({jc.customer_id for jc in job_cards})
    veh_ids = list({jc.vehicle_id for jc in job_cards})
    mech_ids = list({jc.mechanic_id for jc in job_cards})
    
    customers = await Customer.find({"_id": {"$in": cust_ids}}).to_list()
    vehicles = await Vehicle.find({"_id": {"$in": veh_ids}}).to_list()
    mechanics = await User.find({"_id": {"$in": mech_ids}}).to_list()
    
    cust_map = {c.id: c.name for c in customers}
    veh_map = {v.id: v.registration_number for v in vehicles}
    mech_map = {m.id: m.full_name for m in mechanics}
    
    return [
        JobCardOut(
            **jc.model_dump(),
            mechanic_name=mech_map.get(jc.mechanic_id, "Unknown Mechanic"),
            vehicle_number=veh_map.get(jc.vehicle_id, "Unknown Vehicle"),
            customer_name=cust_map.get(jc.customer_id, "Unknown Customer")
        )
        for jc in job_cards
    ]

@router.get("/vehicle/{vehicle_id}", response_model=List[JobCardOut])
async def list_job_cards_by_vehicle(vehicle_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.vehicle_id == vehicle_id).to_list()
    if not job_cards:
        return []
        
    cust_ids = list({jc.customer_id for jc in job_cards})
    mech_ids = list({jc.mechanic_id for jc in job_cards})
    
    customers = await Customer.find({"_id": {"$in": cust_ids}}).to_list()
    mechanics = await User.find({"_id": {"$in": mech_ids}}).to_list()
    
    vehicle = await Vehicle.get(vehicle_id)
    vehicle_number = vehicle.registration_number if vehicle else "Unknown Vehicle"
    
    cust_map = {c.id: c.name for c in customers}
    mech_map = {m.id: m.full_name for m in mechanics}
    
    return [
        JobCardOut(
            **jc.model_dump(),
            mechanic_name=mech_map.get(jc.mechanic_id, "Unknown Mechanic"),
            vehicle_number=vehicle_number,
            customer_name=cust_map.get(jc.customer_id, "Unknown Customer")
        )
        for jc in job_cards
    ]

@router.get("/customer/{customer_id}", response_model=List[JobCardOut])
async def list_job_cards_by_customer(customer_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.customer_id == customer_id).to_list()
    if not job_cards:
        return []
        
    cust_ids = list({jc.customer_id for jc in job_cards})
    veh_ids = list({jc.vehicle_id for jc in job_cards})
    mech_ids = list({jc.mechanic_id for jc in job_cards})
    
    customers = await Customer.find({"_id": {"$in": cust_ids}}).to_list()
    vehicles = await Vehicle.find({"_id": {"$in": veh_ids}}).to_list()
    mechanics = await User.find({"_id": {"$in": mech_ids}}).to_list()
    
    cust_map = {c.id: c.name for c in customers}
    veh_map = {v.id: v.registration_number for v in vehicles}
    mech_map = {m.id: m.full_name for m in mechanics}
    
    return [
        JobCardOut(
            **jc.model_dump(),
            mechanic_name=mech_map.get(jc.mechanic_id, "Unknown Mechanic"),
            vehicle_number=veh_map.get(jc.vehicle_id, "Unknown Vehicle"),
            customer_name=cust_map.get(jc.customer_id, "Unknown Customer")
        )
        for jc in job_cards
    ]

@router.get("/{id}", response_model=JobCardOut)
async def get_job_card(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_card = await JobCard.get(id)
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job card not found"
        )
    customer = await Customer.get(job_card.customer_id)
    vehicle = await Vehicle.get(job_card.vehicle_id)
    mechanic = await User.get(job_card.mechanic_id)
    
    return JobCardOut(
        **job_card.model_dump(),
        mechanic_name=mechanic.full_name if mechanic else "Unknown Mechanic",
        vehicle_number=vehicle.registration_number if vehicle else "Unknown Vehicle",
        customer_name=customer.name if customer else "Unknown Customer"
    )

@router.put("/{id}", response_model=JobCardOut)
async def update_job_card(
    id: PydanticObjectId,
    job_card_data: JobCardUpdate,
    current_user: dict = Depends(get_current_user)
):
    job_card = await JobCard.get(id)
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job card not found"
        )
        
    # Check dependencies if IDs are modified
    target_customer_id = job_card_data.customer_id or job_card.customer_id
    target_vehicle_id = job_card_data.vehicle_id or job_card.vehicle_id
    
    if job_card_data.customer_id and job_card_data.customer_id != job_card.customer_id:
        customer = await Customer.get(job_card_data.customer_id)
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The linked customer account does not exist"
            )
            
    if job_card_data.vehicle_id and job_card_data.vehicle_id != job_card.vehicle_id:
        vehicle = await Vehicle.get(job_card_data.vehicle_id)
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The linked vehicle does not exist"
            )
        if vehicle.customer_id != target_customer_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The selected vehicle does not belong to the selected customer"
            )
            
    if job_card_data.mechanic_id and job_card_data.mechanic_id != job_card.mechanic_id:
        mechanic = await User.get(job_card_data.mechanic_id)
        if not mechanic:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The assigned mechanic does not exist"
            )
        if mechanic.role != "mechanic":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The assigned user is not a mechanic"
            )
            
    update_dict = job_card_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(job_card, key, value)
        
    job_card.updated_at = datetime.utcnow()
    await job_card.save()
    
    customer = await Customer.get(job_card.customer_id)
    vehicle = await Vehicle.get(job_card.vehicle_id)
    mechanic = await User.get(job_card.mechanic_id)
    
    return JobCardOut(
        **job_card.model_dump(),
        mechanic_name=mechanic.full_name if mechanic else "Unknown Mechanic",
        vehicle_number=vehicle.registration_number if vehicle else "Unknown Vehicle",
        customer_name=customer.name if customer else "Unknown Customer"
    )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_card(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_card = await JobCard.get(id)
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job card not found"
        )
    await job_card.delete()
    return None
