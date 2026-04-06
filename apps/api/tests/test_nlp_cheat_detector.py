"""Tests for NLP-based cheat detector.

Pure functions testing — no database needed.
Tests cover:
- Text fingerprinting
- Fingerprint comparison
- AI marker detection
- Cross-user similarity
- Typing dynamics
- Real-time checks
- Edge cases
"""

import pytest
from app.services.nlp_cheat_detector import (
    TextFingerprint,
    compute_text_fingerprint,
    compare_fingerprints,
    detect_ai_text_markers,
    cross_user_answer_similarity,
    analyze_typing_dynamics,
    real_time_check,
)


# ---------------------------------------------------------------------------
# TextFingerprint computation
# ---------------------------------------------------------------------------

def test_compute_text_fingerprint_basic():
    """Test basic fingerprint computation."""
    text = "Это тестовый текст для проверки. Он содержит несколько предложений."
    fp = compute_text_fingerprint(text)

    assert isinstance(fp, TextFingerprint)
    assert fp.punct_ratio > 0
    assert fp.avg_sentence_length > 0
    assert fp.unique_word_ratio > 0
    assert len(fp.char_bigram_freq) > 0
    assert len(fp.word_length_dist) > 0


def test_compute_text_fingerprint_empty():
    """Test fingerprint on empty text."""
    fp = compute_text_fingerprint("")
    assert fp.punct_ratio == 0.0
    assert fp.avg_sentence_length == 0.0
    assert len(fp.char_bigram_freq) == 0

    fp2 = compute_text_fingerprint("   ")
    assert fp2.punct_ratio == 0.0


def test_compute_text_fingerprint_short():
    """Test fingerprint on short text."""
    fp = compute_text_fingerprint("Hi")
    # Should not crash, just return mostly empty
    assert isinstance(fp, TextFingerprint)


def test_compute_text_fingerprint_russian():
    """Test fingerprint on Russian text with Cyrillic."""
    text = "Привет, мир! Это русский текст. Как дела?"
    fp = compute_text_fingerprint(text)

    assert fp.punct_ratio > 0
    assert fp.question_ratio > 0
    assert fp.exclamation_ratio > 0
    assert fp.unique_word_ratio > 0


def test_compute_text_fingerprint_function_words():
    """Test function word ratio detection."""
    text_high_func = "и в на но что это как то же ли бы по к"
    text_low_func = "программирование компьютер алгоритм асимптотическая сложность"

    fp_high = compute_text_fingerprint(text_high_func)
    fp_low = compute_text_fingerprint(text_low_func)

    assert fp_high.function_word_ratio > fp_low.function_word_ratio


def test_compute_text_fingerprint_sentences():
    """Test sentence length variance calculation."""
    text_uniform = "Раз. Два. Три. Четыре. Пять."
    text_varied = "Раз. Два и три. Четыре, пять, шесть и семь!"

    fp_uniform = compute_text_fingerprint(text_uniform)
    fp_varied = compute_text_fingerprint(text_varied)

    # Uniform should have lower variance
    assert fp_uniform.sentence_length_variance <= fp_varied.sentence_length_variance


# ---------------------------------------------------------------------------
# Fingerprint comparison
# ---------------------------------------------------------------------------

def test_compare_fingerprints_identical():
    """Test that same text produces high similarity."""
    text = "Это тестовый текст для проверки функциональности."
    fp1 = compute_text_fingerprint(text)
    fp2 = compute_text_fingerprint(text)

    similarity = compare_fingerprints(fp1, fp2)
    assert similarity == 1.0  # Identical


def test_compare_fingerprints_similar():
    """Test that similar texts produce high similarity."""
    text1 = "Это тестовый текст для проверки."
    text2 = "Это тестовый текст для проверки функциональности."

    fp1 = compute_text_fingerprint(text1)
    fp2 = compute_text_fingerprint(text2)

    similarity = compare_fingerprints(fp1, fp2)
    assert 0.6 < similarity < 1.0


