from fastapi import APIRouter, Depends, HTTPException, status, Query, Form, File, UploadFile, Request
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.vehicle.vehicle_models import Vehicle, VehicleCreate, VehicleUpdate, VehicleOut
from app.features.customer.customer_models import Customer
from app.core.security import get_current_user, get_current_admin
from datetime import datetime
from app.core.datetime_utils import get_current_time
from app.core.s3 import S3Service

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def register_vehicle(
    customer_id: str = Form(...),
    registration_number: str = Form(...),
    brand_make: str = Form(...),
    model: Optional[str] = Form(None),
    variant: Optional[str] = Form(None),
    mfg_year: Optional[str] = Form(None),
    fuel_type: str = Form(...),
    color: Optional[str] = Form(None),
    odometer_reading: Optional[str] = Form(None),
    chassis_number: Optional[str] = Form(None),
    engine_number: Optional[str] = Form(None),
    insurance_expiry_date: Optional[str] = Form(None),
    rc_details: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    # 1. Clean strings, converting empty strings to None where applicable
    def clean_str(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.strip()
        return None if val == "" else val

    try:
        cleaned_customer_id = PydanticObjectId(customer_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid customer ID format"
        )
    
    mfg_year_cleaned = clean_str(mfg_year)
    parsed_mfg_year = int(mfg_year_cleaned) if mfg_year_cleaned is not None else None

    odometer_cleaned = clean_str(odometer_reading)
    parsed_odometer = float(odometer_cleaned) if odometer_cleaned is not None else None

    expiry_cleaned = clean_str(insurance_expiry_date)
    parsed_expiry = None
    if expiry_cleaned is not None:
        try:
            parsed_expiry = datetime.fromisoformat(expiry_cleaned.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid insurance expiry date format. Use ISO format."
            )

    # 2. Use VehicleCreate to trigger Pydantic validation (including field_validators)
    try:
        vehicle_data = VehicleCreate(
            customer_id=cleaned_customer_id,
            registration_number=registration_number,
            brand_make=brand_make,
            model=clean_str(model),
            variant=clean_str(variant),
            mfg_year=parsed_mfg_year,
            fuel_type=fuel_type,
            color=clean_str(color),
            odometer_reading=parsed_odometer,
            chassis_number=clean_str(chassis_number),
            engine_number=clean_str(engine_number),
            insurance_expiry_date=parsed_expiry,
            rc_details=clean_str(rc_details)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    # 3. Verify that the customer exists
    customer = await Customer.get(vehicle_data.customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The linked customer account does not exist"
        )
        
    # 4. Check if a vehicle with the same registration number already exists
    existing_vehicle = await Vehicle.find_one(Vehicle.registration_number == vehicle_data.registration_number)
    if existing_vehicle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A vehicle with this registration number is already registered"
        )

    # 5. Handle S3 upload if file is provided
    photo_url = None
    if photo and photo.filename:
        s3_service = S3Service()
        photo_url = await s3_service.upload_file(photo)

    new_vehicle = Vehicle(
        customer_id=vehicle_data.customer_id,
        registration_number=vehicle_data.registration_number,
        brand_make=vehicle_data.brand_make,
        model=vehicle_data.model,
        variant=vehicle_data.variant,
        mfg_year=vehicle_data.mfg_year,
        fuel_type=vehicle_data.fuel_type,
        color=vehicle_data.color,
        odometer_reading=vehicle_data.odometer_reading,
        chassis_number=vehicle_data.chassis_number,
        engine_number=vehicle_data.engine_number,
        insurance_expiry_date=vehicle_data.insurance_expiry_date,
        rc_details=vehicle_data.rc_details,
        photo_url=photo_url,
        created_by=current_user["username"]
    )
    
    await new_vehicle.insert()
    return VehicleOut(
        **new_vehicle.model_dump(),
        customer_name=customer.name
    )

@router.get("", response_model=List[VehicleOut])
async def list_vehicles(
    customer_id: Optional[PydanticObjectId] = Query(default=None, description="Filter vehicles by customer ID"),
    search: Optional[str] = Query(default=None, description="Search by registration number, brand, model, or owner name"),
    fuel_type: Optional[str] = Query(default=None, description="Filter vehicles by fuel type"),
    start_date: Optional[datetime] = Query(default=None, description="Start date for filtering"),
    end_date: Optional[datetime] = Query(default=None, description="End date for filtering"),
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if customer_id:
        query["customer_id"] = customer_id
    if fuel_type:
        query["fuel_type"] = {"$regex": f"^{fuel_type.strip()}$", "$options": "i"}
    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
        query["created_at"] = date_query
    if search:
        search_str = search.strip()
        cleaned_search = search_str.upper().replace(" ", "").replace("-", "")
        
        # Find matching customer IDs
        matching_customers = await Customer.find({"name": {"$regex": search_str, "$options": "i"}}).to_list()
        cust_ids = [c.id for c in matching_customers]
        
        # Construct $or conditions
        conditions = [
            {"registration_number": {"$regex": cleaned_search, "$options": "i"}},
            {"brand_make": {"$regex": search_str, "$options": "i"}},
            {"model": {"$regex": search_str, "$options": "i"}},
        ]
        if cust_ids:
            conditions.append({"customer_id": {"$in": cust_ids}})
            
        query["$or"] = conditions
        
    vehicles = await Vehicle.find(query).sort("-created_at").to_list()
    if not vehicles:
        return []
        
    customer_ids = list({v.customer_id for v in vehicles})
    customers = await Customer.find({"_id": {"$in": customer_ids}}).to_list()
    customer_map = {c.id: c.name for c in customers}
    
    return [
        VehicleOut(
            **v.model_dump(),
            customer_name=customer_map.get(v.customer_id, "Unknown Customer")
        )
        for v in vehicles
    ]

@router.get("/{id}", response_model=VehicleOut)
async def get_vehicle(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    vehicle = await Vehicle.get(id)
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
    customer = await Customer.get(vehicle.customer_id)
    customer_name = customer.name if customer else "Unknown Customer"
    return VehicleOut(
        **vehicle.model_dump(),
        customer_name=customer_name
    )

@router.put("/{id}", response_model=VehicleOut)
async def update_vehicle(
    id: PydanticObjectId,
    request: Request,
    customer_id: Optional[str] = Form(None),
    registration_number: Optional[str] = Form(None),
    brand_make: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    variant: Optional[str] = Form(None),
    mfg_year: Optional[str] = Form(None),
    fuel_type: Optional[str] = Form(None),
    color: Optional[str] = Form(None),
    odometer_reading: Optional[str] = Form(None),
    chassis_number: Optional[str] = Form(None),
    engine_number: Optional[str] = Form(None),
    insurance_expiry_date: Optional[str] = Form(None),
    rc_details: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    vehicle = await Vehicle.get(id)
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )

    # Get all keys actually sent in the form
    form_data = await request.form()
    update_dict = {}
    
    def clean_str(v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        val = v.strip()
        return None if val == "" else val

    if "customer_id" in form_data:
        try:
            update_dict["customer_id"] = PydanticObjectId(customer_id) if clean_str(customer_id) is not None else None
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid customer ID format"
            )
    if "registration_number" in form_data:
        update_dict["registration_number"] = clean_str(registration_number)
    if "brand_make" in form_data:
        update_dict["brand_make"] = clean_str(brand_make)
    if "model" in form_data:
        update_dict["model"] = clean_str(model)
    if "variant" in form_data:
        update_dict["variant"] = clean_str(variant)
    if "mfg_year" in form_data:
        val = clean_str(mfg_year)
        update_dict["mfg_year"] = int(val) if val is not None else None
    if "fuel_type" in form_data:
        update_dict["fuel_type"] = clean_str(fuel_type)
    if "color" in form_data:
        update_dict["color"] = clean_str(color)
    if "odometer_reading" in form_data:
        val = clean_str(odometer_reading)
        update_dict["odometer_reading"] = float(val) if val is not None else None
    if "chassis_number" in form_data:
        update_dict["chassis_number"] = clean_str(chassis_number)
    if "engine_number" in form_data:
        update_dict["engine_number"] = clean_str(engine_number)
    if "insurance_expiry_date" in form_data:
        val = clean_str(insurance_expiry_date)
        if val is not None:
            try:
                update_dict["insurance_expiry_date"] = datetime.fromisoformat(val.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Invalid insurance expiry date format. Use ISO format."
                )
        else:
            update_dict["insurance_expiry_date"] = None
    if "rc_details" in form_data:
        update_dict["rc_details"] = clean_str(rc_details)

    # 1. Use VehicleUpdate to trigger Pydantic validation (including field_validators)
    try:
        validated_data = VehicleUpdate(**update_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )

    # 2. Extract validated fields that were set in the form
    validated_dict = validated_data.model_dump(exclude_unset=True)

    # 3. If customer ID is updated, verify it exists
    if "customer_id" in validated_dict and validated_dict["customer_id"] != vehicle.customer_id:
        if validated_dict["customer_id"] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer ID is required"
            )
        customer = await Customer.get(validated_dict["customer_id"])
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The linked customer account does not exist"
            )
            
    # 4. If registration number is updated, verify uniqueness
    if "registration_number" in validated_dict and validated_dict["registration_number"] != vehicle.registration_number:
        if not validated_dict["registration_number"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration number cannot be empty"
            )
        existing_reg = await Vehicle.find_one(Vehicle.registration_number == validated_dict["registration_number"])
        if existing_reg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A vehicle with this registration number is already registered"
            )

    # 5. Handle S3 file upload if photo is provided
    if photo and photo.filename:
        s3_service = S3Service()
        if vehicle.photo_url:
            # Delete old file
            await s3_service.delete_file_by_url(vehicle.photo_url)
        # Upload new file
        photo_url = await s3_service.upload_file(photo)
        validated_dict["photo_url"] = photo_url
            
    # 6. Apply updates
    for key, value in validated_dict.items():
        setattr(vehicle, key, value)
        
    vehicle.updated_at = get_current_time()
    await vehicle.save()
    customer = await Customer.get(vehicle.customer_id)
    customer_name = customer.name if customer else "Unknown Customer"
    return VehicleOut(
        **vehicle.model_dump(),
        customer_name=customer_name
    )

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(id: PydanticObjectId, admin: str = Depends(get_current_admin)):
    vehicle = await Vehicle.get(id)
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
    if vehicle.photo_url:
        s3_service = S3Service()
        await s3_service.delete_file_by_url(vehicle.photo_url)
    await vehicle.delete()
    return None
