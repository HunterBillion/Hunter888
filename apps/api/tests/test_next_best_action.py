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


# ── TZ-4 §11.2.1 layer 2 — NBA outdated filter ───────────────────────────


def test_filter_safe_knowledge_refs_drops_outdated_keeps_others():
    """``outdated`` chunks are dropped (parity with the SQL filter at
    rag_legal.py:217); ``disputed`` / ``needs_review`` survive but
    flag the recommendation as ``requires_warning=True``."""
    from types import SimpleNamespace
    from app.services.next_best_action import filter_safe_knowledge_refs

    chunks = [
        SimpleNamespace(id=1, knowledge_status="actual"),
        SimpleNamespace(id=2, knowledge_status="outdated"),
        SimpleNamespace(id=3, knowledge_status="disputed"),
        SimpleNamespace(id=4, knowledge_status="needs_review"),
        SimpleNamespace(id=5, knowledge_status=None),  # NULL → actual default
    ]
    safe, requires_warning = filter_safe_knowledge_refs(chunks)
    assert [c.id for c in safe] == [1, 3, 4, 5]
    assert requires_warning is True


def test_filter_safe_knowledge_refs_clean_when_all_actual():
    """Pure ``actual`` set produces no warning flag — the manager
    sees a normal recommendation without the `источник требует
    проверки` chip."""
    from types import SimpleNamespace
    from app.services.next_best_action import filter_safe_knowledge_refs

    chunks = [
        SimpleNamespace(id=1, knowledge_status="actual"),
        SimpleNamespace(id=2, knowledge_status="actual"),
    ]
    safe, requires_warning = filter_safe_knowledge_refs(chunks)
    assert len(safe) == 2
    assert requires_warning is False


def test_filter_safe_knowledge_refs_empty_returns_empty():
    from app.services.next_best_action import filter_safe_knowledge_refs

    safe, requires_warning = filter_safe_knowledge_refs([])
    assert safe == []
    assert requires_warning is False


def test_filter_safe_knowledge_refs_custom_warning_status_set():
    """The ``needs_warning_status`` argument lets a future caller tune
    which non-actual statuses should annotate the recommendation. By
    default the spec mapping (``disputed``, ``needs_review``) is used.
    """
    from types import SimpleNamespace
    from app.services.next_best_action import filter_safe_knowledge_refs

    chunks = [SimpleNamespace(id=1, knowledge_status="disputed")]
    # Caller decides "disputed is OK, no warning needed" — empty set.
    safe, requires_warning = filter_safe_knowledge_refs(
        chunks, needs_warning_status=()
    )
    assert len(safe) == 1
    assert requires_warning is False
