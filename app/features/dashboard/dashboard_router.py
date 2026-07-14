from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.features.job_card.job_card_models import JobCard
from app.features.invoice.invoice_models import Invoice
from app.features.expense.expense_models import Expense
from app.features.customer.customer_models import Customer
from app.features.vehicle.vehicle_models import Vehicle
from app.features.user.user_models import User
from datetime import datetime, timedelta
from typing import Optional
from app.core.datetime_utils import get_current_time

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/stats")
async def get_dashboard_stats(
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
        
    # 1. Job Cards count & status counts in selected range
    job_cards = await JobCard.find(
        JobCard.created_at >= start_dt,
        JobCard.created_at <= end_dt
    ).to_list()
    
    total_vehicles_today = len(job_cards)
    vehicles_in_progress = await JobCard.find(JobCard.status == "In Progress").count()
    vehicles_completed = sum(1 for jc in job_cards if jc.status == "Delivered")
    pending_delivery = sum(1 for jc in job_cards if jc.status == "Pending Delivery")
    
    # 2. Revenue in selected range (sum of grand_total of Paid invoices created in range)
    invoices = await Invoice.find(
        Invoice.created_at >= start_dt,
        Invoice.created_at <= end_dt
    ).to_list()
    paid_invoices = [inv for inv in invoices if inv.payment_status == "Paid"]
    today_revenue = sum(inv.grand_total for inv in paid_invoices)
    today_spare_parts_total = sum(inv.spare_parts_total for inv in paid_invoices)
    today_labor_total = sum(inv.labor_total for inv in paid_invoices)
    
    # 3. Monthly Revenue (sum of grand_total of Paid invoices created this calendar month)
    start_of_month = datetime(now.year, now.month, 1, 0, 0, 0)
    monthly_invoices = await Invoice.find(
        Invoice.created_at >= start_of_month
    ).to_list()
    paid_monthly_invoices = [inv for inv in monthly_invoices if inv.payment_status == "Paid"]
    monthly_revenue = sum(inv.grand_total for inv in paid_monthly_invoices)
    monthly_spare_parts_total = sum(inv.spare_parts_total for inv in paid_monthly_invoices)
    monthly_labor_total = sum(inv.labor_total for inv in paid_monthly_invoices)
    
    # 4. Pending Payments (sum of balance due across all invoices)
    all_invoices = await Invoice.find_all().to_list()
    pending_payments = sum(max(0.0, inv.grand_total - inv.paid_amount) for inv in all_invoices)
    
    # 5. Expenses in selected range
    expenses = await Expense.find(
        Expense.date >= start_dt,
        Expense.date <= end_dt
    ).to_list()
    today_expense = sum(exp.amount for exp in expenses)
    
    # 6. Monthly Expenses
    monthly_expenses = await Expense.find(
        Expense.date >= start_of_month
    ).to_list()
    monthly_expense = sum(exp.amount for exp in monthly_expenses)
    
    # 7. New Customers in range
    new_customers = await Customer.find(
        Customer.created_at >= start_dt,
        Customer.created_at <= end_dt
    ).count()

    # 8. Customer Repeat Rate in range
    unique_cust_ids = [jc.customer_id for jc in job_cards]
    from collections import Counter
    cust_counts = Counter(unique_cust_ids)
    total_unique_custs = len(cust_counts)
    repeat_custs = sum(1 for c, count in cust_counts.items() if count > 1)
    repeat_rate = (repeat_custs / total_unique_custs * 100) if total_unique_custs > 0 else 0.0

    # 9. Top Visited Vehicles
    veh_ids = [jc.vehicle_id for jc in job_cards]
    vehicles = await Vehicle.find({"_id": {"$in": list(set(veh_ids))}}).to_list()
    veh_map = {v.id: f"{v.brand_make} {v.model or ''}".strip() for v in vehicles}
    
    veh_counts = Counter([veh_map.get(vid, "Unknown") for vid in veh_ids])
    top_vehicles = [{"brand_model": k, "visits": v} for k, v in veh_counts.most_common(5)]

    # 10. Mechanic Productivity
    mech_ids = list({jc.mechanic_id for jc in job_cards if jc.mechanic_id})
    mechanics = await User.find({"_id": {"$in": mech_ids}}).to_list()
    mech_map = {m.id: m.full_name for m in mechanics}
    
    job_card_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).to_list()
    invoice_map = {inv.job_card_id: inv for inv in invoices}
    
    mech_stats = {}
    for jc in job_cards:
        if not jc.mechanic_id:
            continue
        mech_name = mech_map.get(jc.mechanic_id, "Unknown")
        if mech_name not in mech_stats:
            mech_stats[mech_name] = {"completed_jobs": 0, "total_jobs": 0, "labor_revenue": 0.0}
            
        mech_stats[mech_name]["total_jobs"] += 1
        if jc.status == "Delivered":
            mech_stats[mech_name]["completed_jobs"] += 1
            if jc.id in invoice_map:
                mech_stats[mech_name]["labor_revenue"] += invoice_map[jc.id].labor_total
                
    mechanic_productivity = [
        {
            "name": name,
            "completed_jobs": stats["completed_jobs"],
            "total_jobs": stats["total_jobs"],
            "labor_revenue": stats["labor_revenue"]
        }
        for name, stats in mech_stats.items()
    ]
    
    return {
        "total_vehicles_today": total_vehicles_today,
        "vehicles_in_progress": vehicles_in_progress,
        "vehicles_completed": vehicles_completed,
        "pending_delivery": pending_delivery,
        "today_revenue": today_revenue,
        "today_spare_parts_total": today_spare_parts_total,
        "today_labor_total": today_labor_total,
        "monthly_revenue": monthly_revenue,
        "monthly_spare_parts_total": monthly_spare_parts_total,
        "monthly_labor_total": monthly_labor_total,
        "pending_payments": pending_payments,
        "today_expense": today_expense,
        "monthly_expense": monthly_expense,
        "new_customers": new_customers,
        "repeat_rate": repeat_rate,
        "top_vehicles": top_vehicles,
        "mechanic_productivity": mechanic_productivity
    }

