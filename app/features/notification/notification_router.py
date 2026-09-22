from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.core.security import get_current_user
from app.features.notification.notification_models import (
    RegisterTokenRequest,
    DeviceToken,
    NotificationResponse
)
from app.features.notification.notification_service import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])

@router.post("/register-token", response_model=dict)
async def register_device_token(
    body: RegisterTokenRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Register or update an FCM device token for push notifications.
    """
    user_role = current_user.get("role", body.role or "admin")
    username = current_user.get("username")

    device = await notification_service.register_token(
        token=body.token,
        role=user_role,
        device_type=body.device_type or "android",
        user_id=username
    )
    return {
        "message": "Device token registered successfully",
        "token": device.token,
        "role": device.role
    }

@router.post("/trigger-salary-check", response_model=dict)
async def trigger_salary_check(
    force: bool = Query(default=True, description="Force check regardless of 8:00 PM cutoff or daily limit"),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger check for staff salary expense today.
    Notifies shop owner if salary is not recorded.
    """
    result = await notification_service.check_and_send_salary_reminder(force=force)
    return result

@router.post("/trigger-service-check", response_model=dict)
async def trigger_service_check(
    force: bool = Query(default=True, description="Force check regardless of daily limit"),
    current_user: dict = Depends(get_current_user)
):
    """
    Trigger check for due/overdue vehicle service reminders.
    """
    result = await notification_service.check_and_send_service_reminders(force=force)
    return result

@router.get("/status", response_model=dict)
async def get_notification_status(
    current_user: dict = Depends(get_current_user)
):
    """
    Get Firebase initialization status and registered token counts.
    """
    notification_service.ensure_initialized()
    admin_tokens = await notification_service.get_tokens_for_role("admin")
    all_tokens_count = await DeviceToken.count()

    return {
        "firebase_initialized": notification_service.initialized,
        "total_registered_devices": all_tokens_count,
        "admin_devices_count": len(admin_tokens),
        "last_salary_reminder_date": notification_service.last_salary_reminder_date,
        "last_service_reminder_date": notification_service.last_service_reminder_date,
    }
