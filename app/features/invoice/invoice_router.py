from fastapi import APIRouter, Depends, HTTPException, status, Query, Form, File, UploadFile, Request
from typing import List, Optional
import json
from beanie import PydanticObjectId
from app.features.invoice.invoice_models import Invoice, InvoiceCreate, InvoiceUpdate, InvoiceOut, PaymentStatus
from app.features.job_card.job_card_models import JobCard
from app.core.security import get_current_user
from datetime import datetime, time
from app.core.datetime_utils import get_current_time
from app.features.customer.customer_models import Customer
from app.features.vehicle.vehicle_models import Vehicle
from app.features.expense.expense_models import Expense
from app.core.s3 import S3Service

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
        model=vehicle.model if (vehicle and vehicle.model) else "",
        odometer=vehicle.odometer_reading if vehicle else None
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
                model=veh.model if (veh and veh.model) else "",
                odometer=veh.odometer_reading if veh else None
            )
        )
    return results

async def generate_next_invoice_no() -> str:
    now = get_current_time()
    day_start = datetime.combine(now.date(), time.min)
    day_end = datetime.combine(now.date(), time.max)
    
    count = await Invoice.find(Invoice.created_at >= day_start, Invoice.created_at <= day_end).count()
    
    while True:
        next_val = count + 1
        invoice_no = f"{next_val:02d}{now.day:02d}{now.month:02d}{now.year % 100:02d}"
        existing = await Invoice.find_one(Invoice.invoice_no == invoice_no)
        if not existing:
            return invoice_no
        count += 1

@router.post("", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    job_card_id: str = Form(...),
    spare_parts: Optional[str] = Form(None),
    labor_charges: Optional[str] = Form(None),
    payment_status: str = Form("Pending"),
    payment_method: str = Form("Cash"),
    paid_amount: str = Form("0.0"),
    bills: List[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user)
):
    # 1. Clean and parse job_card_id
    try:
        cleaned_job_card_id = PydanticObjectId(job_card_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Job Card ID format"
        )
        
    # 2. Parse spare_parts JSON string
    parsed_spare_parts = []
    if spare_parts and spare_parts.strip():
        try:
            parsed_spare_parts = json.loads(spare_parts)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON format for spare_parts"
            )
            
    # 3. Parse labor_charges JSON string
    parsed_labor_charges = []
    if labor_charges and labor_charges.strip():
        try:
            parsed_labor_charges = json.loads(labor_charges)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON format for labor_charges"
            )
            
    # 4. Clean paid_amount
    try:
        cleaned_paid_amount = float(paid_amount) if paid_amount.strip() != "" else 0.0
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid paid_amount value"
        )

    # Validate utilizing InvoiceCreate
    try:
        invoice_data = InvoiceCreate(
            job_card_id=cleaned_job_card_id,
            spare_parts=parsed_spare_parts,
            labor_charges=parsed_labor_charges,
            payment_status=payment_status,
            payment_method=payment_method,
            paid_amount=cleaned_paid_amount
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    # 5. Verify Job Card exists
    job_card = await JobCard.get(invoice_data.job_card_id)
    if not job_card:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The linked Job Card does not exist"
        )
        
    # 6. Prevent duplicate invoice creation for the same Job Card
    existing_invoice = await Invoice.find_one(Invoice.job_card_id == invoice_data.job_card_id)
    if existing_invoice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An invoice has already been generated for this Job Card (Invoice No: {existing_invoice.invoice_no})"
        )

    # 7. Handle S3 bills upload if files are provided
    bill_urls = []
    if bills:
        s3_service = S3Service()
        for bill in bills:
            if bill.filename:
                url = await s3_service.upload_file(bill, folder="invoices")
                bill_urls.append(url)
        
    next_invoice_no = await generate_next_invoice_no()
    
    new_invoice = Invoice(
        invoice_no=next_invoice_no,
        job_card_id=invoice_data.job_card_id,
        spare_parts=invoice_data.spare_parts,
        labor_charges=invoice_data.labor_charges,
        payment_status=invoice_data.payment_status,
        payment_method=invoice_data.payment_method,
        paid_amount=invoice_data.paid_amount,
        bill_urls=bill_urls,
        created_by=current_user["username"]
    )
    
    # Calculate totals before inserting
    new_invoice.calculate_totals()
    
    await new_invoice.insert()
    
    # Automatically add to expense table if spare parts total > 0
    if new_invoice.spare_parts_total > 0:
        new_expense = Expense(
            category="Tools Purchase",
            amount=new_invoice.spare_parts_total,
            date=new_invoice.created_at,
            description=f"Spare parts for Invoice: {new_invoice.invoice_no}",
            job_card_id=new_invoice.job_card_id,
            created_by=current_user["username"]
        )
        await new_expense.insert()
        
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
        
    invoices = await Invoice.find(query).sort("-created_at").to_list()
    return await populate_invoices_list(invoices)

@router.get("/vehicle/{vehicle_id}", response_model=List[InvoiceOut])
async def list_invoices_by_vehicle(vehicle_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.vehicle_id == vehicle_id).to_list()
    if not job_cards:
        return []
    job_card_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).sort("-created_at").to_list()
    return await populate_invoices_list(invoices)

