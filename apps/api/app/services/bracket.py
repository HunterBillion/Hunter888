"""Bracket / knockout tournament engine.

Manages seeding, bracket generation, match advancement, and final placement
for single-elimination tournaments.

Bracket size is always a power of 2 (8, 16, 32).  If fewer participants
register, byes are assigned to top seeds in the first round.
"""

import json
import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pvp import PvPRating
from app.models.tournament import (
    BracketMatch,
    BracketMatchStatus,
    Tournament,
    TournamentFormat,
    TournamentParticipant,
)
from app.models.user import User

logger = logging.getLogger(__name__)


def _next_power_of_2(n: int) -> int:
    """Return the smallest power of 2 >= n, minimum 4."""
    if n <= 4:
        return 4
    return 1 << (n - 1).bit_length()


def _total_rounds(bracket_size: int) -> int:
    return int(math.log2(bracket_size))


def _standard_seed_order(size: int) -> list[int]:
    """Generate standard tournament seed order for `size` slots.

    Ensures top seeds meet only in later rounds (e.g., seed 1 vs seed 2 only
    in the final).  Returns 1-based seed numbers.
    """
    if size == 1:
        return [1]
    if size == 2:
        return [1, 2]

    half = size // 2
    top = _standard_seed_order(half)
    # Mirror: pair seed k with seed (size + 1 - k)
    bottom: list[int] = []
    for s in top:
        bottom.append(size + 1 - s)

    result: list[int] = []
    for a, b in zip(top, bottom):
        result.extend([a, b])
    return result


# ─── Registration ─────────────────────────────────────────────────────────────


