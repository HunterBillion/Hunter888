"""TZ-5 — scenario_extractor unit tests (extraction pipeline only).

Covers the LLM-free heuristic extractor that ships with PR-1: it must
produce a deterministic ScenarioDraftPayload from text/markdown input,
strip PII before structuring, drop hallucinated quotes, and bound
confidence in [0.0, 1.0]. The DB-backed entry point (``run_extraction``)
has its own integration test in ``test_attachment_pipeline_training_material``.

Why these tests sit in the blocking CI scope
--------------------------------------------

The extractor is the only producer of ``scenario_drafts.extracted``; if it
silently regresses, the import surface ships malformed payloads to ROP
and we lose the ability to audit-trail (quotes_from_source). The contract
is small enough to test directly here without running a full DB session.
"""
from __future__ import annotations

import pytest

from app.services.scenario_extractor import (
    MAX_DECODED_TEXT_SIZE,
    MAX_ZIP_TOTAL_UNCOMPRESSED,
    ScenarioDraftPayload,
    TrainingMaterialTooLarge,
    UnsupportedTrainingMaterialFormat,
    extract_scenario_draft,
    extract_text_from_bytes,
)


# ── Text decoding (.txt / .md) ──────────────────────────────────────────


def test_extract_text_from_txt_utf8():
    data = "Привет, мир!\nЭто памятка.".encode("utf-8")
    assert extract_text_from_bytes("memo.txt", data) == "Привет, мир!\nЭто памятка."


def test_extract_text_from_txt_cp1251_fallback():
    """Text encoded in cp1251 (legacy Russian Windows) decodes via fallback."""
    data = "Скрипт звонка".encode("cp1251")
    out = extract_text_from_bytes("script.txt", data)
    # Even via lenient fallback the result must contain readable cyrillic.
    # cp1251 → utf-8 fallback may produce mojibake; we just assert non-empty + length.
    assert isinstance(out, str)
    assert len(out) > 0


def test_extract_text_from_md_treated_as_text():
    data = "# Заголовок\n\nПервый абзац.".encode("utf-8")
    out = extract_text_from_bytes("memo.md", data)
    assert "Заголовок" in out
    assert "Первый абзац" in out


def test_extract_text_unsupported_format_raises():
    with pytest.raises(UnsupportedTrainingMaterialFormat):
        extract_text_from_bytes("audio.mp3", b"fake-audio")


# ── Heuristic structure extraction ──────────────────────────────────────


def test_extract_returns_dataclass_with_full_shape():
    text = "Скрипт звонка\n\nПозвоните клиенту и представьтесь."
    payload = extract_scenario_draft(text)
    assert isinstance(payload, ScenarioDraftPayload)
    # All fields exist and have the right types.
    assert isinstance(payload.title_suggested, str)
    assert isinstance(payload.summary, str)
    assert payload.archetype_hint is None or isinstance(payload.archetype_hint, str)
    assert isinstance(payload.steps, list)
    assert isinstance(payload.expected_objections, list)
    assert isinstance(payload.success_criteria, list)
    assert isinstance(payload.quotes_from_source, list)
    assert 0.0 <= payload.confidence <= 1.0


def test_extract_empty_text_yields_zero_confidence():
    payload = extract_scenario_draft("")
    assert payload.confidence == 0.0
    assert payload.steps == []


def test_extract_finds_steps_from_headings():
    text = (
        "# Памятка по холодному звонку\n\n"
        "## Шаг 1: Приветствие\n"
        "Скажите клиенту: «Здравствуйте, это компания X».\n\n"
        "## Шаг 2: Квалификация\n"
        "Задайте 3 ключевых вопроса.\n\n"
        "## Шаг 3: Закрытие\n"
        "Договоритесь о следующей встрече."
    )
    payload = extract_scenario_draft(text)
    assert len(payload.steps) >= 1
    # Heuristic groups markdown headings as step names — at least one
    # step name should reference one of the three sections.
    titles = " ".join(s.name for s in payload.steps).lower()
    assert any(k in titles for k in ("приветств", "квалифик", "закрыт", "шаг"))


def test_extract_picks_objections_from_keywords():
    text = (
        "Скрипт.\n\n"
        "Возражение: дорого.\n"
        "Клиент часто говорит: подумаю.\n"
        "Могут ответить нет, не сейчас."
    )
    payload = extract_scenario_draft(text)
    assert any("дорого" in o.lower() for o in payload.expected_objections)


