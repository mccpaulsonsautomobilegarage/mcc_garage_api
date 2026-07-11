from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.invoice.invoice_models import Invoice, InvoiceCreate, InvoiceUpdate, InvoiceOut, PaymentStatus
from app.features.job_card.job_card_models import JobCard
from app.core.security import get_current_user
from datetime import datetime
from app.features.customer.customer_models import Customer
from app.features.vehicle.vehicle_models import Vehicle

router = APIRouter(prefix="/invoices", tags=["Invoices"])

async def populate_invoice_details(invoice: Invoice) -> InvoiceOut:
    job_card = await JobCard.get(invoice.job_card_id)
    if not job_card:
        return InvoiceOut(**invoice.model_dump())
        
    customer = await Customer.get(job_card.customer_id)
    vehicle = await Vehicle.get(job_card.vehicle_id)
    
    return InvoiceOut(
        **invoice.model_dump(),
        job_no=job_card.job_no,
        customer_name=customer.name if customer else "Unknown Customer",
        customer_mobile_number=f"{customer.phone_code} {customer.phone_number}".strip() if customer else "",
        registration_number=vehicle.registration_number if vehicle else "Unknown Vehicle",
        brand_make=vehicle.brand_make if vehicle else "Unknown Brand",
        model=vehicle.model if (vehicle and vehicle.model) else ""
    )

async def populate_invoices_list(invoices: List[Invoice]) -> List[InvoiceOut]:
    if not invoices:
        return []
        
    job_card_ids = list({inv.job_card_id for inv in invoices})
    job_cards = await JobCard.find({"_id": {"$in": job_card_ids}}).to_list()
    job_card_map = {jc.id: jc for jc in job_cards}
    
    customer_ids = list({jc.customer_id for jc in job_cards})
    vehicle_ids = list({jc.vehicle_id for jc in job_cards})
    
    customers = await Customer.find({"_id": {"$in": customer_ids}}).to_list()
    vehicles = await Vehicle.find({"_id": {"$in": vehicle_ids}}).to_list()
    
    customer_map = {c.id: c for c in customers}
    vehicle_map = {v.id: v for v in vehicles}
    
    results = []
    for inv in invoices:
        jc = job_card_map.get(inv.job_card_id)
        cust = customer_map.get(jc.customer_id) if jc else None
        veh = vehicle_map.get(jc.vehicle_id) if jc else None
        
        results.append(
            InvoiceOut(
                **inv.model_dump(),
                job_no=jc.job_no if jc else "",
                customer_name=cust.name if cust else "Unknown Customer",
                customer_mobile_number=f"{cust.phone_code} {cust.phone_number}".strip() if cust else "",
                registration_number=veh.registration_number if veh else "Unknown Vehicle",
                brand_make=veh.brand_make if veh else "Unknown Brand",
                model=veh.model if (veh and veh.model) else ""
            )
        )
    return results

async def generate_next_invoice_no() -> str:
    # Find the latest registered invoice sorted by creation time
    last_invoices = await Invoice.find_all().sort("-created_at").limit(1).to_list()
    if not last_invoices:
        return "INV-2401"
    
    last_invoice_no = last_invoices[0].invoice_no
    try:
        parts = last_invoice_no.split("-")
        if len(parts) == 2:
            num = int(parts[1])
            return f"INV-{num + 1}"
    except (ValueError, IndexError):
        pass
    
    return "INV-2401"

@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_invoice(invoice_data: InvoiceCreate, current_user: dict = Depends(get_current_user)):
    # 1. Verify Job Card exists
    job_card = await JobCard.get(invoice_data.job_card_id)
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The linked Job Card does not exist"
        )
        
    next_invoice_no = await generate_next_invoice_no()
    
    new_invoice = Invoice(
        invoice_no=next_invoice_no,
        job_card_id=invoice_data.job_card_id,
        spare_parts=invoice_data.spare_parts,
        labor_charges=invoice_data.labor_charges,
        payment_status=invoice_data.payment_status,
        payment_method=invoice_data.payment_method,
        paid_amount=invoice_data.paid_amount,
        created_by=current_user["username"]
    )
    
    # Calculate totals before inserting
    new_invoice.calculate_totals()
    
    await new_invoice.insert()
    return await populate_invoice_details(new_invoice)

@router.get("", response_model=List[InvoiceOut])
async def list_invoices(
    job_card_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by Job Card ID"),
    vehicle_id: Optional[PydanticObjectId] = Query(default=None, description="Filter by Vehicle ID"),
    payment_status: Optional[PaymentStatus] = Query(default=None, description="Filter by payment status"),
    search: Optional[str] = Query(default=None, description="Search by Invoice Number (case-insensitive)"),
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if job_card_id:
        query["job_card_id"] = job_card_id
    if vehicle_id:
        job_cards = await JobCard.find(JobCard.vehicle_id == vehicle_id).to_list()
        if not job_cards:
            return []
        query["job_card_id"] = {"$in": [jc.id for jc in job_cards]}
    if payment_status:
        query["payment_status"] = payment_status
    if search:
        query["invoice_no"] = {"$regex": search.strip().upper(), "$options": "i"}
        
    invoices = await Invoice.find(query).to_list()
    return await populate_invoices_list(invoices)

@router.get("/vehicle/{vehicle_id}", response_model=List[InvoiceOut])
async def list_invoices_by_vehicle(vehicle_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.vehicle_id == vehicle_id).to_list()
    if not job_cards:
        return []
    job_card_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).to_list()
    return await populate_invoices_list(invoices)

@router.get("/customer/{customer_id}", response_model=List[InvoiceOut])
async def list_invoices_by_customer(customer_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.customer_id == customer_id).to_list()
    if not job_cards:
        return []
    job_card_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).to_list()
    return await populate_invoices_list(invoices)

@router.get("/{id}", response_model=InvoiceOut)
async def get_invoice(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    invoice = await Invoice.get(id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    return await populate_invoice_details(invoice)

@router.put("/{id}", response_model=InvoiceOut)
async def update_invoice(
    id: PydanticObjectId,
    invoice_data: InvoiceUpdate,
    current_user: dict = Depends(get_current_user)
):
    invoice = await Invoice.get(id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
        
    # Verify Job Card if updated
    if invoice_data.job_card_id and invoice_data.job_card_id != invoice.job_card_id:
        job_card = await JobCard.get(invoice_data.job_card_id)
        if not job_card:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The linked Job Card does not exist"
            )
            
    for field in invoice_data.model_fields_set:
        value = getattr(invoice_data, field)
        setattr(invoice, field, value)
        
    # Recalculate totals after updating values
    invoice.calculate_totals()
    
    invoice.updated_at = datetime.utcnow()
    await invoice.save()
    return await populate_invoice_details(invoice)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    invoice = await Invoice.get(id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
    await invoice.delete()
    return None
