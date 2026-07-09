from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.customer.customer_models import Customer, CustomerCreate, CustomerUpdate, CustomerOut
from app.core.security import get_current_user
from datetime import datetime

router = APIRouter(prefix="/customers", tags=["Customers"])

@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(customer_data: CustomerCreate, current_user: dict = Depends(get_current_user)):
    # Check if a customer with the same phone number already exists
    existing_customer = await Customer.find_one(Customer.phone_number == customer_data.phone_number)
    if existing_customer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A customer with this phone number is already registered"
        )
        
    new_customer = Customer(
        name=customer_data.name,
        phone_number=customer_data.phone_number,
        whatsapp_number=customer_data.whatsapp_number,
        email=customer_data.email,
        address=customer_data.address,
        gst_number=customer_data.gst_number,
        notes=customer_data.notes,
        created_by=current_user["username"]
    )
    
    await new_customer.insert()
    return new_customer

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
        
    return customers

@router.get("/{id}", response_model=CustomerOut)
async def get_customer(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    customer = await Customer.get(id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    return customer

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
    if customer_data.phone_number and customer_data.phone_number != customer.phone_number:
        existing_phone = await Customer.find_one(Customer.phone_number == customer_data.phone_number)
        if existing_phone:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A customer with this phone number is already registered"
            )
            
    update_dict = customer_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(customer, key, value)
        
    customer.updated_at = datetime.utcnow()
    await customer.save()
    return customer

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    customer = await Customer.get(id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    await customer.delete()
    return None
