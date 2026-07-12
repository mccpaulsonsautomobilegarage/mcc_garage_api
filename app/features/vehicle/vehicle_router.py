from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.vehicle.vehicle_models import Vehicle, VehicleCreate, VehicleUpdate, VehicleOut
from app.features.customer.customer_models import Customer
from app.core.security import get_current_user, get_current_admin
from datetime import datetime
from app.core.datetime_utils import get_current_time

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])

@router.post("", response_model=VehicleOut, status_code=status.HTTP_201_CREATED)
async def register_vehicle(vehicle_data: VehicleCreate, current_user: dict = Depends(get_current_user)):
    # 1. Verify that the customer exists
    customer = await Customer.get(vehicle_data.customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The linked customer account does not exist"
        )
        
    # 2. Check if a vehicle with the same registration number already exists
    existing_vehicle = await Vehicle.find_one(Vehicle.registration_number == vehicle_data.registration_number)
    if existing_vehicle:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A vehicle with this registration number is already registered"
        )
        
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
    search: Optional[str] = Query(default=None, description="Search by registration number (case-insensitive)"),
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if customer_id:
        query["customer_id"] = customer_id
    if search:
        # Standardize search query to uppercase and clean it (like we clean registration numbers)
        cleaned_search = search.strip().upper().replace(" ", "").replace("-", "")
        query["registration_number"] = {"$regex": cleaned_search, "$options": "i"}
        
    vehicles = await Vehicle.find(query).to_list()
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
    vehicle_data: VehicleUpdate,
    current_user: dict = Depends(get_current_user)
):
    vehicle = await Vehicle.get(id)
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )
        
    # 1. If customer ID is updated, verify it exists
    if vehicle_data.customer_id and vehicle_data.customer_id != vehicle.customer_id:
        customer = await Customer.get(vehicle_data.customer_id)
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The linked customer account does not exist"
            )
            
    # 2. If registration number is updated, verify uniqueness
    if vehicle_data.registration_number and vehicle_data.registration_number != vehicle.registration_number:
        existing_reg = await Vehicle.find_one(Vehicle.registration_number == vehicle_data.registration_number)
        if existing_reg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A vehicle with this registration number is already registered"
            )
            
    update_dict = vehicle_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
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
    await vehicle.delete()
    return None
