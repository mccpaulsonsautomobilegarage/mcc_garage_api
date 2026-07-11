from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from beanie import PydanticObjectId
from app.features.expense.expense_models import Expense, ExpenseCreate, ExpenseUpdate, ExpenseOut
from app.core.security import get_current_user
from datetime import datetime

router = APIRouter(prefix="/expenses", tags=["Expenses"])

@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(expense_data: ExpenseCreate, current_user: dict = Depends(get_current_user)):
    new_expense = Expense(
        description=expense_data.description,
        category=expense_data.category,
        amount=expense_data.amount,
        date=expense_data.date,
        created_by=current_user["username"]
    )
    await new_expense.insert()
    return new_expense

@router.get("", response_model=List[ExpenseOut])
async def list_expenses(
    category: Optional[str] = Query(default=None, description="Filter by category"),
    search: Optional[str] = Query(default=None, description="Search by description"),
    start_date: Optional[datetime] = Query(default=None, description="Start date filter"),
    end_date: Optional[datetime] = Query(default=None, description="End date filter"),
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if category:
        query["category"] = category
    if search:
        query["description"] = {"$regex": search, "$options": "i"}

    if start_date or end_date:
        date_query = {}
        if start_date:
            date_query["$gte"] = start_date
        if end_date:
            date_query["$lte"] = end_date
        query["date"] = date_query

    expenses = await Expense.find(query).sort("-date").to_list()
    return expenses

@router.get("/{id}", response_model=ExpenseOut)
async def get_expense(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    expense = await Expense.get(id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )
    return expense

@router.put("/{id}", response_model=ExpenseOut)
async def update_expense(
    id: PydanticObjectId,
    expense_data: ExpenseUpdate,
    current_user: dict = Depends(get_current_user)
):
    expense = await Expense.get(id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )

    update_dict = expense_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(expense, key, value)

    expense.updated_at = datetime.utcnow()
    await expense.save()
    return expense

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(id: PydanticObjectId, current_user: dict = Depends(get_current_user)):
    expense = await Expense.get(id)
    if not expense:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Expense not found"
        )
    await expense.delete()
    return None
