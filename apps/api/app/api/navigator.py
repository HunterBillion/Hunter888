"""Navigator API — curated quote library with 6-hour rotation.

GET /navigator/current   → current quote + metadata (public, no auth required)
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.services.navigator import get_navigator_response

router = APIRouter(prefix="/navigator", tags=["navigator"])


@router.get("/current")
async def get_current_navigator():
    """Return the current Navigator quote for the active 6-hour window.

    The quote changes at 00:00, 06:00, 12:00, 18:00 UTC.
    Response is deterministic — all users see the same quote simultaneously.
    No authentication required (used on the dashboard landing widget).
    """
    now = datetime.now(timezone.utc)
    return get_navigator_response(now)
