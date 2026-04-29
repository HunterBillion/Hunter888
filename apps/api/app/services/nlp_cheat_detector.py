"""NLP-based cheat detection module for PvP duels.

Advanced detection using pure Python (no external NLP libs):
- Text fingerprinting: char bigrams, word lengths, punctuation patterns
- AI text marker detection: Russian-specific patterns
- Cross-user answer similarity: comparing players' responses
- Typing dynamics: keystroke timing analysis
- Real-time lightweight checks for immediate feedback

All functions use stdlib + regex only. No nltk, spacy, sklearn dependencies.
"""

import re
import statistics
import logging
from dataclasses import dataclass, field
from typing import Optional

# Sprint 0 (2026-04-29): the four lexicons below moved to a shared module
# (app.services.ai_lexicon) so the call-mode sentence-gate can reuse the
# same source. These re-imports preserve the pre-existing public API of
# this module — anything that did `from app.services.nlp_cheat_detector
# import KNOWN_RUSSIAN_AI_PHRASES` keeps working unchanged.
from app.services.ai_lexicon import (  # noqa: F401
    KNOWN_RUSSIAN_AI_PHRASES,
    RUSSIAN_FUNCTION_WORDS,
    RUSSIAN_INFORMAL_MARKERS,
    RUSSIAN_TRANSITION_WORDS,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TextFingerprint:
    """Linguistic fingerprint of a text sample."""
    char_bigram_freq: dict[str, float] = field(default_factory=dict)
    word_length_dist: dict[int, float] = field(default_factory=dict)
    punct_ratio: float = 0.0
    avg_sentence_length: float = 0.0
    sentence_length_variance: float = 0.0
    unique_word_ratio: float = 0.0
    function_word_ratio: float = 0.0
    russian_informal_markers: int = 0
    transition_word_count: int = 0
    question_ratio: float = 0.0
    exclamation_ratio: float = 0.0
    comma_density: float = 0.0
    paragraph_structure_score: float = 0.0


# ---------------------------------------------------------------------------
# Text Fingerprinting
# ---------------------------------------------------------------------------

def compute_text_fingerprint(text: str) -> TextFingerprint:
    """Compute linguistic fingerprint of text using pure Python.

    Returns a TextFingerprint dataclass with 13+ linguistic features.
    """
    if not text or len(text.strip()) < 5:
        return TextFingerprint()

    fp = TextFingerprint()

    # Normalize
    normalized = text.lower()
    words = normalized.split()

    if not words:
        return fp

    # 1. Character bigrams (normalized frequency)
    bigram_counts: dict[str, int] = {}
    for i in range(len(normalized) - 1):
        if normalized[i].isalnum() or normalized[i] in " -'":
            bigram = normalized[i:i+2]
            bigram_counts[bigram] = bigram_counts.get(bigram, 0) + 1

    total_bigrams = sum(bigram_counts.values())
    if total_bigrams > 0:
        fp.char_bigram_freq = {
            bg: count / total_bigrams
            for bg, count in sorted(bigram_counts.items(), key=lambda x: x[1], reverse=True)[:50]
        }

    # 2. Word length distribution (normalized)
    word_lengths: dict[int, int] = {}
    for word in words:
        clean_word = ''.join(c for c in word if c.isalnum())
        if clean_word:
            wlen = len(clean_word)
            word_lengths[wlen] = word_lengths.get(wlen, 0) + 1

    total_words = sum(word_lengths.values())
    if total_words > 0:
        fp.word_length_dist = {
            wlen: count / total_words
            for wlen, count in sorted(word_lengths.items())
        }

    # 3. Punctuation ratio
    punct_chars = sum(1 for c in text if c in '.,!?;:"\'()[]{}')
    fp.punct_ratio = punct_chars / max(len(text), 1)

    # 4. Sentence metrics
    # Split while preserving the delimiter so we know how each sentence ended
    sentence_parts = re.split(r'([.!?…]+)', text)
    sentences = []
    sentence_terminators = []
    for i in range(0, len(sentence_parts) - 1, 2):
        s = sentence_parts[i].strip()
        if s:
            sentences.append(s)
            sentence_terminators.append(sentence_parts[i + 1])
    # Handle last part if no trailing punctuation
    if len(sentence_parts) % 2 == 1 and sentence_parts[-1].strip():
        sentences.append(sentence_parts[-1].strip())
        sentence_terminators.append("")

    if sentences:
        sent_lengths = [len(s.split()) for s in sentences]
        fp.avg_sentence_length = statistics.mean(sent_lengths)
        fp.sentence_length_variance = (
            statistics.variance(sent_lengths) if len(sent_lengths) > 1 else 0.0
        )

        # Question and exclamation ratio — check the terminator that followed each sentence
        questions = sum(1 for t in sentence_terminators if '?' in t)
        exclamations = sum(1 for t in sentence_terminators if '!' in t)
        fp.question_ratio = questions / max(len(sentences), 1)
        fp.exclamation_ratio = exclamations / max(len(sentences), 1)

    # 5. Unique word ratio
    unique_words = len(set(words))
    fp.unique_word_ratio = unique_words / max(len(words), 1)

    # 6. Function word ratio (Russian)
    func_word_count = sum(
        1 for w in words if w.rstrip('.,!?;:') in RUSSIAN_FUNCTION_WORDS
    )
    fp.function_word_ratio = func_word_count / max(len(words), 1)

    # 7. Russian informal markers (count, not ratio)
    # Use word-boundary regex to avoid false positives ("да" in "когда", "ну" in "минуту")
    fp.russian_informal_markers = sum(
        1 for marker in RUSSIAN_INFORMAL_MARKERS
        if re.search(r'(?:^|\s)' + re.escape(marker) + r'(?:\s|[.,!?;:]|$)', normalized)
    )

    # 8. Transition words
    fp.transition_word_count = sum(
        1 for trans in RUSSIAN_TRANSITION_WORDS if trans in normalized
    )

    # 9. Comma density (commas per 100 words)
    comma_count = text.count(',')
    fp.comma_density = (comma_count / max(len(words), 1)) * 100

    # 10. Paragraph structure (uniformity score, 0-1)
    paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
    if len(paragraphs) >= 2:
        para_lengths = [len(p.split()) for p in paragraphs]
        mean_para = statistics.mean(para_lengths)
        if mean_para > 0:
            para_variance = statistics.variance(para_lengths) if len(para_lengths) > 1 else 0
            # High variance = low uniformity. Cap at reasonable values.
            uniformity = max(0.0, 1.0 - (para_variance / (mean_para ** 2)) * 0.5)
            fp.paragraph_structure_score = min(1.0, uniformity)
        else:
            fp.paragraph_structure_score = 0.5
    else:
        fp.paragraph_structure_score = 0.5

    return fp


def compare_fingerprints(a: TextFingerprint, b: TextFingerprint) -> float:
    """Compare two fingerprints and return similarity (0.0-1.0).

    Higher = more similar. Uses weighted combination of all features.
    """
    if not a.char_bigram_freq and not b.char_bigram_freq:
        return 1.0  # Both empty

    if not a.char_bigram_freq or not b.char_bigram_freq:
        return 0.0  # One empty, one not

    scores = []
    weights = []

    # 1. Bigram similarity (Jaccard-like)
    if a.char_bigram_freq and b.char_bigram_freq:
        bigrams_a = set(a.char_bigram_freq.keys())
        bigrams_b = set(b.char_bigram_freq.keys())
        if bigrams_a or bigrams_b:
            jaccard = len(bigrams_a & bigrams_b) / max(len(bigrams_a | bigrams_b), 1)
            scores.append(jaccard)
            weights.append(0.2)

    # 2. Word length distribution similarity
    if a.word_length_dist and b.word_length_dist:
        all_keys = set(a.word_length_dist.keys()) | set(b.word_length_dist.keys())
        if all_keys:
            sum_abs_diff = sum(
                abs(a.word_length_dist.get(k, 0) - b.word_length_dist.get(k, 0))
                for k in all_keys
            )
            word_dist_sim = max(0.0, 1.0 - sum_abs_diff / 2)
            scores.append(word_dist_sim)
            weights.append(0.15)

    # 3. Punctuation ratio
    punct_sim = 1.0 - abs(a.punct_ratio - b.punct_ratio)
    scores.append(punct_sim)
    weights.append(0.1)

    # 4. Average sentence length
    sent_len_diff = abs(a.avg_sentence_length - b.avg_sentence_length)
    sent_len_sim = max(0.0, 1.0 - (sent_len_diff / 20.0))
    scores.append(sent_len_sim)
    weights.append(0.1)

    # 5. Sentence length variance
    sent_var_diff = abs(a.sentence_length_variance - b.sentence_length_variance)
    sent_var_sim = max(0.0, 1.0 - (sent_var_diff / 20.0))
    scores.append(sent_var_sim)
    weights.append(0.1)

    # 6. Unique word ratio
    unique_sim = 1.0 - abs(a.unique_word_ratio - b.unique_word_ratio)
    scores.append(unique_sim)
    weights.append(0.1)

    # 7. Function word ratio
    func_sim = 1.0 - abs(a.function_word_ratio - b.function_word_ratio)
    scores.append(func_sim)
    weights.append(0.08)

    # 8. Question ratio
    quest_sim = 1.0 - abs(a.question_ratio - b.question_ratio)
    scores.append(quest_sim)
    weights.append(0.07)

    # Compute weighted average
    if not scores or not weights:
        return 0.5

    total_weight = sum(weights)
    weighted_score = sum(s * w for s, w in zip(scores, weights)) / max(total_weight, 0.01)

    return max(0.0, min(1.0, weighted_score))


def detect_ai_text_markers(text: str) -> dict:
    """Detect known AI writing patterns in Russian text.

    Returns: {
        "ai_probability": 0.0-1.0,
        "markers_found": [list of detected patterns],
        "confidence": "low" | "medium" | "high"
    }
    """
    if not text or len(text.strip()) < 10:
        return {
            "ai_probability": 0.0,
            "markers_found": [],
            "confidence": "low",
        }

    normalized = text.lower()
    markers_found = []
    ai_score = 0.0

    # 1. Check for perfect structure: numbered lists (at least 2 items)
    numbered_items = re.findall(r'(?:^|\n)\s*[1-9][0-9]?\)\s+', normalized)
    if len(numbered_items) >= 2:
        markers_found.append("numbered_lists")
        ai_score += 0.15

    # 2. Check for perfect transitions (Во-первых... Во-вторых... В-третьих...)
    transitions = re.findall(r'(во-первых|во-вторых|в-третьих|в-четвёртых|в-пятых)', normalized)
    if len(transitions) >= 2:
        markers_found.append(f"structured_transitions_{len(transitions)}")
        ai_score += 0.15

    # 3. Check for absence of typos/corrections (overly formal)
    # Humans often have: двойные буквы, пропуски, etc.
    words = normalized.split()
    potential_typos = sum(
        1 for w in words
        if re.search(r'([а-я])\1{2,}', w)  # Triple letters (like "ааа")
    )
    if len(words) > 10 and potential_typos == 0:
        markers_found.append("no_typos_no_corrections")
        ai_score += 0.1

    # 4. Check for known AI phrase patterns
    ai_phrase_count = sum(
        1 for phrase in KNOWN_RUSSIAN_AI_PHRASES
        if phrase in normalized
    )
    if ai_phrase_count >= 2:
        markers_found.append(f"known_ai_phrases_{ai_phrase_count}")
        ai_score += 0.2
    elif ai_phrase_count == 1:
        markers_found.append("one_known_ai_phrase")
        ai_score += 0.08

    # 5. Check for excessive formality (no informal markers)
    informal_count = sum(
        1 for marker in RUSSIAN_INFORMAL_MARKERS
        if re.search(r'(?:^|\s)' + re.escape(marker) + r'(?:\s|[.,!?;:]|$)', normalized)
    )
    if len(words) > 15 and informal_count == 0:
        markers_found.append("zero_informal_markers")
        ai_score += 0.12

    # 6. Check for consistent sentence length (low variance)
    sentences = re.split(r'[.!?…]+\s*', normalized)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.split()) > 2]
    if len(sentences) >= 3:
        lengths = [len(s.split()) for s in sentences]
        if max(lengths) - min(lengths) <= 2:  # All very similar
            markers_found.append("uniform_sentence_length")
            ai_score += 0.15

    # 7. Check for absence of hesitation/filler words
    hesitation_markers = ["ну", "ээ", "ммм", "хм", "типа", "как бы"]
    hesitation_count = sum(
        1 for h in hesitation_markers
        if re.search(r'(?:^|\s)' + re.escape(h) + r'(?:\s|[.,!?;:]|$)', normalized)
    )
    if len(words) > 20 and hesitation_count == 0:
        markers_found.append("no_hesitation_markers")
        ai_score += 0.1

    # 8. Check for overly formal vocabulary density
    formal_words = {
        "несомненно", "безусловно", "представляется", "следует",
        "необходимо", "требуется", "надлежит", "должно", "принципиально",
    }
    formal_count = sum(1 for fw in formal_words if fw in normalized)
    if formal_count >= 3:
        markers_found.append(f"formal_vocabulary_{formal_count}")
        ai_score += 0.15

    # Cap the score
    ai_score = min(1.0, ai_score)

    # Determine confidence
    if ai_score >= 0.6:
        confidence = "high"
    elif ai_score >= 0.35:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "ai_probability": round(ai_score, 3),
        "markers_found": markers_found,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Cross-user Answer Similarity