async def register_participant(
    tournament_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> TournamentParticipant | None:
    """Register a user for a bracket tournament.

    Returns None if already registered or registration is closed.
    """
    t = await db.get(Tournament, tournament_id)
    if not t or t.format != TournamentFormat.bracket.value or not t.is_active:
        return None

    now = datetime.now(timezone.utc)
    if t.registration_end and now > t.registration_end:
        return None

    # Check duplicate
    existing = await db.execute(
        select(TournamentParticipant).where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return None

    # Snapshot rating
    rating_row = await db.execute(
        select(PvPRating.rating).where(
            PvPRating.user_id == user_id,
            PvPRating.rating_type == "training_duel",
        )
    )
    rating_val = rating_row.scalar_one_or_none() or 1500.0

    p = TournamentParticipant(
        tournament_id=tournament_id,
        user_id=user_id,
        rating_snapshot=rating_val,
    )
    db.add(p)
    await db.flush()
    logger.info("User %s registered for bracket tournament %s (rating=%.0f)", user_id, tournament_id, rating_val)
    return p


async def get_participants(
    tournament_id: uuid.UUID,
    db: AsyncSession,
) -> list[TournamentParticipant]:
    result = await db.execute(
        select(TournamentParticipant)
        .where(TournamentParticipant.tournament_id == tournament_id)
        .order_by(TournamentParticipant.rating_snapshot.desc())
    )
    return list(result.scalars().all())


# ─── Bracket generation ──────────────────────────────────────────────────────


async def generate_bracket(
    tournament_id: uuid.UUID,
    db: AsyncSession,
) -> list[BracketMatch]:
    """Seed participants and create first-round matches.

    Call this when registration closes. Uses Glicko-2 RD-weighted seeding to incorporate
    rating confidence. Assigns seeds by adjusted seed_score = rating - (RD penalty).
    Bracket matches are created with byes for missing slots.
    """
    t = await db.get(Tournament, tournament_id)
    if not t or t.format != TournamentFormat.bracket.value:
        return []

    participants = await get_participants(tournament_id, db)
    if len(participants) < 2:
        logger.warning("Not enough participants (%d) for bracket in tournament %s", len(participants), tournament_id)
        return []

    # ─── RD-weighted seeding ────────────────────────────────────────────────────

    # Load RD values for each participant to adjust seed scores
    SEED_RD_PENALTY = 0.5  # How much uncertainty reduces effective rating

    participant_ids = [p.user_id for p in participants]
    rd_result = await db.execute(
        select(PvPRating.user_id, PvPRating.rd).where(
            PvPRating.user_id.in_(participant_ids),
            PvPRating.rating_type == "training_duel",
        )
    )
    user_to_rd: dict[uuid.UUID, float] = {
        user_id: rd for user_id, rd in rd_result.all()
    }

    # Calculate seed score for each participant (lower RD = higher confidence = higher seed score)
    seed_scores: list[tuple[TournamentParticipant, float]] = []
    for p in participants:
        rd = user_to_rd.get(p.user_id, 350.0)
        # Seed score = rating - (RD penalty); high RD reduces the score
        penalty = max(0, rd - 50) * SEED_RD_PENALTY
        seed_score = p.rating_snapshot - penalty
        seed_scores.append((p, seed_score))

    # Sort by seed score descending
    seed_scores.sort(key=lambda x: x[1], reverse=True)
    participants = [p for p, _ in seed_scores]

    bracket_size = _next_power_of_2(len(participants))
    total_rounds = _total_rounds(bracket_size)
    num_matches_r1 = bracket_size // 2

    # Assign seeds (1-based, ordered by adjusted seed score)
    for i, p in enumerate(participants):
        p.seed = i + 1
        db.add(p)

    # Build participant lookup by seed
    seed_to_user: dict[int, uuid.UUID] = {p.seed: p.user_id for p in participants}

    # Generate seed order for bracket placement
    seed_order = _standard_seed_order(bracket_size)

    # Create round-1 matches
    matches: list[BracketMatch] = []
    for match_idx in range(num_matches_r1):
        seed_a = seed_order[match_idx * 2]
        seed_b = seed_order[match_idx * 2 + 1]
        player1 = seed_to_user.get(seed_a)
        player2 = seed_to_user.get(seed_b)

        is_bye = player1 is None or player2 is None
        winner = (player1 or player2) if is_bye else None

        m = BracketMatch(
            tournament_id=tournament_id,
            round_num=1,
            match_index=match_idx,
            player1_id=player1,
            player2_id=player2,
            winner_id=winner,
            status=BracketMatchStatus.bye.value if is_bye else BracketMatchStatus.pending.value,
            completed_at=datetime.now(timezone.utc) if is_bye else None,
        )
        db.add(m)
        matches.append(m)

    # Create placeholder matches for subsequent rounds
    for rnd in range(2, total_rounds + 1):
        num_matches = bracket_size // (2**rnd)
        for match_idx in range(num_matches):
            m = BracketMatch(
                tournament_id=tournament_id,
                round_num=rnd,
                match_index=match_idx,
                status=BracketMatchStatus.pending.value,
            )
            db.add(m)
            matches.append(m)

    # Update tournament state
    t.bracket_size = bracket_size
    t.current_round_num = 1
    t.bracket_data = {"seed_order": seed_order, "total_rounds": total_rounds}
    db.add(t)

    await db.flush()

    # Advance byes from round 1
    await _advance_byes(tournament_id, 1, db)

    # Auto-schedule round 1 with forfeit deadlines
    await schedule_round_matches(tournament_id, 1, db)

    logger.info(
        "Generated bracket for tournament %s: %d participants, size=%d, rounds=%d (RD-weighted seeding)",
        tournament_id, len(participants), bracket_size, total_rounds,
    )
    return matches


async def _advance_byes(
    tournament_id: uuid.UUID,
    round_num: int,
    db: AsyncSession,
) -> None:
    """Advance bye winners to the next round."""
    result = await db.execute(
        select(BracketMatch).where(
            BracketMatch.tournament_id == tournament_id,
            BracketMatch.round_num == round_num,
            BracketMatch.status == BracketMatchStatus.bye.value,
        ).order_by(BracketMatch.match_index)
    )
    bye_matches = list(result.scalars().all())

    for m in bye_matches:
        if m.winner_id:
            await _place_winner_in_next_round(tournament_id, m.round_num, m.match_index, m.winner_id, db)


async def _place_winner_in_next_round(
    tournament_id: uuid.UUID,
    current_round: int,
    current_match_index: int,
    winner_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Place a match winner into their next-round match slot."""
    next_round = current_round + 1
    next_match_index = current_match_index // 2
    is_top_slot = current_match_index % 2 == 0  # even index → player1 slot

    result = await db.execute(
        select(BracketMatch).where(
            BracketMatch.tournament_id == tournament_id,
            BracketMatch.round_num == next_round,
            BracketMatch.match_index == next_match_index,
        )
    )
    next_match = result.scalar_one_or_none()
    if not next_match:
        return  # Final was won — tournament complete

    if is_top_slot:
        next_match.player1_id = winner_id
    else:
        next_match.player2_id = winner_id

    # If both players are now set, check for auto-bye
    if next_match.player1_id and next_match.player2_id:
        pass  # Both present — match is ready
    elif next_match.player1_id or next_match.player2_id:
        # Check if the other slot's source match exists and is completed
        other_source_match_idx = next_match_index * 2 + (1 if is_top_slot else 0)
        other_result = await db.execute(
            select(BracketMatch).where(
                BracketMatch.tournament_id == tournament_id,
                BracketMatch.round_num == current_round,
                BracketMatch.match_index == other_source_match_idx,
            )
        )
        other_match = other_result.scalar_one_or_none()
        if other_match and other_match.status in (
            BracketMatchStatus.completed.value,
            BracketMatchStatus.bye.value,
        ):
            # Both source matches are done — this is a bye in the next round
            only_player = next_match.player1_id or next_match.player2_id
            next_match.winner_id = only_player
            next_match.status = BracketMatchStatus.bye.value
            next_match.completed_at = datetime.now(timezone.utc)

    db.add(next_match)
    await db.flush()


# ─── Match start (create PvP duel) ────────────────────────────────────────────


async def start_bracket_match(
    match_id: uuid.UUID,
    db: AsyncSession,
) -> BracketMatch | None:
    """Create a PvP duel for a pending bracket match.

    Links the duel to the bracket match and marks it as active.
    Returns None if the match isn't ready (missing players, wrong status).
    """
    from app.models.pvp import PvPDuel, DuelStatus, DuelDifficulty

    match = await db.get(BracketMatch, match_id)
    if not match or match.status != BracketMatchStatus.pending.value:
        return None
    if not match.player1_id or not match.player2_id:
        return None

    # Get tournament for scenario
    t = await db.get(Tournament, match.tournament_id)
    if not t:
        return None

    # Anti-cheat: check both players before starting bracket match
    try:
        from app.services.anti_cheat import check_multi_account
        for pid in (match.player1_id, match.player2_id):
            multi = await check_multi_account(pid, db)
            if multi.get("is_suspicious") and multi.get("confidence", 0) > 0.9:
                logger.warning(
                    "Bracket match %s: player %s flagged by anti-cheat (confidence=%.2f)",
                    match_id, pid, multi["confidence"],
                )
    except Exception:
        logger.debug("Anti-cheat check skipped for bracket match %s", match_id)

    # Create PvP duel linked to this bracket match
    duel = PvPDuel(
        player1_id=match.player1_id,
        player2_id=match.player2_id,
        status=DuelStatus.pending,
        difficulty=DuelDifficulty.medium,
        scenario_id=t.scenario_id,
        is_pve=False,
    )
    db.add(duel)
    await db.flush()

    # Link duel to bracket match
    match.duel_id = duel.id
    match.status = BracketMatchStatus.active.value
    match.scheduled_at = datetime.now(timezone.utc)
    db.add(match)
    await db.flush()

    logger.info(
        "Started bracket match %s: duel %s (%s vs %s)",
        match_id, duel.id, match.player1_id, match.player2_id,
    )

    try:
        await broadcast_bracket_event(match.tournament_id, "bracket.match_started", {
            "match_id": str(match_id),
            "duel_id": str(duel.id),
            "player1_id": str(match.player1_id),
            "player2_id": str(match.player2_id),
        })
    except Exception:
        pass

    return match


# ─── Match completion ─────────────────────────────────────────────────────────


async def complete_bracket_match(
    match_id: uuid.UUID,
    winner_id: uuid.UUID,
    player1_score: float,
    player2_score: float,
    duel_id: uuid.UUID | None,
    db: AsyncSession,
) -> BracketMatch | None:
    """Record the result of a bracket match and advance the winner."""
    match = await db.get(BracketMatch, match_id)
    if not match or match.status not in (
        BracketMatchStatus.pending.value,
        BracketMatchStatus.active.value,
    ):
        return None

    if winner_id not in (match.player1_id, match.player2_id):
        logger.error("Winner %s not in match %s", winner_id, match_id)
        return None

    loser_id = match.player2_id if winner_id == match.player1_id else match.player1_id

    match.winner_id = winner_id
    match.player1_score = player1_score
    match.player2_score = player2_score
    match.duel_id = duel_id
    match.status = BracketMatchStatus.completed.value
    match.completed_at = datetime.now(timezone.utc)
    db.add(match)

    # Mark loser as eliminated
    if loser_id:
        await db.execute(
            update(TournamentParticipant)
            .where(
                TournamentParticipant.tournament_id == match.tournament_id,
                TournamentParticipant.user_id == loser_id,
            )
            .values(eliminated_at_round=match.round_num)
        )

    # Advance winner to next round
    await _place_winner_in_next_round(
        match.tournament_id, match.round_num, match.match_index, winner_id, db
    )

    # Check if current round is complete → advance tournament round
    await _check_round_complete(match.tournament_id, match.round_num, db)

    await db.flush()

    try:
        await broadcast_bracket_event(match.tournament_id, "bracket.match_completed", {
            "match_id": str(match_id),
            "winner_id": str(winner_id),
            "loser_id": str(loser_id) if loser_id else None,
            "player1_score": player1_score,
            "player2_score": player2_score,
            "round_num": match.round_num,
        })
    except Exception:
        pass

    return match


async def _check_round_complete(
    tournament_id: uuid.UUID,
    round_num: int,
    db: AsyncSession,
) -> None:
    """Check if all matches in a round are complete. If so, advance tournament."""
    result = await db.execute(
        select(func.count(BracketMatch.id)).where(
            BracketMatch.tournament_id == tournament_id,
            BracketMatch.round_num == round_num,
            BracketMatch.status.in_([
                BracketMatchStatus.pending.value,
                BracketMatchStatus.active.value,
            ]),
        )
    )
    remaining = result.scalar() or 0
    if remaining > 0:
        return

    t = await db.get(Tournament, tournament_id)
    if not t or not t.bracket_data:
        return

    total_rounds = t.bracket_data.get("total_rounds", 0)

    if round_num >= total_rounds:
        # Tournament is finished — determine final placements
        await _finalize_tournament(tournament_id, db)
        # Broadcast tournament complete
        try:
            await broadcast_bracket_event(tournament_id, "bracket.tournament_complete", {
                "tournament_id": str(tournament_id),
            })
        except Exception:
            pass
    else:
        next_round = round_num + 1
        t.current_round_num = next_round
        db.add(t)
        # Auto-schedule next round matches with forfeit deadlines
        await schedule_round_matches(tournament_id, next_round, db)
        # Advance any byes in the new round
        await _advance_byes(tournament_id, next_round, db)
        # Broadcast round advancement
        try:
            await broadcast_bracket_event(tournament_id, "bracket.round_advanced", {
                "tournament_id": str(tournament_id),
                "new_round": next_round,
            })
        except Exception:
            pass


async def _finalize_tournament(
    tournament_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Mark tournament complete and assign final placements."""
    t = await db.get(Tournament, tournament_id)
    if not t:
        return

    total_rounds = t.bracket_data.get("total_rounds", 0) if t.bracket_data else 0

    # Find the final match
    result = await db.execute(
        select(BracketMatch).where(
            BracketMatch.tournament_id == tournament_id,
            BracketMatch.round_num == total_rounds,
            BracketMatch.match_index == 0,
        )
    )
    final = result.scalar_one_or_none()
    if not final or not final.winner_id:
        return

    # 1st place = final winner
    await _set_placement(tournament_id, final.winner_id, 1, db)

    # 2nd place = final loser
    runner_up = final.player2_id if final.winner_id == final.player1_id else final.player1_id
    if runner_up:
        await _set_placement(tournament_id, runner_up, 2, db)

    # 3rd/4th = semifinal losers
    if total_rounds >= 2:
        semi_result = await db.execute(
            select(BracketMatch).where(
                BracketMatch.tournament_id == tournament_id,
                BracketMatch.round_num == total_rounds - 1,
            ).order_by(BracketMatch.match_index)
        )
        semis = list(semi_result.scalars().all())
        placement = 3
        for semi in semis:
            if semi.winner_id and semi.status == BracketMatchStatus.completed.value:
                loser = semi.player2_id if semi.winner_id == semi.player1_id else semi.player1_id
                if loser:
                    await _set_placement(tournament_id, loser, placement, db)
                    placement += 1

    t.is_active = False
    db.add(t)

    logger.info("Tournament %s finalized. Winner: %s", tournament_id, final.winner_id)


async def _set_placement(
    tournament_id: uuid.UUID,
    user_id: uuid.UUID,
    placement: int,
    db: AsyncSession,
) -> None:
    await db.execute(
        update(TournamentParticipant)
        .where(
            TournamentParticipant.tournament_id == tournament_id,
            TournamentParticipant.user_id == user_id,
        )
        .values(final_placement=placement)
    )


# ─── Bracket view ─────────────────────────────────────────────────────────────


async def get_bracket_view(
    tournament_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Return full bracket data for the frontend visualization."""
    t = await db.get(Tournament, tournament_id)
    if not t:
        return {}

    # Load all matches
    result = await db.execute(
        select(BracketMatch)
        .where(BracketMatch.tournament_id == tournament_id)
        .order_by(BracketMatch.round_num, BracketMatch.match_index)
    )
    matches = list(result.scalars().all())

    # Load participant names
    p_result = await db.execute(
        select(TournamentParticipant, User.full_name)
        .join(User, User.id == TournamentParticipant.user_id)
        .where(TournamentParticipant.tournament_id == tournament_id)
        .order_by(TournamentParticipant.seed)
    )
    participants = [
        {
            "user_id": str(p.user_id),
            "seed": p.seed,
            "full_name": name,
            "rating_snapshot": p.rating_snapshot,
            "eliminated_at_round": p.eliminated_at_round,
            "final_placement": p.final_placement,
        }
        for p, name in p_result.all()
    ]

    # Build user name map
    name_map: dict[str, str] = {p["user_id"]: p["full_name"] for p in participants}

    # Serialize matches grouped by round
    rounds: dict[int, list[dict]] = {}
    for m in matches:
        rnd = m.round_num
        if rnd not in rounds:
            rounds[rnd] = []
        rounds[rnd].append({
            "id": str(m.id),
            "match_index": m.match_index,
            "player1_id": str(m.player1_id) if m.player1_id else None,
            "player2_id": str(m.player2_id) if m.player2_id else None,
            "player1_name": name_map.get(str(m.player1_id), "BYE") if m.player1_id else "TBD",
            "player2_name": name_map.get(str(m.player2_id), "BYE") if m.player2_id else "TBD",
            "winner_id": str(m.winner_id) if m.winner_id else None,
            "player1_score": m.player1_score,
            "player2_score": m.player2_score,
            "status": m.status,
            "duel_id": str(m.duel_id) if m.duel_id else None,
        })

    total_rounds = t.bracket_data.get("total_rounds", 0) if t.bracket_data else 0

    return {
        "tournament_id": str(t.id),
        "title": t.title,
        "format": t.format,
        "bracket_size": t.bracket_size,
        "total_rounds": total_rounds,
        "current_round": t.current_round_num,
        "is_active": t.is_active,
        "participants": participants,
        "rounds": {str(k): v for k, v in sorted(rounds.items())},
    }


# ─── Advanced features: forfeit, scheduling, RD-weighted seeding ──────────────


def _round_label(round_num: int, total_rounds: int) -> str:
    """Return Russian label for bracket round.

    Examples: 'Первый раунд', 'Четвертьфинал', 'Полуфинал', 'Финал'
    """
    if round_num >= total_rounds:
        # Final
        if total_rounds == 1:
            return "Финал"
        return "Финал"
    elif round_num == total_rounds - 1:
        # Semifinal
        return "Полуфинал"
    elif round_num == total_rounds - 2:
        # Quarterfinal
        return "Четвертьфинал"
    else:
        # Earlier rounds — use round number
        return f"Раунд {round_num}"


async def schedule_round_matches(
    tournament_id: uuid.UUID,
    round_num: int,
    db: AsyncSession,
) -> None:
    """Schedule all pending matches in a round by setting forfeit deadlines.

    When a round starts, set forfeit_deadline = now + round_deadline_hours
    for all matches that haven't been completed yet.
    """
    t = await db.get(Tournament, tournament_id)
    if not t:
        return

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(hours=t.round_deadline_hours)

    # Get all matches in this round that are still pending or active
    result = await db.execute(
        select(BracketMatch).where(
            BracketMatch.tournament_id == tournament_id,
            BracketMatch.round_num == round_num,
            BracketMatch.status.in_([
                BracketMatchStatus.pending.value,
                BracketMatchStatus.active.value,
            ]),
        )
    )
    matches = list(result.scalars().all())

    for m in matches:
        if not m.forfeit_deadline:
            m.forfeit_deadline = deadline
            db.add(m)

    await db.flush()
    logger.info(
        "Scheduled %d matches in tournament %s round %d. Forfeit deadline: %s",
        len(matches), tournament_id, round_num, deadline.isoformat(),
    )


async def process_forfeit(
    match_id: uuid.UUID,
    forfeiting_user_id: uuid.UUID,
    db: AsyncSession,
) -> BracketMatch | None:
    """Handle player forfeit by advancing opponent.

    Sets match winner to the non-forfeiting player, marks forfeiter as eliminated,
    and advances winner to next round.
    """
    match = await db.get(BracketMatch, match_id)
    if not match or match.status == BracketMatchStatus.bye.value:
        return None

    # Determine winner and loser
    if match.player1_id == forfeiting_user_id and match.player2_id:
        winner_id = match.player2_id
        loser_id = match.player1_id
    elif match.player2_id == forfeiting_user_id and match.player1_id:
        winner_id = match.player1_id
        loser_id = match.player2_id
    else:
        logger.error("Forfeit: forfeiting user %s not in match %s", forfeiting_user_id, match_id)
        return None

    match.winner_id = winner_id
    match.forfeit_by_id = loser_id
    match.status = BracketMatchStatus.completed.value
    match.completed_at = datetime.now(timezone.utc)
    db.add(match)

    # Mark loser as eliminated
    await db.execute(
        update(TournamentParticipant)
        .where(
            TournamentParticipant.tournament_id == match.tournament_id,
            TournamentParticipant.user_id == loser_id,
        )
        .values(eliminated_at_round=match.round_num)
    )

    # Advance winner to next round
    await _place_winner_in_next_round(
        match.tournament_id, match.round_num, match.match_index, winner_id, db
    )

    # Check if round is complete
    await _check_round_complete(match.tournament_id, match.round_num, db)

    await db.flush()

    logger.info(
        "Forfeit processed: match %s, winner %s, loser %s",
        match_id, winner_id, loser_id,
    )

    try:
        await broadcast_bracket_event(match.tournament_id, "bracket.forfeit", {
            "match_id": str(match_id),
            "winner_id": str(winner_id),
            "forfeited_by": str(loser_id),
            "round_num": match.round_num,
        })
    except Exception:
        pass

    return match


async def check_and_process_timeouts(
    tournament_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Check for timed-out matches and auto-forfeit players.

    Called by periodic scheduler. For each pending match with passed forfeit_deadline:
    - If only one player showed up → auto-forfeit the absent player
    - If neither showed up → mark match as bye, advance neither

    Returns dict with counts: {'auto_forfeits': N, 'mutual_no_shows': N}
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(BracketMatch).where(
            BracketMatch.tournament_id == tournament_id,
            BracketMatch.status.in_([
                BracketMatchStatus.pending.value,
                BracketMatchStatus.active.value,
            ]),
            BracketMatch.forfeit_deadline.isnot(None),
            BracketMatch.forfeit_deadline < now,
        )
    )
    expired_matches = list(result.scalars().all())

    auto_forfeits = 0
    mutual_no_shows = 0

    for match in expired_matches:
        if match.status == BracketMatchStatus.active.value:
            # Match started — check if duel completed
            if match.duel_id:
                from app.models.pvp import PvPDuel, DuelStatus
                duel = await db.get(PvPDuel, match.duel_id)
                if duel and duel.status == DuelStatus.completed.value:
                    # Duel completed normally
                    continue

        # No active duel or duel didn't complete — handle timeout

        if match.player1_id and match.player2_id:
            if match.status == BracketMatchStatus.active.value and match.duel_id:
                # Duel was started but didn't finish — both players present,
                # but match timed out. Forfeit the player who started later
                # (for now, default to treating this as a mutual issue)
                # Use process_forfeit for the player2 (arbitrary but consistent)
                await process_forfeit(match.id, match.player2_id, db)
                auto_forfeits += 1
            elif match.status == BracketMatchStatus.pending.value:
                # Match never started — mutual no-show
                # Both players eliminated, mark match as completed with no winner
                match.status = BracketMatchStatus.completed.value
                match.completed_at = datetime.now(timezone.utc)
                # No winner — both eliminated
                db.add(match)
                for pid in (match.player1_id, match.player2_id):
                    await db.execute(
                        update(TournamentParticipant)
                        .where(
                            TournamentParticipant.tournament_id == match.tournament_id,
                            TournamentParticipant.user_id == pid,
                        )
                        .values(eliminated_at_round=match.round_num)
                    )
                mutual_no_shows += 1
                # Check if round is complete after this
                await _check_round_complete(match.tournament_id, match.round_num, db)
        elif match.player1_id or match.player2_id:
            # One player is TBD (from a previous no-show cascade)
            # Auto-advance the present player
            present = match.player1_id or match.player2_id
            match.winner_id = present
            match.status = BracketMatchStatus.bye.value
            match.completed_at = datetime.now(timezone.utc)
            db.add(match)
            await _place_winner_in_next_round(
                match.tournament_id, match.round_num, match.match_index, present, db
            )
            await _check_round_complete(match.tournament_id, match.round_num, db)
            auto_forfeits += 1

    await db.flush()

    logger.info(
        "Timeout check for tournament %s: %d auto-forfeits, %d mutual no-shows",
        tournament_id, auto_forfeits, mutual_no_shows,
    )

    return {"auto_forfeits": auto_forfeits, "mutual_no_shows": mutual_no_shows}


async def get_bracket_visualization(
    tournament_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """Return enhanced bracket visualization for frontend with positioning data.

    Includes slot indices, connects_to info, forfeit deadlines, and full player data.
    """
    t = await db.get(Tournament, tournament_id)
    if not t:
        return {}

    # Load all matches
    result = await db.execute(
        select(BracketMatch)
        .where(BracketMatch.tournament_id == tournament_id)
        .order_by(BracketMatch.round_num, BracketMatch.match_index)
    )
    all_matches = list(result.scalars().all())

    # Load participants and user names
    p_result = await db.execute(
        select(TournamentParticipant, User.full_name)
        .join(User, User.id == TournamentParticipant.user_id)
        .where(TournamentParticipant.tournament_id == tournament_id)
        .order_by(TournamentParticipant.seed)
    )
    participants_data = p_result.all()

    # Build user maps
    user_to_name: dict[uuid.UUID, str] = {p.user_id: name for p, name in participants_data}
    user_to_seed: dict[uuid.UUID, int] = {p.user_id: p.seed for p, _ in participants_data}

    total_rounds = t.bracket_data.get("total_rounds", 0) if t.bracket_data else 0

    # Build rounds array
    rounds: list[dict] = []

    for round_num in range(1, total_rounds + 1):
        round_label = _round_label(round_num, total_rounds)

        # Get matches for this round
        round_matches = [m for m in all_matches if m.round_num == round_num]

        matches_data: list[dict] = []

        for match in round_matches:
            # Determine where winner advances to
            next_round = round_num + 1
            next_match_index = match.match_index // 2
            is_top_slot = match.match_index % 2 == 0

            connects_to = None
            if next_round <= total_rounds:
                connects_to = {
                    "round": next_round,
                    "slot": next_match_index,
                    "position": "top" if is_top_slot else "bottom",
                }

            player1_info = None
            if match.player1_id:
                player1_info = {
                    "id": str(match.player1_id),
                    "name": user_to_name.get(match.player1_id, "Unknown"),
                    "seed": user_to_seed.get(match.player1_id),
                    "score": match.player1_score,
                    "is_winner": match.winner_id == match.player1_id,
                }

            player2_info = None
            if match.player2_id:
                player2_info = {
                    "id": str(match.player2_id),
                    "name": user_to_name.get(match.player2_id, "Unknown"),
                    "seed": user_to_seed.get(match.player2_id),
                    "score": match.player2_score,
                    "is_winner": match.winner_id == match.player2_id,
                }

            match_dict = {
                "id": str(match.id),
                "slot_index": match.match_index,
                "player_top": player1_info,
                "player_bottom": player2_info,
                "status": match.status,
                "connects_to": connects_to,
            }

            if match.forfeit_deadline:
                match_dict["forfeit_deadline"] = match.forfeit_deadline.isoformat()

            matches_data.append(match_dict)

        rounds.append({
            "round_num": round_num,
            "label": round_label,
            "matches": matches_data,
        })

    # Determine champion
    champion_info = None
    if not t.is_active and total_rounds > 0:
        final_match_result = await db.execute(
            select(BracketMatch).where(
                BracketMatch.tournament_id == tournament_id,
                BracketMatch.round_num == total_rounds,
                BracketMatch.match_index == 0,
            )
        )
        final_match = final_match_result.scalar_one_or_none()
        if final_match and final_match.winner_id:
            champion_info = {
                "id": str(final_match.winner_id),
                "name": user_to_name.get(final_match.winner_id, "Unknown"),
            }

    return {
        "tournament_id": str(t.id),
        "bracket_size": t.bracket_size,
        "total_rounds": total_rounds,
        "rounds": rounds,
        "champion": champion_info,
    }


async def broadcast_bracket_event(
    tournament_id: uuid.UUID,
    event_type: str,
    data: dict,
) -> None:
    """Broadcast a bracket event via Redis Pub/Sub for live updates.

    Event types:
    - bracket.match_scheduled: when forfeit_deadline is set
    - bracket.match_started: when duel is created
    - bracket.match_completed: when winner determined
    - bracket.forfeit: when player forfeits
    - bracket.round_advanced: when new round starts
    - bracket.tournament_complete: when champion determined
    """
    try:
        from app.core.redis_pool import get_redis

        r = get_redis()
        channel = f"tournament:{tournament_id}:bracket"

        event_payload = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        await r.publish(channel, json.dumps(event_payload))

        logger.debug(
            "Broadcast event %s to %s: %s",
            event_type, channel, event_payload,
        )
    except Exception as e:
        logger.warning("Failed to broadcast bracket event: %s", e)
        # Don't raise — allow core logic to proceed even if broadcast fails