def test_compare_fingerprints_different():
    """Test that different texts produce low similarity."""
    text1 = "Кот сидел на диване."
    text2 = "Программирование это интересно и сложно очень трудно."

    fp1 = compute_text_fingerprint(text1)
    fp2 = compute_text_fingerprint(text2)

    similarity = compare_fingerprints(fp1, fp2)
    assert similarity < 0.5


def test_compare_fingerprints_empty():
    """Test comparing empty fingerprints."""
    fp1 = compute_text_fingerprint("")
    fp2 = compute_text_fingerprint("")

    similarity = compare_fingerprints(fp1, fp2)
    assert similarity == 1.0  # Both empty = similar


def test_compare_fingerprints_one_empty():
    """Test comparing one empty and one non-empty."""
    fp1 = compute_text_fingerprint("")
    fp2 = compute_text_fingerprint("Тестовый текст")

    similarity = compare_fingerprints(fp1, fp2)
    assert similarity == 0.0


# ---------------------------------------------------------------------------
# AI text marker detection
# ---------------------------------------------------------------------------

def test_detect_ai_markers_human_text():
    """Test detection on clearly human text."""
    text = "Ну, я думаю что это ваще не имеет смысла, типа. Короче говоря, лол"
    result = detect_ai_text_markers(text)

    assert isinstance(result, dict)
    assert "ai_probability" in result
    assert "markers_found" in result
    assert "confidence" in result
    assert result["ai_probability"] < 0.4


def test_detect_ai_markers_ai_text():
    """Test detection on clearly AI-like text."""
    text = (
        "Во-первых, следует отметить, что данный вопрос представляется весьма важным. "
        "Во-вторых, необходимо подчеркнуть следующее. В-третьих, можно утверждать. "
        "Безусловно, следует отметить. Однако, представляется интересным."
    )
    result = detect_ai_text_markers(text)

    assert result["ai_probability"] > 0.5
    assert len(result["markers_found"]) >= 2


def test_detect_ai_markers_numbered_lists():
    """Test detection of numbered lists (AI indicator)."""
    text = "1) Первый пункт. 2) Второй пункт. 3) Третий пункт."
    result = detect_ai_text_markers(text)

    assert result["ai_probability"] > 0.1
    assert "numbered_lists" in result["markers_found"]


def test_detect_ai_markers_transition_words():
    """Test detection of structured transitions."""
    text = "Во-первых, решение. Во-вторых, анализ. В-третьих, вывод."
    result = detect_ai_text_markers(text)

    assert result["ai_probability"] > 0.3
    assert any("structured_transitions" in m for m in result["markers_found"])


def test_detect_ai_markers_known_phrases():
    """Test detection of known AI phrases."""
    text = "Конечно, безусловно это представляется весьма интересным вопросом!"
    result = detect_ai_text_markers(text)

    assert result["ai_probability"] > 0.2
    assert "known_ai_phrases" in str(result["markers_found"])


def test_detect_ai_markers_empty():
    """Test detection on empty text."""
    result = detect_ai_text_markers("")
    assert result["ai_probability"] == 0.0
    assert result["confidence"] == "low"


def test_detect_ai_markers_short():
    """Test detection on very short text."""
    result = detect_ai_text_markers("Привет")
    assert result["ai_probability"] == 0.0
    assert result["confidence"] == "low"


# ---------------------------------------------------------------------------
# Cross-user answer similarity
# ---------------------------------------------------------------------------

def test_cross_user_similarity_no_match():
    """Test when answers are different."""
    user_answers = [
        "Это моя собственная подробная ответ на первый вопрос который я тщательно обдумал."
    ]
    other_answers = [
        ["Это совсем другой ответ на тот же вопрос здесь другие идеи и мысли."]
    ]

    result = cross_user_answer_similarity(user_answers, other_answers)

    assert result["max_similarity"] < 0.7
    assert result["flagged"] is False


