"""Anti-cheat system for PvP duels (Agent 8 — PvP Battle).

3-level detection + extensions:

Level 1 — Statistical:
  Score deviation analysis, unnatural win streaks, anomalous accuracy.
  Action: flag for review, increase monitoring.

Level 2 — Behavioral:
  ML pattern analysis — scripts, auto-responses, copy-paste detection.
  Action: temporary ban (24h), manual review.

Level 3 — AI Detector + Extensions:
  - Text perplexity + burstiness (one signal, not sole decider)
  - Latency analysis: median response < 3s at length > 50 words = red flag
  - Semantic consistency: vocabulary complexity jump detection
  Action: flag + rating freeze + manual review (NO auto-disqualification).

Prize Protection:
  - KYC: identity verification before payout
  - 72h payout delay: anti-cheat review period
  - Hidden metrics: players don't know exact scoring formula
  - Immutable audit log
  - Multi-account detection: fingerprint + IP + behavioral
"""

import logging
import math
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pvp import (
    AntiCheatLog,
    AntiCheatCheckType,
    AntiCheatAction,
    PvPDuel,
    DuelStatus,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Level 1: Statistical
MAX_WINSTREAK_BEFORE_FLAG = 12      # Flag if streak > 12
SCORE_DEVIATION_THRESHOLD = 2.5     # Standard deviations from mean
MIN_DUELS_FOR_STATS = 5             # Need at least 5 duels for analysis

# Level 2: Behavioral
COPY_PASTE_SIMILARITY_THRESHOLD = 0.85  # Jaccard similarity between responses
MIN_UNIQUE_RESPONSE_RATIO = 0.6         # At least 60% unique responses
SLIDING_WINDOW_SIZE = 5                 # S3-08: Compare against last N messages

# Level 3: AI Detection
PERPLEXITY_THRESHOLD = 35.0         # Low perplexity = likely AI-generated (recalibrated)
BURSTINESS_THRESHOLD = 0.3         # Low burstiness = likely AI
MEDIAN_RESPONSE_TIME_MIN = 3.0     # Seconds — faster = suspicious
RESPONSE_LENGTH_FOR_LATENCY = 50   # Words — only flag if response is long
VOCAB_COMPLEXITY_JUMP = 2.0        # Std dev jump in vocabulary complexity


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AntiCheatSignal:
    """Single anti-cheat detection signal."""
    check_type: AntiCheatCheckType
    score: float            # 0.0-1.0 confidence
    flagged: bool
    details: dict = field(default_factory=dict)


@dataclass
class AntiCheatResult:
    """Aggregated anti-cheat result for a player in a duel."""
    user_id: uuid.UUID
    duel_id: uuid.UUID
    signals: list[AntiCheatSignal] = field(default_factory=list)
    overall_flagged: bool = False
    recommended_action: AntiCheatAction = AntiCheatAction.none

    @property
    def max_score(self) -> float:
        return max((s.score for s in self.signals), default=0.0)

    @property
    def flagged_signals(self) -> list[AntiCheatSignal]:
        return [s for s in self.signals if s.flagged]


# ---------------------------------------------------------------------------
# Level 1: Statistical Analysis
# ---------------------------------------------------------------------------

async def check_statistical(
    user_id: uuid.UUID,
    duel_id: uuid.UUID,
    db: AsyncSession,
) -> AntiCheatSignal:
    """Analyze player's score history for anomalies.

    Checks:
    - Unnatural win streaks (> 12)
    - Score deviation from personal mean (> 2.5σ)
    - Anomalous win rate in recent N games
    """
    # Get recent duels for this user
    stmt = (
        select(PvPDuel)
        .where(
            PvPDuel.status == DuelStatus.completed,
            (PvPDuel.player1_id == user_id) | (PvPDuel.player2_id == user_id),
        )
        .order_by(PvPDuel.completed_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    duels = result.scalars().all()

    if len(duels) < MIN_DUELS_FOR_STATS:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.statistical,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_data", "duels": len(duels)},
        )

    # Calculate scores and streaks
    scores = []
    wins = 0
    current_streak = 0
    max_streak = 0

    for d in duels:
        is_p1 = d.player1_id == user_id
        player_score = d.player1_total if is_p1 else d.player2_total
        won = d.winner_id == user_id

        scores.append(player_score)
        if won:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
            wins += 1
        else:
            current_streak = 0

    mean_score = statistics.mean(scores)
    stdev = statistics.stdev(scores) if len(scores) > 1 else 10.0
    win_rate = wins / len(duels)

    # Anomaly score (0.0-1.0)
    anomaly_score = 0.0
    flags = []

    # Win streak check
    if max_streak > MAX_WINSTREAK_BEFORE_FLAG:
        anomaly_score += 0.4
        flags.append(f"win_streak={max_streak}")

    # Win rate anomaly (> 85% over 20+ games)
    if len(duels) >= 20 and win_rate > 0.85:
        anomaly_score += 0.3
        flags.append(f"win_rate={win_rate:.2f}")

    # Latest score deviation
    if stdev > 0 and scores:
        latest_z = abs(scores[0] - mean_score) / stdev
        if latest_z > SCORE_DEVIATION_THRESHOLD:
            anomaly_score += 0.3
            flags.append(f"score_z={latest_z:.2f}")

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.5

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.statistical,
        score=anomaly_score,
        flagged=flagged,
        details={
            "max_streak": max_streak,
            "win_rate": round(win_rate, 3),
            "mean_score": round(mean_score, 1),
            "stdev": round(stdev, 1),
            "flags": flags,
        },
    )


# ---------------------------------------------------------------------------
# Level 2: Behavioral Analysis
# ---------------------------------------------------------------------------

def _jaccard_similarity(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two strings."""
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def check_behavioral(
    messages: list[dict],
    user_id: uuid.UUID,
) -> AntiCheatSignal:
    """Analyze message patterns for scripted/automated behavior.

    S3-08: Sliding window of last 5 messages instead of single-predecessor
    comparison. Detects A,B,A,B alternation patterns that evade pairwise checks.

    Checks:
    1. Sliding window similarity: each message vs. last 5 predecessors
    2. Response template patterns (fill-in-the-blank style)
    3. Unnatural response timing + length combo
    """
    user_msgs = [m for m in messages if m.get("sender_id") == str(user_id)]

    if len(user_msgs) < 3:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.behavioral,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_messages"},
        )

    texts = [m.get("text", "") for m in user_msgs]
    anomaly_score = 0.0
    flags = []

    # S3-08: Sliding window similarity (last SLIDING_WINDOW_SIZE messages)
    # For each message, compare against the previous N messages.
    # This catches A,B,A,B patterns where A-vs-B is low but A-vs-A is high.
    window_hits = 0
    window_checks = 0
    for i in range(1, len(texts)):
        window_start = max(0, i - SLIDING_WINDOW_SIZE)
        for j in range(window_start, i):
            sim = _jaccard_similarity(texts[i], texts[j])
            window_checks += 1
            if sim > COPY_PASTE_SIMILARITY_THRESHOLD:
                window_hits += 1

    if window_checks > 0:
        sim_ratio = window_hits / window_checks
        if sim_ratio > 0.2:  # Lower threshold because window is more focused
            anomaly_score += 0.5
            flags.append(f"sliding_window_sim={sim_ratio:.2f}")

    # Unique response ratio
    unique_count = len(set(texts))
    unique_ratio = unique_count / len(texts)
    if unique_ratio < MIN_UNIQUE_RESPONSE_RATIO:
        anomaly_score += 0.3
        flags.append(f"unique_ratio={unique_ratio:.2f}")

    # Response length variance (bots tend to have uniform length)
    lengths = [len(t.split()) for t in texts if t]
    if len(lengths) >= 3:
        mean_len = statistics.mean(lengths)
        length_cv = (statistics.stdev(lengths) / mean_len) if mean_len > 0 else 0
        if length_cv < 0.15:  # Very uniform = suspicious
            anomaly_score += 0.2
            flags.append(f"length_cv={length_cv:.3f}")

    # S3-08: Latency + response length combo detection
    # If user responds suspiciously fast with long messages → likely copy-paste
    latencies = []
    for msg in user_msgs:
        latency = msg.get("latency_ms") or msg.get("response_time_ms")
        if latency is not None:
            latencies.append(float(latency))
    if latencies and lengths:
        # Fast responses (< 3s) with long text (> 50 words) = suspicious
        fast_long = sum(
            1 for lat, wc in zip(latencies, lengths)
            if lat < MEDIAN_RESPONSE_TIME_MIN * 1000 and wc > RESPONSE_LENGTH_FOR_LATENCY
        )
        if fast_long >= 2:
            anomaly_score += 0.3
            flags.append(f"fast_long_responses={fast_long}")

        # S4-10: Words-per-second analysis — catches sleep(3.1) bypass
        # Even if response time > 3s, check if wps is superhuman
        high_wps_count = 0
        for lat, wc in zip(latencies, lengths):
            if lat > 0 and wc >= 10:
                wps = wc / (lat / 1000.0)
                if wps > 15.0:  # >15 words/sec = impossible for human
                    high_wps_count += 1
        if high_wps_count >= 2:
            anomaly_score += 0.3
            flags.append(f"high_wps_responses={high_wps_count}")

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.5

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.behavioral,
        score=anomaly_score,
        flagged=flagged,
        details={
            "message_count": len(user_msgs),
            "window_hits": window_hits,
            "window_checks": window_checks,
            "unique_ratio": round(unique_ratio, 3),
            "flags": flags,
        },
    )


# ---------------------------------------------------------------------------
# Level 3: AI Detection + Latency + Semantic
# ---------------------------------------------------------------------------

def _estimate_perplexity(text: str) -> float:
    """Rough perplexity proxy based on multiple linguistic signals.

    Real implementation would use a language model. This heuristic combines:
    1. Type-token ratio (TTR) — AI text tends to have HIGH TTR (varied vocabulary)
    2. Average sentence length uniformity — AI tends to produce uniform sentences
    3. Punctuation diversity — humans use more varied punctuation in informal chat

    Lower return value = more likely AI. Range roughly 5-100.
    """
    words = text.lower().split()
    if len(words) < 10:
        return 50.0  # Not enough text, assume human

    unique = set(words)
    ttr = len(unique) / len(words)

    # Signal 1: HIGH TTR in conversational context = suspicious (AI uses varied vocab)
    # Humans in casual chat repeat words: "да", "ну", "это", "я", etc.
    # Typical human chat TTR: 0.3-0.5; AI text TTR: 0.6-0.85
    ttr_signal = ttr  # Higher = more AI-like

    # Signal 2: Sentence length uniformity (low variance = AI)
    import re as _re
    sentences = _re.split(r"[.!?…]+\s*", text)
    sentences = [s for s in sentences if len(s.split()) >= 2]
    if len(sentences) >= 3:
        lengths = [len(s.split()) for s in sentences]
        mean_len = sum(lengths) / len(lengths)
        variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
        cv = (variance ** 0.5) / mean_len if mean_len > 0 else 0
        # Low CV = uniform = AI-like
        uniformity_signal = max(0.0, 1.0 - cv)  # Higher = more AI-like
    else:
        uniformity_signal = 0.5

    # Signal 3: Absence of informal markers (typos, filler words, emoji)
    informal_markers = [
        "ну", "ага", "типа", "короче", "блин", "ой", "ааа", "ммм",
        "хз", "лол", "кек", "ваще", "чё", "щас", "норм", "ок",
        "...", ")", "(", "!!", "??",
    ]
    informal_count = sum(1 for m in informal_markers if m in text.lower())
    # More informal markers = more human
    formality_signal = max(0.0, 1.0 - informal_count * 0.15)  # Higher = more formal = AI-like

    # Combine signals: weighted average
    ai_likeness = (
        ttr_signal * 0.45 +
        uniformity_signal * 0.30 +
        formality_signal * 0.25
    )

    # Map to perplexity-like scale: low = AI, high = human
    # ai_likeness ~0.3-0.4 → human → perplexity ~60-80
    # ai_likeness ~0.6-0.8 → AI → perplexity ~10-25
    estimated = 100.0 * (1.0 - ai_likeness)
    return max(5.0, min(100.0, estimated))


def _estimate_burstiness(response_times: list[float]) -> float:
    """Burstiness of response timing. Low = robotic, high = human.

    Burstiness B = (σ - μ) / (σ + μ), range [-1, 1].
    Humans: B > 0 (irregular timing). Bots: B ≈ 0 or < 0 (regular).
    """
    if len(response_times) < 3:
        return 0.5  # Neutral

    mu = statistics.mean(response_times)
    sigma = statistics.stdev(response_times)

    if mu + sigma == 0:
        return 0.0

    return (sigma - mu) / (sigma + mu)


def check_ai_detector(
    messages: list[dict],
    user_id: uuid.UUID,
) -> AntiCheatSignal:
    """Detect AI-generated responses during PvP.

    Combines:
    - Text perplexity estimate (low = AI)
    - Response burstiness (regular timing = AI)
    - Latency analysis (fast + long = AI)
    """
    user_msgs = [m for m in messages if m.get("sender_id") == str(user_id)]

    if len(user_msgs) < 5:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.ai_detector,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_messages"},
        )

    anomaly_score = 0.0
    flags = []

    # Perplexity check
    all_text = " ".join(m.get("text", "") for m in user_msgs)
    perplexity = _estimate_perplexity(all_text)
    if perplexity < PERPLEXITY_THRESHOLD:
        anomaly_score += 0.25
        flags.append(f"low_perplexity={perplexity:.1f}")

    # Burstiness check
    response_times = []
    for m in user_msgs:
        rt = m.get("response_time")
        if rt is not None:
            response_times.append(float(rt))

    if response_times:
        burstiness = _estimate_burstiness(response_times)
        if burstiness < BURSTINESS_THRESHOLD:
            anomaly_score += 0.25
            flags.append(f"low_burstiness={burstiness:.3f}")

    # Latency analysis: fast responses to long texts
    fast_long_count = 0
    for m in user_msgs:
        rt = m.get("response_time")
        text = m.get("text", "")
        word_count = len(text.split())
        if rt is not None and rt < MEDIAN_RESPONSE_TIME_MIN and word_count > RESPONSE_LENGTH_FOR_LATENCY:
            fast_long_count += 1

    if fast_long_count >= 3:
        anomaly_score += 0.3
        flags.append(f"fast_long_responses={fast_long_count}")

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.5

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.ai_detector,
        score=anomaly_score,
        flagged=flagged,
        details={
            "perplexity": round(perplexity, 1),
            "burstiness": round(_estimate_burstiness(response_times), 3) if response_times else None,
            "fast_long_count": fast_long_count,
            "flags": flags,
        },
    )


def check_semantic_consistency(
    current_messages: list[dict],
    historical_vocab_complexity: float | None,
    user_id: uuid.UUID,
) -> AntiCheatSignal:
    """Detect sudden jumps in legal vocabulary complexity.

    Compares current session's vocabulary level to player's historical average.
    A sudden jump (> 2σ) suggests external assistance.
    """
    user_msgs = [
        m.get("text", "")
        for m in current_messages
        if m.get("sender_id") == str(user_id)
    ]

    if len(user_msgs) < 3 or historical_vocab_complexity is None:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.semantic,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_data"},
        )

    # Simple vocabulary complexity: avg word length + unique legal terms ratio
    all_text = " ".join(user_msgs)
    words = all_text.lower().split()

    if not words:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.semantic,
            score=0.0,
            flagged=False,
        )

    # Legal terms (sample — would be loaded from DB in production)
    legal_terms = {
        "банкротство", "арбитражный", "конкурсный", "реструктуризация",
        "кредитор", "должник", "финансовый", "управляющий", "реестр",
        "требований", "субсидиарная", "ответственность", "мораторий",
        "реализация", "имущество", "процедура", "несостоятельность",
    }

    avg_word_length = sum(len(w) for w in words) / len(words)
    legal_ratio = sum(1 for w in words if w in legal_terms) / len(words)
    current_complexity = avg_word_length * 2 + legal_ratio * 100

    deviation = abs(current_complexity - historical_vocab_complexity)

    flagged = deviation > VOCAB_COMPLEXITY_JUMP * 10  # Scaled threshold
    score = min(1.0, deviation / (VOCAB_COMPLEXITY_JUMP * 20))

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.semantic,
        score=score,
        flagged=flagged,
        details={
            "current_complexity": round(current_complexity, 2),
            "historical_complexity": round(historical_vocab_complexity, 2),
            "deviation": round(deviation, 2),
        },
    )


# ---------------------------------------------------------------------------
# Level 3++: LLM Perplexity Scoring
# ---------------------------------------------------------------------------

LLM_PERPLEXITY_LOW_THRESHOLD = 0.25  # Below this = very likely AI
LLM_PERPLEXITY_MED_THRESHOLD = 0.45  # Below this = suspicious


async def check_llm_perplexity(
    messages: list[dict],
    user_id: uuid.UUID,
) -> AntiCheatSignal:
    """Use LLM to score how likely user messages are AI-generated.

    Sends a sample of user messages to the LLM and asks it to estimate
    the probability of AI authorship based on stylistic markers:
    - Unnaturally perfect grammar in informal context
    - Absence of typos, hedging, filler words
    - Homogeneous sentence structure
    - Over-structured arguments (numbered lists, perfect transitions)
    - Legal terminology density inconsistent with conversational context

    Returns a score from 0 (definitely human) to 1 (definitely AI).
    """
    from app.services.llm import generate_response

    user_msgs = [m.get("text", "") for m in messages if m.get("sender_id") == str(user_id)]
    if len(user_msgs) < 3:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.llm_perplexity,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_messages"},
        )

    # Sample up to 8 messages for analysis (avoid sending entire conversation)
    sample = user_msgs[:8]
    sample_text = "\n---\n".join(f"[Сообщение {i+1}]: {msg}" for i, msg in enumerate(sample))

    prompt = (
        "Ты — детектор AI-текстов на русском языке. "
        "Проанализируй следующие сообщения пользователя из тренировочного чата по банкротству (127-ФЗ). "
        "Определи вероятность того, что эти сообщения написаны AI (ChatGPT, Claude и т.п.), а не человеком.\n\n"
        "Признаки AI:\n"
        "- Идеальная грамматика в неформальном контексте\n"
        "- Отсутствие опечаток, разговорных слов, пауз\n"
        "- Однородная структура предложений\n"
        "- Нумерованные списки, идеальные переходы\n"
        "- Слишком равномерная длина ответов\n"
        "- Чрезмерно формальный стиль для устного диалога\n\n"
        "Признаки человека:\n"
        "- Опечатки, сокращения, эмоциональные выбросы\n"
        "- Неравномерные ответы (то короткие, то длинные)\n"
        "- Разговорный стиль, жаргон\n"
        "- Незавершённые мысли, самоправки\n\n"
        f"Сообщения пользователя:\n{sample_text}\n\n"
        "Ответь ТОЛЬКО одним числом от 0.0 до 1.0 — вероятность AI. "
        "Ничего больше. Только число."
    )

    try:
        # generate_response returns LLMResponse (not str)
        # and does NOT accept temperature/max_tokens params
        llm_result = await generate_response(
            system_prompt="Ты детектор AI-текстов. Отвечай только числом 0.0-1.0.",
            messages=[{"role": "user", "content": prompt}],
            emotion_state="cold",
            task_type="simple",
            prefer_provider="local",
        )
        # Extract text content from LLMResponse object
        response_text = llm_result.content.strip()
        # Parse the score
        cleaned = response_text.replace(",", ".")
        # Extract first float-like token
        ai_score = 0.5  # Default
        for token in cleaned.split():
            try:
                ai_score = float(token)
                ai_score = max(0.0, min(1.0, ai_score))
                break
            except ValueError:
                continue
    except Exception as e:
        logger.warning("LLM perplexity check failed: %s", e)
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.llm_perplexity,
            score=0.0,
            flagged=False,
            details={"reason": "llm_call_failed", "error": str(e)},
        )

    flagged = ai_score >= LLM_PERPLEXITY_MED_THRESHOLD
    confidence = "high" if ai_score >= LLM_PERPLEXITY_LOW_THRESHOLD * 2 else "medium" if flagged else "low"

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.llm_perplexity,
        score=ai_score,
        flagged=flagged,
        details={
            "ai_probability": round(ai_score, 3),
            "confidence": confidence,
            "sample_count": len(sample),
        },
    )


# ---------------------------------------------------------------------------
# Level 4: Multi-Account Detection
# ---------------------------------------------------------------------------

MULTI_ACCOUNT_SHARED_IP_THRESHOLD = 3   # 3+ accounts from same IP = flag
MULTI_ACCOUNT_SHARED_UA_THRESHOLD = 2   # 2+ accounts same rare UA = flag


async def record_fingerprint(
    user_id: uuid.UUID,
    ip_address: str | None,
    user_agent: str | None,
    browser_fingerprint: str | None = None,
    event_type: str = "login",
    session_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
) -> None:
    """Record a device/network fingerprint for multi-account detection."""
    if db is None:
        return

    import hashlib

    ua_hash = None
    if user_agent:
        # Normalize: lowercase, strip version numbers for grouping
        normalized = user_agent.lower().strip()
        ua_hash = hashlib.sha256(normalized.encode()).hexdigest()[:32]

    from app.models.pvp import UserFingerprint

    fp = UserFingerprint(
        user_id=user_id,
        ip_address=ip_address,
        user_agent=user_agent[:500] if user_agent else None,
        ua_hash=ua_hash,
        browser_fingerprint=browser_fingerprint,
        session_id=session_id,
        event_type=event_type,
    )
    db.add(fp)
    await db.flush()


async def check_multi_account(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AntiCheatSignal:
    """Detect potential multi-account abuse.

    Checks:
    1. IP sharing: how many distinct users share the same IPs as this user
    2. UA sharing: how many distinct users share the same rare User-Agent hash
    3. Browser fingerprint overlap: same JS fingerprint across accounts

    Returns a signal with details on shared accounts.
    """
    from app.models.pvp import UserFingerprint

    # Get this user's fingerprints
    user_fps = await db.execute(
        select(UserFingerprint.ip_address, UserFingerprint.ua_hash, UserFingerprint.browser_fingerprint)
        .where(UserFingerprint.user_id == user_id)
        .order_by(UserFingerprint.created_at.desc())
        .limit(50)
    )
    fps = user_fps.all()

    if not fps:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.multi_account,
            score=0.0,
            flagged=False,
            details={"reason": "no_fingerprints"},
        )

    user_ips = {fp[0] for fp in fps if fp[0]}
    user_ua_hashes = {fp[1] for fp in fps if fp[1]}
    user_browser_fps = {fp[2] for fp in fps if fp[2]}

    anomaly_score = 0.0
    flags = []
    shared_accounts: set[str] = set()

    # Check IP sharing
    if user_ips:
        ip_result = await db.execute(
            select(
                UserFingerprint.user_id,
                sa_func.count(UserFingerprint.id).label("cnt"),
            )
            .where(
                UserFingerprint.ip_address.in_(user_ips),
                UserFingerprint.user_id != user_id,
            )
            .group_by(UserFingerprint.user_id)
        )
        ip_shared = ip_result.all()
        unique_ip_users = len(ip_shared)

        if unique_ip_users >= MULTI_ACCOUNT_SHARED_IP_THRESHOLD:
            anomaly_score += 0.4
            flags.append(f"shared_ip_users={unique_ip_users}")
            for row in ip_shared:
                shared_accounts.add(str(row[0]))
        elif unique_ip_users >= 2:
            anomaly_score += 0.15
            flags.append(f"shared_ip_users={unique_ip_users}")

    # Check UA hash sharing (more specific than IP)
    if user_ua_hashes:
        ua_result = await db.execute(
            select(
                UserFingerprint.user_id,
                sa_func.count(UserFingerprint.id).label("cnt"),
            )
            .where(
                UserFingerprint.ua_hash.in_(user_ua_hashes),
                UserFingerprint.user_id != user_id,
            )
            .group_by(UserFingerprint.user_id)
        )
        ua_shared = ua_result.all()
        unique_ua_users = len(ua_shared)

        if unique_ua_users >= MULTI_ACCOUNT_SHARED_UA_THRESHOLD:
            anomaly_score += 0.3
            flags.append(f"shared_ua_users={unique_ua_users}")
            for row in ua_shared:
                shared_accounts.add(str(row[0]))

    # Check browser fingerprint sharing (most specific)
    if user_browser_fps:
        bf_result = await db.execute(
            select(
                UserFingerprint.user_id,
                sa_func.count(UserFingerprint.id).label("cnt"),
            )
            .where(
                UserFingerprint.browser_fingerprint.in_(user_browser_fps),
                UserFingerprint.user_id != user_id,
            )
            .group_by(UserFingerprint.user_id)
        )
        bf_shared = bf_result.all()

        if bf_shared:
            anomaly_score += 0.5
            flags.append(f"shared_browser_fp_users={len(bf_shared)}")
            for row in bf_shared:
                shared_accounts.add(str(row[0]))

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.4

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.multi_account,
        score=anomaly_score,
        flagged=flagged,
        details={
            "shared_accounts": list(shared_accounts)[:10],  # Limit for privacy
            "shared_account_count": len(shared_accounts),
            "user_ips_count": len(user_ips),
            "flags": flags,
        },
    )


# ---------------------------------------------------------------------------
# Aggregated check
# ---------------------------------------------------------------------------

async def run_anti_cheat(
    user_id: uuid.UUID,
    duel_id: uuid.UUID,
    messages: list[dict],
    db: AsyncSession,
    historical_vocab_complexity: float | None = None,
    run_llm_check: bool = False,
) -> AntiCheatResult:
    """Run all anti-cheat checks for a player in a duel.

    Args:
        run_llm_check: If True, also runs the LLM-based perplexity check.
            This is expensive (LLM call), so only use for tournaments and
            flagged players.

    Returns aggregated result with recommended action.
    """
    result = AntiCheatResult(user_id=user_id, duel_id=duel_id)

    # Level 1: Statistical
    stat_signal = await check_statistical(user_id, duel_id, db)
    result.signals.append(stat_signal)

    # Level 2: Behavioral
    behav_signal = check_behavioral(messages, user_id)
    result.signals.append(behav_signal)

    # Level 3: AI Detection (heuristic)
    ai_signal = check_ai_detector(messages, user_id)
    result.signals.append(ai_signal)

    # Level 3+: Semantic consistency
    sem_signal = check_semantic_consistency(
        messages, historical_vocab_complexity, user_id
    )
    result.signals.append(sem_signal)

    # Level 3++: Advanced NLP Analysis (fingerprinting + AI markers)
    try:
        nlp_signal = await check_nlp_advanced(messages, user_id, duel_id, db)
        result.signals.append(nlp_signal)
    except Exception as e:
        logger.warning("NLP advanced check error: %s", e)

    # Level 3+++: LLM Perplexity (optional, expensive)
    if run_llm_check or ai_signal.flagged:
        # Run LLM check if explicitly requested OR if heuristic AI detector flagged
        try:
            llm_signal = await check_llm_perplexity(messages, user_id)
            result.signals.append(llm_signal)
        except Exception as e:
            logger.warning("LLM perplexity check error: %s", e)

    # Level 4: Multi-account detection
    try:
        multi_signal = await check_multi_account(user_id, db)
        result.signals.append(multi_signal)
    except Exception as e:
        logger.warning("Multi-account check error: %s", e)

    # Determine overall flag and action
    flagged_count = len(result.flagged_signals)
    result.overall_flagged = flagged_count > 0

    # Check for high-severity signals
    has_multi_account = any(
        s.check_type == AntiCheatCheckType.multi_account and s.flagged
        for s in result.signals
    )
    has_llm_flag = any(
        s.check_type == AntiCheatCheckType.llm_perplexity and s.flagged
        for s in result.signals
    )

    if flagged_count == 0:
        result.recommended_action = AntiCheatAction.none
    elif has_multi_account and flagged_count >= 2:
        # Multi-account + another flag = serious
        result.recommended_action = AntiCheatAction.rating_freeze
    elif has_llm_flag and flagged_count >= 2:
        # LLM confirmed AI + another flag = rating freeze
        result.recommended_action = AntiCheatAction.rating_freeze
    elif flagged_count == 1:
        result.recommended_action = AntiCheatAction.flag_review
    elif flagged_count == 2:
        result.recommended_action = AntiCheatAction.rating_freeze
    else:
        # 3+ signals flagged — serious, but still manual review
        result.recommended_action = AntiCheatAction.rating_freeze

    return result


# ---------------------------------------------------------------------------
# Level 3++: Advanced NLP Analysis
# ---------------------------------------------------------------------------

async def check_nlp_advanced(
    messages: list[dict],
    user_id: uuid.UUID,
    duel_id: uuid.UUID,
    db: AsyncSession,
) -> AntiCheatSignal:
    """Level 3+: Advanced NLP analysis using text fingerprinting.

    Performs:
    1. Text fingerprinting (linguistic features)
    2. Comparison against user's historical fingerprint
    3. AI text marker detection (Russian-specific)
    4. Cross-user answer similarity
    5. Aggregation into single signal

    This check is non-blocking and catches sophisticated AI usage.
    """
    try:
        from app.services.nlp_cheat_detector import (
            compute_text_fingerprint,
            compare_fingerprints,
            detect_ai_text_markers,
            cross_user_answer_similarity,
        )
    except ImportError:
        logger.warning("NLP cheat detector module not available")
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.ai_detector,
            score=0.0,
            flagged=False,
            details={"reason": "nlp_module_unavailable"},
        )

    user_msgs = [m for m in messages if m.get("sender_id") == str(user_id)]

    if len(user_msgs) < 2:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.ai_detector,
            score=0.0,
            flagged=False,
            details={"reason": "insufficient_messages", "message_count": len(user_msgs)},
        )

    anomaly_score = 0.0
    flags = []

    # 1. Build current fingerprint
    current_text = " ".join(m.get("text", "") for m in user_msgs)
    current_fp = compute_text_fingerprint(current_text)

    if not current_fp.char_bigram_freq:
        return AntiCheatSignal(
            check_type=AntiCheatCheckType.ai_detector,
            score=0.0,
            flagged=False,
            details={"reason": "empty_fingerprint"},
        )

    # 2. Compare to historical fingerprint (if available)
    try:
        from app.models.pvp import PvPDuel

        # Get previous duels by this user
        stmt = (
            select(PvPDuel)
            .where(
                PvPDuel.status == DuelStatus.completed,
                (PvPDuel.player1_id == user_id) | (PvPDuel.player2_id == user_id),
                PvPDuel.id != duel_id,
            )
            .order_by(PvPDuel.completed_at.desc())
            .limit(5)
        )
        result = await db.execute(stmt)
        previous_duels = result.scalars().all()

        if previous_duels:
            # Extract text from round_data JSONB and compare fingerprints
            historical_texts = []
            for d in previous_duels:
                for rd in (d.round_1_data, d.round_2_data):
                    if rd and isinstance(rd, dict):
                        # Extract seller/client messages if stored
                        for key in ("seller_messages", "client_messages", "messages"):
                            if key in rd and isinstance(rd[key], list):
                                for msg in rd[key]:
                                    if isinstance(msg, dict) and str(msg.get("sender_id", "")) == str(user_id):
                                        historical_texts.append(msg.get("text", ""))

            if historical_texts:
                combined_hist = " ".join(t for t in historical_texts if t)
                if len(combined_hist) > 20:
                    hist_fp = compute_text_fingerprint(combined_hist)
                    if hist_fp.char_bigram_freq:
                        hist_sim = compare_fingerprints(current_fp, hist_fp)
                        # Sudden large style shift compared to history
                        if hist_sim < 0.35:
                            anomaly_score += 0.15
                            flags.append(f"style_shift_from_history={hist_sim:.2f}")
    except Exception as e:
        logger.debug("Could not retrieve historical duels: %s", e)

    # 3. AI text marker detection
    ai_markers = detect_ai_text_markers(current_text)
    if ai_markers["ai_probability"] >= 0.5:
        anomaly_score += 0.3
        flags.append(f"ai_markers_p={ai_markers['ai_probability']:.2f}")

    if ai_markers["confidence"] == "high":
        anomaly_score += 0.15
        flags.extend(ai_markers.get("markers_found", [])[:3])

    # 4. Check consistency within current messages (variance in style)
    if len(user_msgs) >= 3:
        fingerprints = [
            compute_text_fingerprint(m.get("text", ""))
            for m in user_msgs
        ]
        fingerprints = [fp for fp in fingerprints if fp.char_bigram_freq]

        if len(fingerprints) >= 2:
            similarities = [
                compare_fingerprints(fingerprints[0], fp)
                for fp in fingerprints[1:]
            ]
            avg_similarity = statistics.mean(similarities)

            # Too consistent = suspicious (AI tends to have same style)
            if avg_similarity > 0.85:
                anomaly_score += 0.2
                flags.append(f"style_too_consistent={avg_similarity:.2f}")

            # Highly variable = potential copy-paste from different sources
            if avg_similarity < 0.5:
                anomaly_score += 0.1
                flags.append(f"style_highly_variable={avg_similarity:.2f}")

    anomaly_score = min(1.0, anomaly_score)
    flagged = anomaly_score >= 0.5

    return AntiCheatSignal(
        check_type=AntiCheatCheckType.ai_detector,
        score=anomaly_score,
        flagged=flagged,
        details={
            "ai_probability": ai_markers.get("ai_probability", 0.0),
            "ai_confidence": ai_markers.get("confidence", "low"),
            "message_count": len(user_msgs),
            "flags": flags,
        },
    )


async def save_anti_cheat_result(
    result: AntiCheatResult,
    db: AsyncSession,
) -> list[AntiCheatLog]:
    """Persist anti-cheat signals to database."""
    logs = []
    for signal in result.signals:
        if signal.score > 0.1:  # Only save non-trivial signals
            log = AntiCheatLog(
                user_id=result.user_id,
                duel_id=result.duel_id,
                check_type=signal.check_type,
                score=signal.score,
                flagged=signal.flagged,
                action_taken=result.recommended_action if signal.flagged else AntiCheatAction.none,
                details=signal.details,
            )
            db.add(log)
            logs.append(log)

    await db.flush()
    logger.info(
        "Anti-cheat: user=%s, duel=%s, flagged=%s, action=%s, signals=%d",
        result.user_id,
        result.duel_id,
        result.overall_flagged,
        result.recommended_action.value,
        len(logs),
    )
    return logs