# ---------------------------------------------------------------------------

def cross_user_answer_similarity(
    user_answers: list[str],
    other_users_answers: list[list[str]],
) -> dict:
    """Compare one user's answers against other users' answers from same match.

    Args:
        user_answers: Current user's answers
        other_users_answers: List of lists (each inner list = answers from one other user)

    Returns: {
        "suspicious_pairs": [...],  # list of (other_user_idx, answer_idx, similarity)
        "max_similarity": float,
        "flagged": bool
    }
    """
    if not user_answers:
        return {
            "suspicious_pairs": [],
            "max_similarity": 0.0,
            "flagged": False,
        }

    suspicious_pairs = []
    max_similarity = 0.0

    for other_user_idx, other_answers in enumerate(other_users_answers):
        for user_ans_idx, user_ans in enumerate(user_answers):
            for other_ans_idx, other_ans in enumerate(other_answers):
                # Skip trivial answers (< 20 words)
                if len(user_ans.split()) < 20 or len(other_ans.split()) < 20:
                    continue

                # Compute character n-gram similarity (not just word Jaccard)
                similarity = _ngramm_similarity(user_ans, other_ans, n=3)

                if similarity > 0.7:  # High similarity on non-trivial answers
                    suspicious_pairs.append({
                        "other_user_idx": other_user_idx,
                        "user_answer_idx": user_ans_idx,
                        "other_answer_idx": other_ans_idx,
                        "similarity": round(similarity, 3),
                    })

                max_similarity = max(max_similarity, similarity)

    flagged = len(suspicious_pairs) > 0 and max_similarity > 0.7

    return {
        "suspicious_pairs": suspicious_pairs[:10],  # Limit output
        "max_similarity": round(max_similarity, 3),
        "flagged": flagged,
    }


