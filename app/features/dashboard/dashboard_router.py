from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.features.job_card.job_card_models import JobCard
from app.features.invoice.invoice_models import Invoice
from datetime import datetime

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/stats")
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    now = datetime.utcnow()
    start_of_today = datetime(now.year, now.month, now.day, 0, 0, 0)
    end_of_today = datetime(now.year, now.month, now.day, 23, 59, 59)
    
    # 1. Today's Job Cards count & status counts
    todays_job_cards = await JobCard.find(
        JobCard.created_at >= start_of_today,
        JobCard.created_at <= end_of_today
    ).to_list()
    
    total_vehicles_today = len(todays_job_cards)
    vehicles_in_progress = sum(1 for jc in todays_job_cards if jc.status == "In Progress")
    vehicles_completed = sum(1 for jc in todays_job_cards if jc.status == "Completed")
    pending_delivery = sum(1 for jc in todays_job_cards if jc.status == "Pending Delivery")
    
    # 2. Revenue Today (sum of paid_amount of invoices created today)
    todays_invoices = await Invoice.find(
        Invoice.created_at >= start_of_today,
        Invoice.created_at <= end_of_today
    ).to_list()
    today_revenue = sum(inv.paid_amount for inv in todays_invoices)
    
    # 3. Monthly Revenue (sum of paid_amount of invoices created this calendar month)
    start_of_month = datetime(now.year, now.month, 1, 0, 0, 0)
    monthly_invoices = await Invoice.find(
        Invoice.created_at >= start_of_month
    ).to_list()
    monthly_revenue = sum(inv.paid_amount for inv in monthly_invoices)
    
    # 4. Pending Payments (sum of balance due across all invoices)
    all_invoices = await Invoice.find_all().to_list()
    pending_payments = sum(max(0.0, inv.grand_total - inv.paid_amount) for inv in all_invoices)
    
    return {
        "total_vehicles_today": total_vehicles_today,
        "vehicles_in_progress": vehicles_in_progress,
        "vehicles_completed": vehicles_completed,
        "pending_delivery": pending_delivery,
        "today_revenue": today_revenue,
        "monthly_revenue": monthly_revenue,
        "pending_payments": pending_payments
    }
