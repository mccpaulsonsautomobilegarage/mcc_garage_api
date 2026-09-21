from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.features.job_card.job_card_models import JobCard, JOB_TYPE_MAP, NEXT_SERVICE_TYPES
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
    
    # 2. Revenue in selected range (sum of revenue from Paid & Partial invoices created in range)
    invoices = await Invoice.find(
        Invoice.created_at >= start_dt,
        Invoice.created_at <= end_dt,
        {"is_draft": {"$ne": True}}
    ).to_list()
    
    today_revenue = 0.0
    today_spare_parts_total = 0.0
    today_labor_total = 0.0
    for inv in invoices:
        if inv.payment_status == "Paid":
            today_revenue += inv.grand_total or 0.0
            today_spare_parts_total += inv.spare_parts_total or 0.0
            today_labor_total += inv.labor_total or 0.0
        elif inv.payment_status == "Partial":
            today_revenue += inv.paid_amount or 0.0
            today_spare_parts_total += inv.spare_parts_total or 0.0
            today_labor_total += inv.labor_total or 0.0
    
    # Determine target month for monthly stats
    target_year = start_dt.year
    target_month = start_dt.month
    start_of_month = datetime(target_year, target_month, 1, 0, 0, 0)
    if target_month == 12:
        next_month_start = datetime(target_year + 1, 1, 1, 0, 0, 0)
    else:
        next_month_start = datetime(target_year, target_month + 1, 1, 0, 0, 0)
    end_of_month = next_month_start - timedelta(seconds=1)

    # 3. Monthly Revenue (sum of revenue from Paid & Partial invoices created in target calendar month)
    monthly_invoices = await Invoice.find(
        Invoice.created_at >= start_of_month,
        Invoice.created_at <= end_of_month,
        {"is_draft": {"$ne": True}}
    ).to_list()
    
    monthly_revenue = 0.0
    monthly_spare_parts_total = 0.0
    monthly_labor_total = 0.0
    for inv in monthly_invoices:
        if inv.payment_status == "Paid":
            monthly_revenue += inv.grand_total or 0.0
            monthly_spare_parts_total += inv.spare_parts_total or 0.0
            monthly_labor_total += inv.labor_total or 0.0
        elif inv.payment_status == "Partial":
            monthly_revenue += inv.paid_amount or 0.0
            monthly_spare_parts_total += inv.spare_parts_total or 0.0
            monthly_labor_total += inv.labor_total or 0.0
    
    # 4. Pending Payments (sum of balance due across Pending and Partial status non-draft invoices)
    all_invoices = await Invoice.find({"is_draft": {"$ne": True}}).to_list()
    pending_payments = 0.0
    for inv in all_invoices:
        if inv.payment_status == "Pending":
            pending_payments += inv.grand_total
        elif inv.payment_status == "Partial":
            pending_payments += max(0.0, inv.grand_total - inv.paid_amount)
    
    # 5. Expenses in selected range
    expenses = await Expense.find(
        Expense.date >= start_dt,
        Expense.date <= end_dt
    ).to_list()
    today_expense = sum(exp.amount for exp in expenses)
    
    # 6. Monthly Expenses in target calendar month
    monthly_expenses = await Expense.find(
        Expense.date >= start_of_month,
        Expense.date <= end_of_month
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
    all_mech_ids = set()
    for jc in job_cards:
        ids = getattr(jc, "mechanic_ids", None) or []
        if not ids and getattr(jc, "mechanic_id", None):
            ids = [jc.mechanic_id]
        all_mech_ids.update(ids)

    mechanics = await User.find({"_id": {"$in": list(all_mech_ids)}}).to_list()
    mech_map = {m.id: m.full_name for m in mechanics}
    
    job_card_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find({"job_card_id": {"$in": job_card_ids}}).to_list()
    invoice_map = {inv.job_card_id: inv for inv in invoices}
    
    mech_stats = {}
    for jc in job_cards:
        m_ids = getattr(jc, "mechanic_ids", None) or []
        if not m_ids and getattr(jc, "mechanic_id", None):
            m_ids = [jc.mechanic_id]
            
        if not m_ids:
            continue
            
        num_mechs = len(m_ids)
        inv = invoice_map.get(jc.id)
        labor_val = (getattr(inv, "labor_total", 0.0) or 0.0) if inv else 0.0
        labor_split = (labor_val / num_mechs) if num_mechs > 0 else 0.0
        
        for mid in m_ids:
            mech_name = mech_map.get(mid, "Unknown")
            if mech_name not in mech_stats:
                mech_stats[mech_name] = {
                    "completed_jobs": 0,
                    "total_jobs": 0,
                    "active_jobs": 0,
                    "labor_revenue": 0.0
                }
                
            mech_stats[mech_name]["total_jobs"] += 1
            if jc.status == "Delivered":
                mech_stats[mech_name]["completed_jobs"] += 1
                mech_stats[mech_name]["labor_revenue"] += labor_split
            else:
                mech_stats[mech_name]["active_jobs"] += 1
                
    mechanic_productivity = [
        {
            "name": name,
            "completed_jobs": stats["completed_jobs"],
            "total_jobs": stats["total_jobs"],
            "active_jobs": stats["active_jobs"],
            "labor_revenue": round(stats["labor_revenue"], 2)
        }
        for name, stats in sorted(mech_stats.items(), key=lambda x: x[1]["completed_jobs"], reverse=True)
    ]
    
    # 10. Today's Invoices Summary (for current calendar day)
    today_start_dt = datetime(now.year, now.month, now.day, 0, 0, 0)
    today_end_dt = datetime(now.year, now.month, now.day, 23, 59, 59)
    
    today_invoices_list = await Invoice.find(
        Invoice.created_at >= today_start_dt,
        Invoice.created_at <= today_end_dt,
        {"is_draft": {"$ne": True}}
    ).to_list()
    
    today_invoices_count = len(today_invoices_list)
    today_paid_revenue_val = 0.0
    today_total_billed_val = 0.0
    today_labor_cost_val = 0.0
    
    for inv in today_invoices_list:
        today_total_billed_val += inv.grand_total or 0.0
        today_labor_cost_val += inv.labor_total or 0.0
        
        if inv.payment_status == "Paid":
            today_paid_revenue_val += inv.grand_total or 0.0
        elif inv.payment_status == "Partial":
            today_paid_revenue_val += inv.paid_amount or 0.0
    
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
        "mechanic_productivity": mechanic_productivity,
        "today_summary": {
            "vehicles": today_invoices_count,
            "paid_revenue": today_paid_revenue_val,
            "total_billed": today_total_billed_val,
            "labor_cost": today_labor_cost_val
        }
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
    invoices = await Invoice.find(
        Invoice.created_at >= start_dt,
        Invoice.created_at <= end_dt,
        {"is_draft": {"$ne": True}}
    ).to_list()
    
    expenses = await Expense.find(
        Expense.date >= start_dt,
        Expense.date <= end_dt
    ).to_list()
    
    # Aggregate counts/totals day-by-day based on generated invoices
    inv_by_date = {}
    paid_inv_by_date = {}
    labor_by_date = {}
    veh_count_by_date = {}
    for inv in invoices:
        d_str = inv.created_at.strftime("%Y-%m-%d")
        inv_by_date[d_str] = inv_by_date.get(d_str, 0.0) + (inv.grand_total or 0.0)
        
        # Calculate paid revenue incorporating both Paid and Partial status invoices
        if inv.payment_status == "Paid":
            paid_val = inv.grand_total or 0.0
        elif inv.payment_status == "Partial":
            paid_val = inv.paid_amount or 0.0
        else:
            paid_val = 0.0
            
        paid_inv_by_date[d_str] = paid_inv_by_date.get(d_str, 0.0) + paid_val
        labor_by_date[d_str] = labor_by_date.get(d_str, 0.0) + (inv.labor_total or 0.0)
        veh_count_by_date[d_str] = veh_count_by_date.get(d_str, 0) + 1
            
    exp_by_date = {}
    for exp in expenses:
        d_str = exp.date.strftime("%Y-%m-%d")
        exp_by_date[d_str] = exp_by_date.get(d_str, 0.0) + exp.amount
        
    # Generate calendar row data
    daily_rows = []
    curr = start_dt
    while curr <= end_dt:
        d_str = curr.strftime("%Y-%m-%d")
        
        vehicles = veh_count_by_date.get(d_str, 0)
        total_billed = inv_by_date.get(d_str, 0.0)
        paid_amount = paid_inv_by_date.get(d_str, 0.0)
        labor_cost = labor_by_date.get(d_str, 0.0)
        expense = exp_by_date.get(d_str, 0.0)
        
        # Only add rows with activity to keep the table clean
        if vehicles > 0 or total_billed > 0 or expense > 0:
            daily_rows.append({
                "date": d_str,
                "vehicles": vehicles,
                "revenue": paid_amount,        # Revenue is the paid amount
                "paid_amount": paid_amount,
                "total_billed": total_billed,  # Total invoiced amount without paid restriction
                "labor_cost": labor_cost,
                "expense": expense,
                "paid_profit": paid_amount - expense,
                "billed_profit": total_billed - expense,
                "profit": paid_amount - expense
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

@router.get("/due-services")
async def get_due_services(
    current_user: dict = Depends(get_current_user)
):
    now = get_current_time()
    end_of_today = datetime(now.year, now.month, now.day, 23, 59, 59)
    
    # 1. Query vehicles where next_service_date <= end_of_today
    vehicles = await Vehicle.find(
        Vehicle.next_service_date != None,
        Vehicle.next_service_date <= end_of_today
    ).to_list()
    
    # 2. Also check if any job cards have next_service_date <= end_of_today for vehicles not yet covered
    veh_ids = {v.id for v in vehicles}
    extra_filter = {"next_service_date": {"$ne": None, "$lte": end_of_today}}
    if veh_ids:
        extra_filter["vehicle_id"] = {"$nin": list(veh_ids)}
    extra_job_cards = await JobCard.find(extra_filter).to_list()
    
    if extra_job_cards:
        extra_veh_ids = list({jc.vehicle_id for jc in extra_job_cards if jc.vehicle_id not in veh_ids})
        if extra_veh_ids:
            extra_vehicles = await Vehicle.find({"_id": {"$in": extra_veh_ids}}).to_list()
            for ev in extra_vehicles:
                if ev.next_service_date and ev.next_service_date > end_of_today:
                    continue
                matching_jc = next((jc for jc in extra_job_cards if jc.vehicle_id == ev.id), None)
                if matching_jc:
                    ev.next_service_date = matching_jc.next_service_date
                    ev.next_service_type = matching_jc.next_service_type
                vehicles.append(ev)
                veh_ids.add(ev.id)

    if not vehicles:
        return []

    # 3. Exclude vehicles currently having an active job card in progress
    all_veh_ids = [v.id for v in vehicles]
    active_jobs = await JobCard.find(
        {"vehicle_id": {"$in": all_veh_ids}, "status": {"$in": ["In Progress", "Pending Delivery"]}}
    ).to_list()
    active_veh_ids = {jc.vehicle_id for jc in active_jobs}

    due_vehicles = [v for v in vehicles if v.id not in active_veh_ids]
    if not due_vehicles:
        return []

    # 4. Fetch customers
    cust_ids = list({v.customer_id for v in due_vehicles if v.customer_id})
    customers = await Customer.find({"_id": {"$in": cust_ids}}).to_list()
    cust_map = {c.id: c for c in customers}

    # 5. Service work mapping
    service_work_map = {item["service_type"]: item["typical_work"] for item in NEXT_SERVICE_TYPES}

    results = []
    for veh in due_vehicles:
        customer = cust_map.get(veh.customer_id)
        service_date = veh.next_service_date
        
        delta_days = (now.date() - service_date.date()).days
        days_overdue = max(0, delta_days)
        is_due_today = (service_date.date() == now.date())

        stype = veh.next_service_type or "General / Basic Service"
        typical_work = service_work_map.get(stype, "")

        results.append({
            "vehicle_id": str(veh.id),
            "registration_number": veh.registration_number or "",
            "brand_model": f"{veh.brand_make or ''} {veh.model or ''}".strip(),
            "next_service_date": service_date.isoformat(),
            "next_service_type": stype,
            "typical_work": typical_work,
            "days_overdue": days_overdue,
            "is_due_today": is_due_today,
            "customer": {
                "id": str(customer.id) if customer else "",
                "name": customer.name if customer else "Unknown Customer",
                "phone": f"{customer.phone_code or ''} {customer.phone_number or ''}".strip() if customer else "",
                "phone_code": customer.phone_code or "+91",
                "phone_number": customer.phone_number or "",
            } if customer else None,
        })

    results.sort(key=lambda x: (x["days_overdue"], x["next_service_date"]), reverse=True)
    return results


@router.get("/job-type-report")
async def get_job_type_report(
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
        
    # Query job cards in date range
    job_cards = await JobCard.find(
        JobCard.created_at >= start_dt,
        JobCard.created_at <= end_dt
    ).to_list()
    
    total_jobs = len(job_cards)
    
    # Query non-draft invoices linked to these job cards
    jc_ids = [jc.id for jc in job_cards]
    invoices = await Invoice.find(
        {"job_card_id": {"$in": jc_ids}},
        {"is_draft": {"$ne": True}}
    ).to_list() if jc_ids else []
    
    # Group invoices by job_card_id
    inv_map = {inv.job_card_id: inv for inv in invoices}
    
    # Pre-populate all 9 job types from JOB_TYPE_MAP
    stats_by_type = {}
    for code, name in JOB_TYPE_MAP.items():
        stats_by_type[code] = {
            "code": code,
            "name": name,
            "total_jobs": 0,
            "in_progress": 0,
            "pending_delivery": 0,
            "delivered": 0,
            "total_billed": 0.0,
            "paid_revenue": 0.0,
            "percentage": 0.0,
        }
        
    total_billed_all = 0.0
    total_paid_all = 0.0
    
    for jc in job_cards:
        jtype = getattr(jc, "job_type", None) or "GS"
        if jtype not in stats_by_type:
            stats_by_type[jtype] = {
                "code": jtype,
                "name": JOB_TYPE_MAP.get(jtype, jtype),
                "total_jobs": 0,
                "in_progress": 0,
                "pending_delivery": 0,
                "delivered": 0,
                "total_billed": 0.0,
                "paid_revenue": 0.0,
                "percentage": 0.0,
            }
            
        stats = stats_by_type[jtype]
        stats["total_jobs"] += 1
        
        if jc.status == "In Progress":
            stats["in_progress"] += 1
        elif jc.status == "Pending Delivery":
            stats["pending_delivery"] += 1
        elif jc.status == "Delivered":
            stats["delivered"] += 1
            
        inv = inv_map.get(jc.id)
        if inv:
            billed = inv.grand_total or 0.0
            paid = (inv.grand_total or 0.0) if inv.payment_status == "Paid" else ((inv.paid_amount or 0.0) if inv.payment_status == "Partial" else 0.0)
            stats["total_billed"] += billed
            stats["paid_revenue"] += paid
            total_billed_all += billed
            total_paid_all += paid

    # Compute percentage
    breakdown_list = []
    for code in JOB_TYPE_MAP.keys():
        stats = stats_by_type.get(code)
        if stats:
            stats["percentage"] = round((stats["total_jobs"] / total_jobs * 100), 1) if total_jobs > 0 else 0.0
            stats["total_billed"] = round(stats["total_billed"], 2)
            stats["paid_revenue"] = round(stats["paid_revenue"], 2)
            breakdown_list.append(stats)
            
    # Include any custom/unmapped types if present
    for code, stats in stats_by_type.items():
        if code not in JOB_TYPE_MAP:
            stats["percentage"] = round((stats["total_jobs"] / total_jobs * 100), 1) if total_jobs > 0 else 0.0
            stats["total_billed"] = round(stats["total_billed"], 2)
            stats["paid_revenue"] = round(stats["paid_revenue"], 2)
            breakdown_list.append(stats)
            
    # Sort breakdown: highest total_jobs first
    breakdown_list.sort(key=lambda x: (x["total_jobs"], x["total_billed"]), reverse=True)
    
    return {
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat(),
        "total_jobs": total_jobs,
        "total_billed": round(total_billed_all, 2),
        "total_paid": round(total_paid_all, 2),
        "breakdown": breakdown_list
    }
