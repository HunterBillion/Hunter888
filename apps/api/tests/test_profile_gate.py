from types import SimpleNamespace

from app.services.profile_gate import is_profile_complete, required_profile_missing


def _make_user(
    *,
    full_name: str = "Иван Иванов",
    role: str = "manager",
    preferences: dict | None = None,
):
    return SimpleNamespace(
        full_name=full_name,
        role=role,
        preferences=preferences or {},
    )


def test_profile_complete_when_required_fields_present():
    user = _make_user(
        preferences={
            "gender": "male",
            "role_title": "Менеджер по банкротству",
            "lead_source": "sso_google",
            "primary_contact": "+79990000000",
            "specialization": "bfl",
            "experience_level": "beginner",
            "training_mode": "structured",
        },
    )
    assert required_profile_missing(user) == []
    assert is_profile_complete(user) is True


def test_profile_incomplete_reports_missing_preferences():
    user = _make_user(preferences={"specialization": "bfl"})
    missing = required_profile_missing(user)
    assert "preferences.gender" in missing
    assert "preferences.role_title" in missing
    assert "preferences.lead_source" in missing
    assert "preferences.primary_contact" in missing
    assert "preferences.experience_level" in missing
    assert "preferences.training_mode" in missing
    assert is_profile_complete(user) is False


def test_profile_incomplete_reports_blank_name():
    user = _make_user(full_name="   ", preferences={})
    missing = required_profile_missing(user)
    assert "full_name" in missing
    assert "preferences.gender" in missing
    assert "preferences.specialization" in missing
