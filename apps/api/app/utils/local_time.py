"""Local-time helpers for daily/streak windows.

Everything that decides "did the user do X today" must use the user's
business timezone (settings.app_tz) — not UTC. Otherwise a warm-up done
at 00:30 MSK lands on yesterday's UTC date and silently breaks streak +
daily-goal counting.

Usage:
    from app.utils.local_time import local_now, local_today

    now = local_now()          # aware datetime in Europe/Moscow (or configured)
    today = local_today()      # date() of `now` in the same tz
"""

from __future__ import annotations

from datetime import date as _date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.config import settings


@lru_cache(maxsize=4)
def _tz() -> ZoneInfo:
    """ZoneInfo for settings.app_tz, cached across the process."""
    return ZoneInfo(settings.app_tz or "Europe/Moscow")


def local_now() -> datetime:
    """Timezone-aware `datetime.now` in the app's business timezone."""
    return datetime.now(_tz())


def local_today() -> _date:
    """`date` of `local_now()`."""
    return local_now().date()


def to_local(dt: datetime) -> datetime:
    """Convert any aware datetime to the app's business timezone."""
    if dt.tzinfo is None:
        # Treat naïve datetimes as UTC — that's the convention everywhere
        # else in this codebase (SQLAlchemy returns aware UTC datetimes).
        from datetime import timezone as _tz_utc
        dt = dt.replace(tzinfo=_tz_utc.utc)
    return dt.astimezone(_tz())
