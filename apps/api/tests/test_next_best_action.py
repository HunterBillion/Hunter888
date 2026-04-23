import uuid
from datetime import datetime, timedelta, timezone

from app.models.client import ClientStatus, RealClient
from app.services.next_best_action import choose_next_best_action


def _client(status: ClientStatus, next_contact_at=None):
    return RealClient(
        id=uuid.uuid4(),
        manager_id=uuid.uuid4(),
        full_name="Вера Константиновна",
        status=status,
        next_contact_at=next_contact_at,
    )


def test_overdue_next_contact_wins():
    now = datetime(2026, 4, 23, tzinfo=timezone.utc)
    action = choose_next_best_action(
        client=_client(ClientStatus.thinking, now - timedelta(minutes=5)),
        now=now,
    )
    assert action.action == "make_follow_up_call"
    assert action.priority == 1
    assert action.mode == "call"


def test_new_client_goes_to_center():
    action = choose_next_best_action(client=_client(ClientStatus.new))
    assert action.action == "start_center_call"
    assert action.mode == "center"


def test_consent_given_requests_documents():
    action = choose_next_best_action(client=_client(ClientStatus.consent_given))
    assert action.action == "request_documents"
    assert action.mode == "chat"
    assert "passport" in action.payload["required_documents"]


def test_pending_attachments_prioritized_before_status_action():
    action = choose_next_best_action(
        client=_client(ClientStatus.new),
        pending_attachments=2,
    )
    assert action.action == "process_documents"
    assert action.priority == 2