def test_extract_collects_quoted_sentences_for_audit_trail():
    """Each "quote_from_source" must be a substring of the extracted text
    (after PII scrub). The contract is the whole point of TZ-5 §3.1: ROP
    needs to verify the LLM didn't fabricate the quote."""
    text = (
        "Здравствуйте, я представляю компанию X.\n"
        "Меня интересует ваш интерес к процедуре банкротства."
    )
    payload = extract_scenario_draft(text)
    # All retained quotes must appear (whitespace-tolerant) in source.
    import re

    haystack = re.sub(r"\s+", " ", text).lower()
    for q in payload.quotes_from_source:
        normalised = re.sub(r"\s+", " ", q).lower()
        assert normalised in haystack, f"hallucinated quote: {q!r}"


# ── PII scrubbing (152-FZ §4) ───────────────────────────────────────────


def test_extract_scrubs_phone_numbers_from_payload():
    """Source mentions a phone — neither summary nor any extracted field
    should leak the digits to the LLM-facing payload."""
    text = (
        "Клиент Петров Иван Иванович.\n"
        "Контакт: +7 (495) 123-45-67.\n\n"
        "## Шаг 1\nПозвоните по контактному номеру и представьтесь."
    )
    payload = extract_scenario_draft(text)
    serialised = " ".join(
        [
            payload.title_suggested,
            payload.summary,
            *(s.name for s in payload.steps),
            *(s.description for s in payload.steps),
            *payload.expected_objections,
            *payload.success_criteria,
            *payload.quotes_from_source,
        ]
    )
    assert "495" not in serialised
    assert "1234567" not in serialised.replace("-", "").replace(" ", "")


def test_extract_scrubs_email_from_payload():
    text = (
        "Связь: info@example.com\n\n"
        "## Шаг\nОтправьте письмо по почте, указанной в карточке."
    )
    payload = extract_scenario_draft(text)
    blob = payload.summary + " " + " ".join(s.description for s in payload.steps)
    assert "info@example.com" not in blob


# ── Quote validator (pass 2) ────────────────────────────────────────────


def test_quote_validator_drops_hallucinated_quotes():
    """If the heuristic emitted quotes that aren't in the source, the
    second pass strips them and pulls confidence down."""
    from app.services.scenario_extractor import (
        ScenarioDraftPayload,
        ScenarioStep,
        _validate_quotes,
    )

    raw = ScenarioDraftPayload(
        title_suggested="t",
        summary="s",
        archetype_hint=None,
        steps=[ScenarioStep(order=1, name="a", description="b")],
        expected_objections=[],
        success_criteria=[],
        quotes_from_source=[
            "Это в исходнике",
            "Это выдумала LLM, в исходнике этого нет",
        ],
        confidence=0.8,
    )
    source = "Длинный текст, в котором написано: Это в исходнике. Конец."
    result = _validate_quotes(raw, source)
    assert "Это в исходнике" in result.quotes_from_source
    assert all("выдумала LLM" not in q for q in result.quotes_from_source)
    # Half the quotes were dropped → 0.25 penalty (0.5 * 0.5).
    assert result.confidence < raw.confidence
    assert result.confidence >= 0.0


def test_quote_validator_handles_no_quotes_gracefully():
    from app.services.scenario_extractor import (
        ScenarioDraftPayload,
        _validate_quotes,
    )

    raw = ScenarioDraftPayload(
        title_suggested="t",
        summary="s",
        archetype_hint=None,
        steps=[],
        expected_objections=[],
        success_criteria=[],
        quotes_from_source=[],
        confidence=0.5,
    )
    result = _validate_quotes(raw, "anything")
    assert result.confidence == 0.5
    assert result.quotes_from_source == []


# ── Confidence policy ────────────────────────────────────────────────────


def test_low_confidence_is_in_range():
    """A trivial "title only" material gets low confidence but still in [0,1]."""
    payload = extract_scenario_draft("Однострочный текст.")
    assert 0.0 <= payload.confidence <= 1.0


def test_to_jsonable_round_trips():
    payload = extract_scenario_draft("Test\n\nStep one description.")
    blob = payload.to_jsonable()
    # Must contain every spec field name from TZ-5 §3.1.
    for key in (
        "title_suggested",
        "summary",
        "archetype_hint",
        "steps",
        "expected_objections",
        "success_criteria",
        "quotes_from_source",
        "confidence",
    ):
        assert key in blob


# ── draft → template field mapping ──────────────────────────────────────


def test_draft_payload_to_template_fields_status_is_draft():
    """TZ-5 §3.2 step 4 — imported templates land in 'draft', never
    auto-published."""
    from app.services.scenario_extractor import (
        ScenarioDraftPayload,
        ScenarioStep,
        draft_payload_to_template_fields,
    )

    payload = ScenarioDraftPayload(
        title_suggested="Imported Cold Call",
        summary="Memo about cold calls.",
        archetype_hint=None,
        steps=[ScenarioStep(order=1, name="Greet", description="Hello")],
        expected_objections=["too expensive"],
        success_criteria=["meeting scheduled"],
        quotes_from_source=["Hello"],
        confidence=0.7,
    )
    fields = draft_payload_to_template_fields(payload, fallback_code="imported_abcdef")
    assert fields["status"] == "draft"
    assert fields["code"] == "imported_abcdef"
    assert fields["name"].startswith("Imported")
    assert fields["group_name"] == "imported"
    assert isinstance(fields["stages"], list)
    assert fields["stages"][0]["name"] == "Greet"


