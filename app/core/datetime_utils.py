from datetime import datetime, timezone, timedelta

# IST (Indian Standard Time) timezone: UTC + 5:30
IST = timezone(timedelta(hours=5, minutes=30))

def get_current_time() -> datetime:
    """Returns current Indian Standard Time (IST) as a naive datetime object."""
    return datetime.now(IST).replace(tzinfo=None)