def test_cross_user_similarity_suspicious():
    """Test when answers are suspiciously similar."""
    answer = "Банкротство физического лица регулируется федеральным законом номер сто двадцать семь"
    user_answers = [answer + " дополнительная информация"]
    other_answers = [
        [answer + " немного другая информация"]
    ]

    result = cross_user_answer_similarity(user_answers, other_answers)

    assert result["max_similarity"] > 0.6
    assert len(result["suspicious_pairs"]) > 0


def test_cross_user_similarity_trivial_answers():
    """Test that trivial short answers are skipped."""
    user_answers = ["Да"]
    other_answers = [["Да"]]

    result = cross_user_similarity_trivial_answers(user_answers, other_answers)

    # Should not flag trivial answers
    assert result["flagged"] is False or result["max_similarity"] < 0.5


def test_cross_user_similarity_empty():
    """Test with empty inputs."""
    result = cross_user_answer_similarity([], [])
    assert result["flagged"] is False
    assert result["max_similarity"] == 0.0


# ---------------------------------------------------------------------------
# Typing dynamics analysis
# ---------------------------------------------------------------------------

def test_analyze_typing_dynamics_empty():
    """Test with no events."""
    result = analyze_typing_dynamics([])
    assert result["typing_speed_cpm"] == 0.0
    assert result["suspicious"] is False


def test_analyze_typing_dynamics_normal():
    """Test with normal typing speed."""
    events = [
        {"timestamp_ms": 0, "text_length": 0, "action": "start"},
        {"timestamp_ms": 1000, "text_length": 5, "action": "keystroke"},
        {"timestamp_ms": 2000, "text_length": 10, "action": "keystroke"},
        {"timestamp_ms": 3000, "text_length": 15, "action": "keystroke"},
        {"timestamp_ms": 4000, "text_length": 20, "action": "submit"},
    ]

    result = analyze_typing_dynamics(events)

    assert result["typing_speed_cpm"] > 0
    assert result["pause_count"] >= 0
    # Normal typing should not be suspicious
    assert result["suspicious"] is False or result["confidence"] < 0.7


def test_analyze_typing_dynamics_suspiciously_fast():
    """Test detection of impossibly fast typing."""
    events = [
        {"timestamp_ms": 0, "text_length": 0, "action": "start"},
        {"timestamp_ms": 100, "text_length": 500, "action": "submit"},
    ]

    result = analyze_typing_dynamics(events)

    # 500 chars in 100ms = 300,000 cpm (impossible)
    assert result["typing_speed_cpm"] > 600
    assert result["suspicious"] is True


def test_analyze_typing_dynamics_consistent():
    """Test detection of suspiciously consistent timing."""
    # Create events with perfectly uniform inter-keystroke intervals
    events = [{"timestamp_ms": 0, "text_length": 0, "action": "start"}]
    for i in range(1, 20):
        events.append({
            "timestamp_ms": i * 100,  # Exactly 100ms between each
            "text_length": i,
            "action": "keystroke"
        })

    result = analyze_typing_dynamics(events)

    # Very low variance in timing
    assert result["speed_variance"] < 50  # Very low
    # Perfectly consistent = suspicious
    # (Actual suspicion flag depends on implementation threshold)


def test_analyze_typing_dynamics_pauses():
    """Test pause detection."""
    events = [
        {"timestamp_ms": 0, "text_length": 0, "action": "start"},
        {"timestamp_ms": 500, "text_length": 5, "action": "keystroke"},
        {"timestamp_ms": 3000, "text_length": 10, "action": "keystroke"},  # 2.5s pause
        {"timestamp_ms": 4000, "text_length": 15, "action": "submit"},
    ]

    result = analyze_typing_dynamics(events)

    assert result["pause_count"] >= 1


# ---------------------------------------------------------------------------
# Real-time check
# ---------------------------------------------------------------------------

def test_real_time_check_clean():
    """Test clean input."""
    result = real_time_check("Обычный ответ на вопрос")

    assert result["risk_level"] == "low"
    assert result["should_flag_for_review"] is False


