import os
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from app.core.datetime_utils import get_current_time
from app.features.notification.notification_models import DeviceToken
from app.features.expense.expense_models import Expense
from app.features.vehicle.vehicle_models import Vehicle
from app.features.job_card.job_card_models import JobCard

logger = logging.getLogger("mcc_garage.notifications")

class FirebaseNotificationService:
    def __init__(self):
        self.initialized = False
        self._init_firebase()
        # Track last sent date to avoid multiple notifications per day
        self.last_salary_reminder_date: Optional[str] = None
        self.last_service_reminder_date: Optional[str] = None

    def _init_firebase(self):
        try:
            import firebase_admin
            from firebase_admin import credentials

            if firebase_admin._apps:
                self.initialized = True
                logger.info("Firebase Admin already initialized.")
                return

            # Check environment variable or standard file paths
            cred_path = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")
            candidates = [
                cred_path,
                "serviceAccountKey.json",
                "firebase-credentials.json",
                "app/serviceAccountKey.json"
            ]

            valid_path = next((p for p in candidates if p and os.path.exists(p)), None)

            if valid_path:
                cred = credentials.Certificate(valid_path)
                firebase_admin.initialize_app(cred)
                self.initialized = True
                logger.info(f"Firebase Admin successfully initialized from {valid_path}")
            else:
                logger.warning(
                    "Firebase service account key not found. Push notifications will run in mock/log mode. "
                    "Place 'serviceAccountKey.json' in backend root to enable live FCM notifications."
                )
                self.initialized = False
        except Exception as e:
            logger.error(f"Failed to initialize Firebase Admin SDK: {e}")
            self.initialized = False

    def ensure_initialized(self) -> bool:
        if not self.initialized:
            self._init_firebase()
        return self.initialized

    async def register_token(
        self,
        token: str,
        role: str = "admin",
        device_type: str = "android",
        user_id: Optional[str] = None
    ) -> DeviceToken:
        existing = await DeviceToken.find_one(DeviceToken.token == token)
        current_time = get_current_time()
        if existing:
            existing.role = role
            existing.device_type = device_type
            if user_id:
                existing.user_id = user_id
            existing.updated_at = current_time
            await existing.save()
            return existing

        new_token = DeviceToken(
            token=token,
            role=role,
            device_type=device_type,
            user_id=user_id,
            created_at=current_time,
            updated_at=current_time
        )
        await new_token.insert()
        return new_token

    async def get_tokens_for_role(self, role: str = "admin") -> List[str]:
        tokens = await DeviceToken.find(DeviceToken.role == role).to_list()
        return [t.token for t in tokens if t.token]

    async def send_multicast(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        if not tokens:
            return {"success": True, "sent_count": 0, "failure_count": 0, "message": "No tokens registered"}

        # Format all data values to strings as required by FCM
        safe_data = {str(k): str(v) for k, v in (data or {}).items()}

        self.ensure_initialized()
        if not self.initialized:
            logger.info(
                f"[FCM MOCK] (Firebase not configured) Push to {len(tokens)} devices: "
                f"Title='{title}', Body='{body}', Data={safe_data}"
            )
            return {
                "success": True,
                "sent_count": len(tokens),
                "failure_count": 0,
                "message": f"Mock notification logged for {len(tokens)} device(s)",
                "mode": "mock"
            }

        try:
            from firebase_admin import messaging

            message = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data=safe_data,
                tokens=tokens
            )
            response = messaging.send_each_for_multicast(message)
            
            # Clean up unregistered / invalid tokens
            if response.failure_count > 0:
                failed_tokens = []
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        failed_tokens.append(tokens[idx])
                if failed_tokens:
                    logger.info(f"Pruning {len(failed_tokens)} stale FCM tokens")
                    await DeviceToken.find({"token": {"": failed_tokens}}).delete()

            return {
                "success": True,
                "sent_count": response.success_count,
                "failure_count": response.failure_count,
                "message": f"Sent {response.success_count} notifications ({response.failure_count} failed)",
                "mode": "live"
            }
        except Exception as e:
            logger.error(f"Error sending FCM multicast notification: {e}")
            return {
                "success": False,
                "sent_count": 0,
                "failure_count": len(tokens),
                "message": str(e),
                "mode": "error"
            }

    async def send_to_role(
        self,
        role: str,
        title: str,
        body: str,
        data: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        tokens = await self.get_tokens_for_role(role)
        return await self.send_multicast(tokens, title, body, data)

    async def check_and_send_salary_reminder(self, force: bool = False) -> Dict[str, Any]:
        """
        Checks if staff salary has been recorded today.
        Notifies shop owner after 8:00 PM (20:00) IST if unrecorded.
        """
        now = get_current_time()
        today_str = now.strftime("%Y-%m-%d")

        # Unless forced, only run after 8:00 PM (20:00)
        if not force and now.hour < 20:
            return {
                "checked": True,
                "triggered": False,
                "reason": f"Current time ({now.strftime('%H:%M')}) is before 8:00 PM cutoff."
            }

        # Avoid spamming multiple times on the same date unless forced
        if not force and self.last_salary_reminder_date == today_str:
            return {
                "checked": True,
                "triggered": False,
                "reason": f"Salary reminder already sent today ({today_str})."
            }

        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Check if any expense exists today for category containing 'salary'
        salary_expenses = await Expense.find(
            Expense.date >= start_of_today,
            Expense.date <= end_of_today,
            {"category": {"": "salary", "off on off off off off off off off off on off on off off off off off on off off off on on off off off off on off off off off off off off off off off off off on off off off off off off off on off on on off off off on off off on off off on off off on off on off off on off on off off off off on off off off on off off on off off off off off off off off on off on off off on off off off off off off off off off off off off on off off off on off on off on on off off off off on on off off on on off on off on on off off off off on on off off on off off off off off on off off on off off on off off off off off off on off off off off on on off on off off off off off on off on off off off off off off off off off off on on off on off off off": "i"}}
        ).to_list()

        if len(salary_expenses) > 0:
            return {
                "checked": True,
                "triggered": False,
                "reason": f"Today's salary already recorded ({len(salary_expenses)} entry found)."
            }

        # Salary has NOT been recorded for today
        title = "Staff Salary Reminder"
        body = "Today's staff salary has not been recorded yet. Please update staff salary in Expenses."
        data = {
            "type": "salary_reminder",
            "route": "/create-expense",
            "category": "Staff Salary"
        }

        result = await self.send_to_role(role="admin", title=title, body=body, data=data)
        self.last_salary_reminder_date = today_str
        return {
            "checked": True,
            "triggered": True,
            "notification_result": result
        }

    async def check_and_send_service_reminders(self, force: bool = False) -> Dict[str, Any]:
        """
        Checks for vehicles due or overdue for service today, excluding active jobs.
        """
        now = get_current_time()
        today_str = now.strftime("%Y-%m-%d")

        if not force and self.last_service_reminder_date == today_str:
            return {
                "checked": True,
                "triggered": False,
                "reason": f"Service reminder already sent today ({today_str})."
            }

        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Exclude vehicles currently with active job cards
        active_jobs = await JobCard.find(
            {"status": {"": ["In Progress", "Pending Delivery"]}}
        ).to_list()
        active_vehicle_ids = {jc.vehicle_id for jc in active_jobs if jc.vehicle_id}

        query: Dict[str, Any] = {
            "next_service_date": {"": None, "": end_of_today}
        }
        if active_vehicle_ids:
            query["_id"] = {"": list(active_vehicle_ids)}

        due_vehicles = await Vehicle.find(query).to_list()

        if not due_vehicles:
            return {
                "checked": True,
                "triggered": False,
                "reason": "No vehicles are due for service today."
            }

        if len(due_vehicles) == 1:
            v = due_vehicles[0]
            st = v.next_service_type or "scheduled service"
            title = "Vehicle Service Due Today"
            body = f"Vehicle {v.registration_number} is due for {st}. Tap to view details."
        else:
            title = "Vehicle Service Reminders"
            body = f"{len(due_vehicles)} vehicles are due or overdue for service today. Tap to review reminders."

        data = {
            "type": "service_reminder",
            "route": "/main",
            "due_count": str(len(due_vehicles))
        }

        result = await self.send_to_role(role="admin", title=title, body=body, data=data)
        self.last_service_reminder_date = today_str
        return {
            "checked": True,
            "triggered": True,
            "due_count": len(due_vehicles),
            "notification_result": result
        }

notification_service = FirebaseNotificationService()
