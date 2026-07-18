from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.job_card.job_card_models import JobCard, JobCardCreate, JobCardUpdate, JobCardOut, JobStatus
from app.features.customer.customer_models import Customer
from app.features.vehicle.vehicle_models import Vehicle
from app.features.user.user_models import User
from app.core.security import get_current_user
from datetime import datetime, time
from app.core.datetime_utils import get_current_time

from app.features.invoice.invoice_models import Invoice

router = APIRouter(prefix="/job-cards", tags=["Job Cards"])

async def populate_job_card_details(job_card: JobCard) -> JobCardOut:
    customer = await Customer.get(job_card.customer_id)
    vehicle = await Vehicle.get(job_card.vehicle_id)
    mechanic = await User.get(job_card.mechanic_id)
    invoice = await Invoice.find_one(Invoice.job_card_id == job_card.id)
    
    return JobCardOut(
        **job_card.model_dump(),
        mechanic_name=mechanic.full_name if mechanic else "Unknown Mechanic",
        vehicle_number=vehicle.registration_number if vehicle else "Unknown Vehicle",
        customer_name=customer.name if customer else "Unknown Customer",
        payment_status=invoice.payment_status if invoice else "Unpaid",
        is_invoice_created=invoice is not None,
        invoice_id=str(invoice.id) if invoice else None
    )

async def populate_job_cards_list(job_cards: List[JobCard]) -> List[JobCardOut]:
    if not job_cards:
        return []
        
    cust_ids = list({jc.customer_id for jc in job_cards})
    veh_ids = list({jc.vehicle_id for jc in job_cards})
    mech_ids = list({jc.mechanic_id for jc in job_cards})
    job_card_ids = [jc.id for jc in job_cards]
    
    customers = await Customer.find({"_id": {"$in": cust_ids}}).to_list()
    vehicles = await Vehicle.find({"_id": {"$in": veh_ids}}).to_list()
    mechanics = await User.find({"_id": {"$in": mech_ids}}).to_list()
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).to_list()
    
    cust_map = {c.id: c.name for c in customers}
    veh_map = {v.id: v.registration_number for v in vehicles}
    mech_map = {m.id: m.full_name for m in mechanics}
    invoice_map = {inv.job_card_id: inv for inv in invoices}
    
    return [
        JobCardOut(
            **jc.model_dump(),
            mechanic_name=mech_map.get(jc.mechanic_id, "Unknown Mechanic"),
            vehicle_number=veh_map.get(jc.vehicle_id, "Unknown Vehicle"),
            customer_name=cust_map.get(jc.customer_id, "Unknown Customer"),
            payment_status=invoice_map[jc.id].payment_status if jc.id in invoice_map else "Unpaid",
            is_invoice_created=jc.id in invoice_map,
            invoice_id=str(invoice_map[jc.id].id) if jc.id in invoice_map else None
        )
        for jc in job_cards
    ]

async def generate_next_job_no() -> str:
    now = get_current_time()
    day_start = datetime.combine(now.date(), time.min)
    day_end = datetime.combine(now.date(), time.max)
    
    count = await JobCard.find(JobCard.created_at >= day_start, JobCard.created_at <= day_end).count()
    
    while True:
        next_val = count + 1
        job_no = f"{next_val:02d}{now.day:02d}{now.month:02d}{now.year % 100:02d}"
        existing = await JobCard.find_one(JobCard.job_no == job_no)
        if not existing:
            return job_no
        count += 1

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
    return await populate_job_card_details(new_job_card)