def _ngramm_similarity(text1: str, text2: str, n: int = 3) -> float:
    """Compute n-gram based similarity between two texts (0.0-1.0)."""
    def get_ngrams(text: str, n: int) -> set[str]:
        text_clean = re.sub(r'\s+', '', text.lower())
        return {text_clean[i:i+n] for i in range(len(text_clean) - n + 1)}

    ngrams1 = get_ngrams(text1, n)
    ngrams2 = get_ngrams(text2, n)

    if not ngrams1 or not ngrams2:
        return 0.0

    intersection = len(ngrams1 & ngrams2)
    union = len(ngrams1 | ngrams2)

    return intersection / max(union, 1)


# ---------------------------------------------------------------------------
# Typing Dynamics Analysis
# ---------------------------------------------------------------------------

def analyze_typing_dynamics(events: list[dict]) -> dict:
    """Analyze keystroke timing data.

    Each event should have:
    - timestamp_ms: int
    - text_length: int
    - action: "start" | "keystroke" | "submit"

    Returns: {
        "typing_speed_cpm": float,  # chars per minute
        "speed_variance": float,
        "pause_count": int,
        "suspicious": bool,
        "confidence": float,
    }
    """
    if not events or len(events) < 2:
        return {
            "typing_speed_cpm": 0.0,
            "speed_variance": 0.0,
            "pause_count": 0,
            "suspicious": False,
            "confidence": 0.0,
        }

    # Sort by timestamp
    sorted_events = sorted(events, key=lambda e: e.get("timestamp_ms", 0))

    # Compute inter-keystroke intervals (IKI)
    ikis = []
    text_lengths = []

    for i in range(1, len(sorted_events)):
        prev = sorted_events[i - 1]
        curr = sorted_events[i]

        if curr.get("action") not in ("keystroke", "submit"):
            continue

        iki = curr.get("timestamp_ms", 0) - prev.get("timestamp_ms", 0)
        if 0 < iki < 5000:  # Reasonable bounds (0-5s)
            ikis.append(iki)
            text_lengths.append(curr.get("text_length", 0))

    if not ikis:
        return {
            "typing_speed_cpm": 0.0,
            "speed_variance": 0.0,
            "pause_count": 0,
            "suspicious": False,
            "confidence": 0.0,
        }

    # Compute typing speed: chars per minute
    total_time_ms = sum(ikis)
    total_chars = sum(text_lengths)
    total_time_min = total_time_ms / 60000.0

    typing_speed_cpm = total_chars / max(total_time_min, 0.01) if total_time_min > 0 else 0.0

    # Compute speed variance
    speed_variance = (
        statistics.variance(ikis) if len(ikis) > 1 else 0.0
    ) ** 0.5  # Standard deviation

    # Count pauses (IKI > 2 seconds)
    pause_count = sum(1 for iki in ikis if iki > 2000)

    # Detection logic
    suspicious = False
    confidence = 0.0

    # Flag if perfectly consistent (< 5% variance)
    if typing_speed_cpm > 0 and ikis:
        cv = speed_variance / (sum(ikis) / len(ikis)) if ikis else 0
        if cv < 0.05:  # Very low variance
            suspicious = True
            confidence = 0.8

    # Flag if impossibly fast (> 600 chars/min = 10 chars/sec)
    if typing_speed_cpm > 600:
        suspicious = True
        confidence = 0.9

    return {
        "typing_speed_cpm": round(typing_speed_cpm, 1),
        "speed_variance": round(speed_variance, 1),
        "pause_count": pause_count,
        "suspicious": suspicious,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Real-time Check (lightweight, for immediate feedback)
# ---------------------------------------------------------------------------

def real_time_check(
    answer_text: str,
    response_time_ms: Optional[int] = None,
    question_text: str = "",
    user_history: Optional[list[dict]] = None,
) -> dict:
    """Lightweight real-time check during PvP match.

    This check is designed to be fast and non-blocking.

    Args:
        answer_text: User's answer
        response_time_ms: Time taken to answer (in milliseconds)
        question_text: The question being answered
        user_history: List of user's past responses (for style consistency)

    Returns: {
        "risk_level": "low" | "medium" | "high",
        "flags": [...],
        "should_flag_for_review": bool,
    }
    """
    flags = []
    risk_score = 0.0

    if not answer_text or len(answer_text.strip()) < 3:
        return {
            "risk_level": "low",
            "flags": [],
            "should_flag_for_review": False,
        }

    # 1. Quick AI marker check
    ai_check = detect_ai_text_markers(answer_text)
    if ai_check["ai_probability"] >= 0.5:
        flags.append("ai_markers_detected")
        risk_score += 0.3

    # 2. Answer length vs response time
    # Fast responses to long answers are suspicious
    if response_time_ms is not None and response_time_ms > 0:
        answer_len = len(answer_text)
        # Rough heuristic: humans type ~5-8 chars per second, think 1-2 seconds
        min_time_ms = (answer_len / 8.0) * 1000 + 1000  # Chars/second + min think time
        if response_time_ms < min_time_ms * 0.6:  # 40% faster than expected
            flags.append("suspiciously_fast_response")
            risk_score += 0.25

    # 3. Consistency with user history (if provided)
    if user_history and len(user_history) >= 2:
        # Build fingerprint of answer
        current_fp = compute_text_fingerprint(answer_text)

        # Compare to historical average
        historical_fps = [
            compute_text_fingerprint(h.get("text", ""))
            for h in user_history[-5:]  # Last 5 answers
        ]

        if historical_fps:
            similarities = [
                compare_fingerprints(current_fp, hfp)
                for hfp in historical_fps
            ]
            avg_similarity = statistics.mean(similarities)

            # Sudden style change
            if avg_similarity < 0.4:
                flags.append("unusual_writing_style")
                risk_score += 0.2

            # Perfect mimicry of historical style (too consistent)
            if all(s > 0.95 for s in similarities) and len(similarities) >= 3:
                flags.append("too_consistent_style")
                risk_score += 0.15

    # 4. Excessive formality in casual context
    if question_text and "банкротство" not in question_text.lower():
        # Non-legal question with overly formal answer
        formal_words = {
            "несомненно", "безусловно", "представляется", "следует",
        }
        formal_count = sum(1 for fw in formal_words if fw in answer_text.lower())
        if formal_count >= 2:
            flags.append("excessive_formality")
            risk_score += 0.15

    # Determine risk level
    risk_score = min(1.0, risk_score)

    if risk_score >= 0.6:
        risk_level = "high"
    elif risk_score >= 0.35:
        risk_level = "medium"
    else:
        risk_level = "low"

    should_flag = risk_level in ("high", "medium") and len(flags) >= 2

    return {
        "risk_level": risk_level,
        "flags": flags,
        "should_flag_for_review": should_flag,
    }