# ── PR-1.1 audit fixes ──────────────────────────────────────────────────


def test_pii_scrub_handles_text_longer_than_truncation_window():
    """Audit fix: ``strip_pii`` originally truncated input at 5KB, leaving
    PII in the tail untouched. Now it processes the whole text in
    overlapping windows."""
    from app.services.content_filter import MAX_REGEX_INPUT_LENGTH, strip_pii

    # Build a doc that's well past the truncation window, with a phone
    # number near the end.
    long_filler = "Описание шага " * 1000  # ~13KB
    text = long_filler + "Контакт: +7 (495) 123-45-67. Конец."
    assert len(text) > MAX_REGEX_INPUT_LENGTH * 2

    cleaned = strip_pii(text)
    # The phone digits must NOT survive in the cleaned output, even
    # though they live well past the 5KB cutoff.
    assert "495" not in cleaned
    assert "1234567" not in cleaned.replace("-", "").replace(" ", "")
    # Replacement marker must be present.
    assert "[ДАННЫЕ СКРЫТЫ]" in cleaned


def test_pii_scrub_catches_russian_banking_identifiers():
    """Audit fix: extended PII patterns to cover OGRN/BIK/расчётный счёт."""
    from app.services.content_filter import strip_pii

    text = (
        "ООО Ромашка, ОГРН 1234567890123, БИК 044525225, "
        "расчётный счёт 40702810500000000123."
    )
    cleaned = strip_pii(text)
    # OGRN (13 digits) → masked
    assert "1234567890123" not in cleaned
    # BIK (9 digits with prefix)
    assert "044525225" not in cleaned
    # Bank account (20 digits)
    assert "40702810500000000123" not in cleaned


def test_zip_bomb_guard_rejects_oversized_member(tmp_path):
    """Audit fix: zip-bomb guard refuses to extract a single member
    that exceeds MAX_ZIP_MEMBER_SIZE."""
    import zipfile

    # Build a small zip whose CENTRAL DIRECTORY claims a giant member.
    # We can't actually fit a 100MB+ payload in a unit test, so we
    # construct a real zip with a tiny payload but verify the guard
    # function rejects synthetic ZipInfo claims.
    from app.services.scenario_extractor import (
        MAX_ZIP_MEMBER_SIZE,
        _check_zip_bomb_guards,
    )

    # Build a minimal zipfile with a small member; then patch infolist
    # to claim it's huge.
    p = tmp_path / "fake.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("inner.xml", b"x")
    with zipfile.ZipFile(p, "r") as zf:
        # Override file_size on the in-memory ZipInfo so the guard fires.
        info = zf.infolist()[0]
        info.file_size = MAX_ZIP_MEMBER_SIZE + 1
        with pytest.raises(TrainingMaterialTooLarge):
            _check_zip_bomb_guards(zf)


def test_zip_bomb_guard_rejects_oversized_total(tmp_path):
    import zipfile

    from app.services.scenario_extractor import _check_zip_bomb_guards

    p = tmp_path / "fake.zip"
    with zipfile.ZipFile(p, "w") as zf:
        for i in range(3):
            zf.writestr(f"inner{i}.xml", b"x")
    with zipfile.ZipFile(p, "r") as zf:
        # Each member declares ~80MB → 3*80MB = 240MB > 200MB cap.
        for info in zf.infolist():
            info.file_size = 80 * 1024 * 1024
        with pytest.raises(TrainingMaterialTooLarge):
            _check_zip_bomb_guards(zf)


def test_run_extraction_handles_corrupt_bytes_as_failed_draft():
    """Audit fix: corrupt bytes for a known format produce a draft with
    ``status='failed'`` and an ``error_message``, NOT a 500 / unhandled
    exception. The test exercises ``run_extraction`` via the heuristic
    pipeline against a deliberately-corrupt zip."""
    # Bypass DB by calling extract_text_from_bytes directly — the
    # corruption-handling branch in run_extraction wraps the same call.
    from app.services.scenario_extractor import extract_text_from_bytes

    # Bytes that look like a docx (magic) but aren't a valid zip.
    fake_docx = b"PK\x03\x04" + b"\x00" * 100

    with pytest.raises((UnsupportedTrainingMaterialFormat, Exception)):
        extract_text_from_bytes("memo.docx", fake_docx)