@router.get("/daily-report")
async def get_daily_report(
    start_date: Optional[datetime] = Query(default=None),
    end_date: Optional[datetime] = Query(default=None),
    current_user: dict = Depends(get_current_user)
):
    now = get_current_time()
    
    if start_date:
        start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0)
    else:
        # Default to last 30 days
        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0) - timedelta(days=30)
        
    if end_date:
        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59)
    else:
        end_dt = datetime(now.year, now.month, now.day, 23, 59, 59)
        
    # Query database records in range
    job_cards = await JobCard.find(
        JobCard.created_at >= start_dt,
        JobCard.created_at <= end_dt
    ).to_list()
    
    invoices = await Invoice.find(
        Invoice.created_at >= start_dt,
        Invoice.created_at <= end_dt
    ).to_list()
    
    expenses = await Expense.find(
        Expense.date >= start_dt,
        Expense.date <= end_dt
    ).to_list()
    
    # Aggregate counts/totals day-by-day
    jc_by_date = {}
    for jc in job_cards:
        d_str = jc.created_at.strftime("%Y-%m-%d")
        jc_by_date[d_str] = jc_by_date.get(d_str, 0) + 1
        
    inv_by_date = {}
    for inv in invoices:
        if inv.payment_status == "Paid":
            d_str = inv.created_at.strftime("%Y-%m-%d")
            inv_by_date[d_str] = inv_by_date.get(d_str, 0.0) + inv.grand_total
            
    exp_by_date = {}
    for exp in expenses:
        d_str = exp.date.strftime("%Y-%m-%d")
        exp_by_date[d_str] = exp_by_date.get(d_str, 0.0) + exp.amount
        
    # Generate calendar row data
    daily_rows = []
    curr = start_dt
    while curr <= end_dt:
        d_str = curr.strftime("%Y-%m-%d")
        
        vehicles = jc_by_date.get(d_str, 0)
        revenue = inv_by_date.get(d_str, 0.0)
        expense = exp_by_date.get(d_str, 0.0)
        profit = revenue - expense
        
        # Only add rows with activity to keep the table clean
        if vehicles > 0 or revenue > 0 or expense > 0:
            daily_rows.append({
                "date": d_str,
                "vehicles": vehicles,
                "revenue": revenue,
                "expense": expense,
                "profit": profit
            })
            
        curr += timedelta(days=1)
        
    daily_rows.sort(key=lambda x: x["date"], reverse=True)
    return daily_rows

@router.get("/pending-payment-customers")
async def get_pending_payment_customers(
    current_user: dict = Depends(get_current_user)
):
    now = get_current_time()
    threshold = now - timedelta(days=1)
    
    # Query all unpaid or partially paid invoices older than 2 days
    invoices = await Invoice.find(
        Invoice.created_at <= threshold,
        Invoice.payment_status != "Paid"
    ).to_list()
    
    # Extract unique job card IDs, customer IDs, vehicle IDs
    job_card_ids = [inv.job_card_id for inv in invoices]
    job_cards = await JobCard.find({"_id": {"$in": job_card_ids}}).to_list()
    jc_map = {jc.id: jc for jc in job_cards}
    
    cust_ids = list({jc.customer_id for jc in job_cards})
    customers = await Customer.find({"_id": {"$in": cust_ids}}).to_list()
    cust_map = {c.id: c for c in customers}
    
    veh_ids = list({jc.vehicle_id for jc in job_cards})
    vehicles = await Vehicle.find({"_id": {"$in": veh_ids}}).to_list()
    veh_map = {v.id: v for v in vehicles}
    
    # Build list of pending payment customer records
    results = []
    for inv in invoices:
        jc = jc_map.get(inv.job_card_id)
        if not jc:
            continue
            
        customer = cust_map.get(jc.customer_id)
        vehicle = veh_map.get(jc.vehicle_id)
        
        # Calculate days pending
        days_pending = (now - inv.created_at).days
        
        results.append({
            "invoice_id": str(inv.id),
            "invoice_no": inv.invoice_no,
            "grand_total": inv.grand_total,
            "paid_amount": inv.paid_amount,
            "pending_amount": inv.pending_amount,
            "payment_status": inv.payment_status,
            "created_at": inv.created_at.isoformat(),
            "days_pending": days_pending,
            "customer": {
                "id": str(customer.id) if customer else "",
                "name": customer.name if customer else "Unknown",
                "phone": f"{customer.phone_code} {customer.phone_number}" if customer else ""
            } if customer else None,
            "vehicle": {
                "registration_number": vehicle.registration_number if vehicle else "",
                "brand_model": f"{vehicle.brand_make} {vehicle.model or ''}".strip() if vehicle else ""
            } if vehicle else None
        })
        
    # Sort by days pending (longest pending first)
    results.sort(key=lambda x: x["days_pending"], reverse=True)
    return results
