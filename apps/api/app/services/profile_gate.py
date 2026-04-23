from __future__ import annotations

from typing import Any


REQUIRED_ONBOARDING_PREFS = (
    "specialization",
    "experience_level",
    "training_mode",
)


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def required_profile_missing(
    user: Any,
    *,
    preferences: dict | None = None,
) -> list[str]:
    """Return canonical missing profile fields needed for training/call flows."""
    missing: list[str] = []

    if _is_blank(getattr(user, "full_name", None)):
        missing.append("full_name")
    if getattr(user, "role", None) is None:
        missing.append("role")

    prefs = preferences if preferences is not None else (getattr(user, "preferences", None) or {})
    for key in REQUIRED_ONBOARDING_PREFS:
        if _is_blank(prefs.get(key)):
            missing.append(f"preferences.{key}")

    return missing


def is_profile_complete(
    user: Any,
    *,
    preferences: dict | None = None,
) -> bool:
    return len(required_profile_missing(user, preferences=preferences)) == 0