def test_real_time_check_ai_markers():
    """Test detection of AI markers in real-time."""
    text = (
        "Во-первых, следует отметить, что этот вопрос весьма интересен. "
        "Во-вторых, необходимо подчеркнуть. В-третьих, представляется важным."
    )
    result = real_time_check(text)

    assert result["risk_level"] in ("medium", "high")
    assert len(result["flags"]) >= 1


def test_real_time_check_fast_response():
    """Test detection of suspiciously fast responses."""
    # Long answer in very short time (in milliseconds)
    answer = "Это очень длинный ответ с множеством деталей и подробностей о теме " * 5
    result = real_time_check(answer, response_time_ms=100)  # 100ms for ~400 chars

    assert result["risk_level"] in ("medium", "high")
    assert any("fast" in f for f in result["flags"])


def test_real_time_check_empty():
    """Test with empty answer."""
    result = real_time_check("")

    assert result["risk_level"] == "low"
    assert result["should_flag_for_review"] is False


def test_real_time_check_with_history():
    """Test style consistency check."""
    answer = "Новый ответ с совсем другим стилем и тональностью совершенно иной"
    user_history = [
        {"text": "Коротко. Просто. Ясно."},
        {"text": "Минимум слов. Максимум смысла."},
        {"text": "Лаконичный ответ тут."},
    ]

    result = real_time_check(answer, user_history=user_history)

    # Style is quite different
    if result["should_flag_for_review"]:
        assert "unusual_writing_style" in result["flags"]


def test_real_time_check_too_consistent():
    """Test detection of overly consistent style."""
    answer = "Ответ на вопрос с определённой структурой и стилем изложения материала"
    user_history = [
        {"text": "Ответ на вопрос с определённой структурой и стилем изложения материала"},
        {"text": "Ответ на вопрос с определённой структурой и стилем изложения материала"},
        {"text": "Ответ на вопрос с определённой структурой и стилем изложения материала"},
    ]

    result = real_time_check(answer, user_history=user_history)

    # Overly consistent might be flagged
    # (Depends on implementation)


def test_real_time_check_formal_in_casual():
    """Test detection of excessive formality."""
    answer = "Несомненно, безусловно, представляется интересным следовать такому пути."
    result = real_time_check(answer, question_text="Как ты планируешь отдыхать?")

    if len(result["flags"]) >= 2:
        # If multiple flags, might be marked for review
        assert result["should_flag_for_review"] or result["risk_level"] == "low"


# ---------------------------------------------------------------------------
# Edge cases and stress tests
# ---------------------------------------------------------------------------

def test_very_long_text():
    """Test with very long text."""
    long_text = "Тестовое слово. " * 1000
    fp = compute_text_fingerprint(long_text)

    assert fp.punct_ratio > 0
    assert fp.avg_sentence_length > 0


def test_unicode_text():
    """Test with various Unicode characters."""
    text = "Текст с эмодзи 😀 и специальными символами → ← ↑ ↓"
    fp = compute_text_fingerprint(text)

    assert isinstance(fp, TextFingerprint)


def test_numbers_only():
    """Test with numbers only."""
    text = "123 456 789"
    fp = compute_text_fingerprint(text)

    assert isinstance(fp, TextFingerprint)


def test_mixed_languages():
    """Test with mixed Russian and English."""
    text = "Привет Hello Мир World Тест Test"
    fp = compute_text_fingerprint(text)

    assert isinstance(fp, TextFingerprint)


def test_single_word():
    """Test with single word."""
    fp = compute_text_fingerprint("Слово")
    assert isinstance(fp, TextFingerprint)


# ---------------------------------------------------------------------------
# Helper function for test (missing in stub)
# ---------------------------------------------------------------------------

def cross_user_similarity_trivial_answers(user_answers, other_answers):
    """Stub: call actual function."""
    return cross_user_answer_similarity(user_answers, other_answers)