@router.get("/customer/{customer_id}", response_model=List[InvoiceOut])
async def list_invoices_by_customer(customer_id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    job_cards = await JobCard.find(JobCard.customer_id == customer_id).to_list()
    if not job_cards:
        return []
    job_card_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).sort("-created_at").to_list()
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
    request: Request,
    job_card_id: Optional[str] = Form(None),
    spare_parts: Optional[str] = Form(None),
    labor_charges: Optional[str] = Form(None),
    payment_status: Optional[str] = Form(None),
    payment_method: Optional[str] = Form(None),
    paid_amount: Optional[str] = Form(None),
    existing_bill_urls: Optional[str] = Form(None),
    bills: List[UploadFile] = File(default=[]),
    current_user: dict = Depends(get_current_user)
):
    invoice = await Invoice.get(id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    form_data = await request.form()
    update_dict = {}
    
    # 1. Parse fields actually present in form
    if "job_card_id" in form_data:
        if job_card_id and job_card_id.strip():
            try:
                update_dict["job_card_id"] = PydanticObjectId(job_card_id)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid Job Card ID format"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Job Card ID cannot be empty"
            )

    if "spare_parts" in form_data:
        if spare_parts and spare_parts.strip():
            try:
                update_dict["spare_parts"] = json.loads(spare_parts)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format for spare_parts"
                )
        else:
            update_dict["spare_parts"] = []

    if "labor_charges" in form_data:
        if labor_charges and labor_charges.strip():
            try:
                update_dict["labor_charges"] = json.loads(labor_charges)
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON format for labor_charges"
                )
        else:
            update_dict["labor_charges"] = []

    if "payment_status" in form_data:
        update_dict["payment_status"] = payment_status

    if "payment_method" in form_data:
        update_dict["payment_method"] = payment_method

    if "paid_amount" in form_data:
        if paid_amount and paid_amount.strip():
            try:
                update_dict["paid_amount"] = float(paid_amount)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid paid_amount value"
                )
        else:
            update_dict["paid_amount"] = 0.0

    # Validate utilizing InvoiceUpdate
    try:
        validated_data = InvoiceUpdate(**update_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    # Extract parsed updates
    validated_dict = validated_data.model_dump(exclude_unset=True)

    # Verify Job Card exists if updated
    if "job_card_id" in validated_dict and validated_dict["job_card_id"] != invoice.job_card_id:
        job_card = await JobCard.get(validated_dict["job_card_id"])
        if not job_card:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The linked Job Card does not exist"
            )

    old_job_card_id = invoice.job_card_id

    # Apply standard text/data field updates
    for key in validated_dict.keys():
        setattr(invoice, key, getattr(validated_data, key))

    # 2. Handle S3 bill file uploads and deletes
    s3_service = S3Service()
    if "existing_bill_urls" in form_data:
        keep_urls = []
        if existing_bill_urls and existing_bill_urls.strip():
            try:
                keep_urls = json.loads(existing_bill_urls)
            except Exception:
                # fallback if it's sent as a comma separated string
                keep_urls = [x.strip() for x in existing_bill_urls.split(",") if x.strip()]
        
        # Identify deleted bills and delete them from S3
        deleted_urls = [url for url in (invoice.bill_urls or []) if url not in keep_urls]
        for deleted_url in deleted_urls:
            await s3_service.delete_file_by_url(deleted_url)
            
        invoice.bill_urls = keep_urls

    # Upload new bills if provided
    if bills:
        new_urls = []
        for bill in bills:
            if bill.filename:
                url = await s3_service.upload_file(bill, folder="invoices")
                new_urls.append(url)
        invoice.bill_urls = (invoice.bill_urls or []) + new_urls

    # Recalculate totals
    invoice.calculate_totals()
    invoice.updated_at = get_current_time()
    await invoice.save()
    
    # Handle corresponding expense record update/creation/deletion
    existing_expense = await Expense.find_one(Expense.job_card_id == old_job_card_id)
    if existing_expense:
        if invoice.spare_parts_total > 0:
            existing_expense.amount = invoice.spare_parts_total
            existing_expense.description = f"Spare parts for Invoice: {invoice.invoice_no}"
            existing_expense.job_card_id = invoice.job_card_id
            existing_expense.updated_at = get_current_time()
            await existing_expense.save()
        else:
            await existing_expense.delete()
    else:
        if invoice.spare_parts_total > 0:
            new_expense = Expense(
                category="Tools Purchase",
                amount=invoice.spare_parts_total,
                date=invoice.created_at,
                description=f"Spare parts for Invoice: {invoice.invoice_no}",
                job_card_id=invoice.job_card_id,
                created_by=current_user["username"]
            )
            await new_expense.insert()
            
    return await populate_invoice_details(invoice)

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invoice(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    invoice = await Invoice.get(id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )
        
    # Delete corresponding expense record
    existing_expense = await Expense.find_one(Expense.job_card_id == invoice.job_card_id)
    if existing_expense:
        await existing_expense.delete()

    # Delete all bills from S3
    if invoice.bill_urls:
        s3_service = S3Service()
        for url in invoice.bill_urls:
            await s3_service.delete_file_by_url(url)
        
    await invoice.delete()
    return None
