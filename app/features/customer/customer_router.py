from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.customer.customer_models import Customer, CustomerCreate, CustomerUpdate, CustomerOut
from app.core.security import get_current_user, get_current_admin
from datetime import datetime
from app.core.datetime_utils import get_current_time

router = APIRouter(prefix="/customers", tags=["Customers"])

async def get_customer_stats(customer_id: PydanticObjectId) -> dict:
    from app.features.job_card.job_card_models import JobCard
    from app.features.invoice.invoice_models import Invoice
    
    job_cards = await JobCard.find(JobCard.customer_id == customer_id).to_list()
    total_visits = len(job_cards)
    if not job_cards:
        return {"pending": 0.0, "paid": 0.0, "visits": 0}
    job_card_ids = [jc.id for jc in job_cards]
    
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).to_list()
    pending = sum(inv.pending_amount for inv in invoices)
    paid = sum(inv.paid_amount for inv in invoices)
    return {"pending": pending, "paid": paid, "visits": total_visits}

@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(customer_data: CustomerCreate, current_user: dict = Depends(get_current_user)):
    # Check if a customer with the same phone code and number already exists
    existing_customer = await Customer.find_one(
        Customer.phone_code == customer_data.phone_code,
        Customer.phone_number == customer_data.phone_number
    )
    if existing_customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A customer with this phone number is already registered"
        )
        
    new_customer = Customer(
        name=customer_data.name,
        phone_code=customer_data.phone_code,
        phone_number=customer_data.phone_number,
        whatsapp_code=customer_data.whatsapp_code,
        whatsapp_number=customer_data.whatsapp_number,
        email=customer_data.email,
        address=customer_data.address,
        notes=customer_data.notes,
        created_by=current_user["username"]
    )
    
    await new_customer.insert()
    return CustomerOut(
        **new_customer.model_dump(),
        pending_payment_amount=0.0,
        total_paid_amount=0.0,
        total_visits=0
    )

@router.get("", response_model=List[CustomerOut])
async def list_customers(
    search: Optional[str] = Query(default=None, description="Search by name or phone number"),
    current_user: dict = Depends(get_current_user)
):
    if search:
        # Case-insensitive search on name or phone number
        customers = await Customer.find(
            {"$or": [
                {"name": {"$regex": search, "$options": "i"}},
                {"phone_number": {"$regex": search, "$options": "i"}}
            ]}
        ).to_list()
    else:
        customers = await Customer.find_all().to_list()
        
    if not customers:
        return []

    # Efficient bulk fetch of pending payment amounts
    customer_ids = [c.id for c in customers]
    from app.features.job_card.job_card_models import JobCard
    from app.features.invoice.invoice_models import Invoice
    
    job_cards = await JobCard.find({"customer_id": {"$in": customer_ids}}).to_list()
    customer_to_jobs = {}
    for jc in job_cards:
        customer_to_jobs.setdefault(jc.customer_id, []).append(jc.id)
        
    all_job_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find({"job_card_id": {"$in": all_job_ids}}).to_list()
    job_to_pending = {inv.job_card_id: inv.pending_amount for inv in invoices}
    job_to_paid = {inv.job_card_id: inv.paid_amount for inv in invoices}
    
    out_customers = []
    for c in customers:
        job_ids = customer_to_jobs.get(c.id, [])
        visits = len(job_ids)
        pending = sum(job_to_pending.get(jid, 0.0) for jid in job_ids)
        paid = sum(job_to_paid.get(jid, 0.0) for jid in job_ids)
        out_customers.append(
            CustomerOut(
                **c.model_dump(),
                pending_payment_amount=pending,
                total_paid_amount=paid,
                total_visits=visits
            )
        )
    return out_customers

@router.get("/vehicle/{vehicle_id}", response_model=CustomerOut)
async def get_customer_by_vehicle(
    vehicle_id: PydanticObjectId,
    current_user: dict = Depends(get_current_user)
):
    from app.features.vehicle.vehicle_models import Vehicle
    vehicle = await Vehicle.get(vehicle_id)
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
    customer = await Customer.get(vehicle.customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    stats = await get_customer_stats(customer.id)
    return CustomerOut(
        **customer.model_dump(),
        pending_payment_amount=stats["pending"],
        total_paid_amount=stats["paid"],
        total_visits=stats["visits"]
    )

@router.get("/{id}", response_model=CustomerOut)
async def get_customer(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    customer = await Customer.get(id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    stats = await get_customer_stats(customer.id)
    return CustomerOut(
        **customer.model_dump(),
        pending_payment_amount=stats["pending"],
        total_paid_amount=stats["paid"],
        total_visits=stats["visits"]
    )

@router.put("/{id}", response_model=CustomerOut)
async def update_customer(
    id: PydanticObjectId,
    customer_data: CustomerUpdate,
    current_user: dict = Depends(get_current_user)
):
    customer = await Customer.get(id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
        
    # Check if updating to a phone number that belongs to another customer
    if (customer_data.phone_number and customer_data.phone_number != customer.phone_number) or \
       (customer_data.phone_code and customer_data.phone_code != customer.phone_code):
        target_code = customer_data.phone_code or customer.phone_code
        target_number = customer_data.phone_number or customer.phone_number
        existing_phone = await Customer.find_one(
            Customer.phone_code == target_code,
            Customer.phone_number == target_number
        )
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A customer with this phone number is already registered"
            )
            
    update_dict = customer_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(customer, key, value)
        
    customer.updated_at = get_current_time()
    await customer.save()
    
    stats = await get_customer_stats(customer.id)
    return CustomerOut(
        **customer.model_dump(),
        pending_payment_amount=stats["pending"],
        total_paid_amount=stats["paid"],
        total_visits=stats["visits"]
    )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(id: PydanticObjectId, admin: str = Depends(get_current_admin)):
    customer = await Customer.get(id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    await customer.delete()
    return None