@router.get("", response_model=List[JobCardOut])
async def list_job_cards(
    customer_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by customer ID"),
    vehicle_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by vehicle ID"),
    mechanic_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by assigned mechanic ID"),
    status: Optional[JobStatus] = Query(default=None, description="Filter by job status"),
    payment_status: Optional[str] = Query(default=None, description="Filter by payment status (Paid, Unpaid)"),
    search: Optional[str] = Query(default=None, description="Search by Job Number, Customer Name, or Vehicle Registration Number"),
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
        
    if payment_status:
        val = payment_status.strip().lower()
        if val == "paid":
            paid_invoices = await Invoice.find(Invoice.payment_status == "Paid").to_list()
            paid_job_card_ids = [inv.job_card_id for inv in paid_invoices]
            query["_id"] = {"$in": paid_job_card_ids}
        elif val == "partial":
            partial_invoices = await Invoice.find(Invoice.payment_status == "Partial").to_list()
            partial_job_card_ids = [inv.job_card_id for inv in partial_invoices]
            query["_id"] = {"$in": partial_job_card_ids}
        elif val == "unpaid":
            # Unpaid matches either no invoice at all, or an invoice that isn't Paid/Partial
            non_unpaid_invoices = await Invoice.find({"payment_status": {"$in": ["Paid", "Partial"]}}).to_list()
            non_unpaid_job_card_ids = [inv.job_card_id for inv in non_unpaid_invoices]
            query["_id"] = {"$nin": non_unpaid_job_card_ids}

    if search:
        search_str = search.strip()
        # Find matching customer IDs
        matching_customers = await Customer.find({"name": {"$regex": search_str, "$options": "i"}}).to_list()
        cust_ids = [c.id for c in matching_customers]
        
        # Find matching vehicle IDs
        matching_vehicles = await Vehicle.find({"registration_number": {"$regex": search_str, "$options": "i"}}).to_list()
        veh_ids = [v.id for v in matching_vehicles]
        
        # Construct $or query conditions
        conditions = [
            {"job_no": {"$regex": search_str, "$options": "i"}}
        ]
        if cust_ids:
            conditions.append({"customer_id": {"$in": cust_ids}})
        if veh_ids:
            conditions.append({"vehicle_id": {"$in": veh_ids}})
            
        query["$or"] = conditions
        
    job_cards = await JobCard.find(query).sort("-created_at").to_list()
    return await populate_job_cards_list(job_cards)

@router.get("/vehicle/{vehicle_id}", response_model=List[JobCardOut])
async def list_job_cards_by_vehicle(vehicle_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.vehicle_id == vehicle_id).sort("-created_at").to_list()
    return await populate_job_cards_list(job_cards)

@router.get("/customer/{customer_id}", response_model=List[JobCardOut])
async def list_job_cards_by_customer(customer_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.customer_id == customer_id).sort("-created_at").to_list()
    return await populate_job_cards_list(job_cards)

@router.get("/today", response_model=List[JobCardOut])
async def list_todays_job_cards(
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    now = get_current_time()
    
    if start_date:
        start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    else:
        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0)
        
    if end_date:
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    else:
        end_dt = datetime(now.year, now.month, now.day, 23, 59, 59)
    
    job_cards = await JobCard.find(
        JobCard.created_at >= start_dt,
        JobCard.created_at <= end_dt
    ).sort("-created_at").to_list()
    return await populate_job_cards_list(job_cards)

@router.get("/{id}", response_model=JobCardOut)
async def get_job_card(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_card = await JobCard.get(id)
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job card not found"
        )
    return await populate_job_card_details(job_card)

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
        
    job_card.updated_at = get_current_time()
    await job_card.save()
    
    return await populate_job_card_details(job_card)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_card(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_card = await JobCard.get(id)
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job card not found"
        )
        
    # Delete any linked invoice and expense records
    from app.features.expense.expense_models import Expense
    
    # 1. Delete linked invoice
    linked_invoice = await Invoice.find_one(Invoice.job_card_id == id)
    if linked_invoice:
        await linked_invoice.delete()
        
    # 2. Delete linked expense
    linked_expense = await Expense.find_one(Expense.job_card_id == id)
    if linked_expense:
        await linked_expense.delete()
        
    await job_card.delete()
    return None
