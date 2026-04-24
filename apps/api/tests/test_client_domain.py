import uuid
from datetime import datetime, timezone
from decimal import Decimal

from app.models.client import ClientStatus
from app.services.client_domain import _json_safe, map_legacy_client_status


def test_map_legacy_client_status_maps_lifecycle_and_work_state():
    assert map_legacy_client_status(ClientStatus.new) == ("new", "active")
    assert map_legacy_client_status(ClientStatus.consent_given) == ("consent_received", "active")
    assert map_legacy_client_status(ClientStatus.in_process) == ("case_in_progress", "active")
    assert map_legacy_client_status(ClientStatus.paused) == ("case_in_progress", "paused")
    assert map_legacy_client_status(ClientStatus.consent_revoked) == ("consent_received", "consent_revoked")


def test_json_safe_normalizes_non_json_types():
    now = datetime.now(timezone.utc)
    value = {
        "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "when": now,
        "amount": Decimal("123.45"),
        "status": ClientStatus.completed,
        "nested": [Decimal("1.2"), {"client": ClientStatus.lost}],
    }

    normalized = _json_safe(value)

    assert normalized == {
        "id": "11111111-1111-1111-1111-111111111111",
        "when": now.isoformat(),
        "amount": "123.45",
        "status": "completed",
        "nested": ["1.2", {"client": "lost"}],
    }
