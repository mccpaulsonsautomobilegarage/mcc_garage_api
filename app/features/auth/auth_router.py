from typing import List
from beanie import PydanticObjectId
from fastapi import APIRouter, HTTPException, status, Depends
from app.features.user.user_models import User
from app.features.auth.auth_models import Token, UserRegister, UserLogin, UserOut, UserUpdate
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token, get_current_admin
from app.core.config import settings
from pymongo.errors import DuplicateKeyError

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/create-mechanic-user", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_mechanic_user(user_data: UserRegister, admin: str = Depends(get_current_admin)):
    # Check if user exists
    existing_user = await User.find_one(User.username == user_data.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    # Hash password
    hashed_password = get_password_hash(user_data.password)
    
    new_user = User(
        full_name=user_data.full_name,
        phone_code=user_data.phone_code,
        phone_number=user_data.phone_number,
        salary_monthly=user_data.salary_monthly,
        experience=user_data.experience,
        specialization=user_data.specialization,
        username=user_data.username,
        password_hash=hashed_password,
        password=user_data.password,
        role="mechanic"
    )
    
    try:
        await new_user.insert()
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    return {"message": "Mechanic user registered successfully"}

@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    # 1. Check if it's the admin
    if user_data.username == settings.ADMIN_USERNAME and user_data.password == settings.ADMIN_PASSWORD:
        access_token = create_access_token(subject=settings.ADMIN_USERNAME, role="admin")
        refresh_token = create_refresh_token(subject=settings.ADMIN_USERNAME, role="admin")
        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            role="admin"
        )
        
    # 2. Check if it's a mechanic user
    user = await User.find_one(User.username == user_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not verify_password(user_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(subject=user.username, role=user.role)
    refresh_token = create_refresh_token(subject=user.username, role=user.role)
    
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        role=user.role
    )

@router.get("/mechanics", response_model=List[UserOut])
async def list_mechanics(admin: str = Depends(get_current_admin)):
    mechanics = await User.find(User.role == "mechanic").to_list()
    return mechanics

@router.delete("/mechanics/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mechanic(id: PydanticObjectId, admin: str = Depends(get_current_admin)):
    mechanic = await User.get(id)
    if not mechanic or mechanic.role != "mechanic":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mechanic user not found"
        )
    await mechanic.delete()
    return None

@router.put("/mechanics/{id}", response_model=UserOut)
async def update_mechanic(
    id: PydanticObjectId,
    update_data: UserUpdate,
    admin: str = Depends(get_current_admin)
):
    mechanic = await User.get(id)
    if not mechanic or mechanic.role != "mechanic":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mechanic user not found"
        )
        
    if update_data.username and update_data.username != mechanic.username:
        if update_data.username == settings.ADMIN_USERNAME:
            raise HTTPException(status_code=400, detail="Username already registered")
        existing_user = await User.find_one(User.username == update_data.username)
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already registered")
            
    if update_data.password:
        mechanic.password_hash = get_password_hash(update_data.password)
        mechanic.password = update_data.password
        
    update_dict = update_data.model_dump(exclude_unset=True)
    update_dict.pop("password", None)
    
    for key, value in update_dict.items():
        setattr(mechanic, key, value)
        
    try:
        await mechanic.save()
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    return mechanic
