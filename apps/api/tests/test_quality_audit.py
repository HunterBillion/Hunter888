from types import SimpleNamespace

from app.services.quality_audit import review_session_quality


def _msg(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


def test_quality_review_penalizes_center_without_outcome():
    session = SimpleNamespace(
        custom_params={"session_mode": "center"},
        scoring_details={},
    )
    review = review_session_quality(session, [
        _msg("user", "Здравствуйте"),
        _msg("assistant", "Здравствуйте."),
    ])
    assert review.score < 100
    assert any(f.code == "missing_terminal_outcome" for f in review.findings)


def test_quality_review_detects_repeats():
    session = SimpleNamespace(
        custom_params={"session_mode": "chat"},
        scoring_details={"call_outcome": "continue"},
    )
    review = review_session_quality(session, [
        _msg("assistant", "Пришлите паспорт и документы от приставов."),
        _msg("user", "Хорошо."),
        _msg("assistant", "Пришлите паспорт и документы от приставов."),
    ])
    assert review.metrics["repeat_count"] == 1
    assert review.score <= 85


def test_quality_review_clean_next_step_passes_high():
    session = SimpleNamespace(
        custom_params={"session_mode": "chat"},
        scoring_details={"call_outcome": "continue"},
    )
    review = review_session_quality(session, [
        _msg("user", "Есть просрочки."),
        _msg("assistant", "Зафиксировал. Дальше уточню, были ли исполнительные производства."),
    ])
    assert review.score == 100
    assert review.metrics["missing_next_step_count"] == 0
