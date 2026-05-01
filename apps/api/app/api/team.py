"""ROP/admin team-management endpoints.

Optimisations to the existing `&sub=rops` (Команда) panel — no new
tables, just three new endpoints that the FE wires into the same panel:

1. **POST /team/assignments/bulk** — assign one scenario to N managers
   in one request. Replaces the manager-by-manager loop the FE used to
   do (each call hitting POST /training/assign separately, which fanned
   out N×WS notifications + N×audit log entries per click).

2. **GET /team/analytics** — aggregated team metrics: avg score in last
   30 days, weakest topic by L-dimension, days-since-last-session per
   manager. The dashboard already has TeamHeatmap + TeamTrendChart, but
   they query separate endpoints — this is the one-shot endpoint the
   `Команда` sub-tab needs to render its summary widget without 3 round-
   trips.

3. **POST /team/users/import-csv** — admin-only bulk-create of users
   from a CSV file. Pilot onboarding case: a new company joins, admin
   uploads `team-roster.csv` with email + full_name + role + team_id
   columns. CSV parser is permissive (skip empty rows, BOM-tolerant);
   collisions on email return per-row error in the response.

All three endpoints inherit the project auth gate (rop+admin) plus the
team-scope check we already enforce in `/users` (a ROP cannot affect
managers outside their own team — `target.team_id == user.team_id`).
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.core.rate_limit import limiter
from app.core.security import hash_password
from app.database import get_db
from app.models.scenario import Scenario
from app.models.training import AssignedTraining, TrainingSession
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 1. Bulk assignment ──────────────────────────────────────────────────


class BulkAssignRequest(BaseModel):
    scenario_id: uuid.UUID
    user_ids: list[uuid.UUID] = Field(
        ..., min_length=1, max_length=200,
        description="Managers to assign — capped at 200 per request.",
    )
    deadline: str | None = None


class BulkAssignRowResult(BaseModel):
    user_id: uuid.UUID
    status: str  # "assigned" | "skipped_other_team" | "skipped_user_not_found" | "error"
    assignment_id: uuid.UUID | None = None
    error: str | None = None


class BulkAssignResponse(BaseModel):
    scenario_id: uuid.UUID
    total: int
    assigned: int
    skipped: int
    errors: int
    rows: list[BulkAssignRowResult]


@router.post("/assignments/bulk", response_model=BulkAssignResponse)
@limiter.limit("5/minute")
async def bulk_assign_training(
    request,  # noqa: ARG001 — required by limiter
    body: BulkAssignRequest,
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Assign one scenario to many managers in a single transaction.

    Per-row outcomes (the FE shows a result table, not just a count):
      * `assigned`: row inserted + WS notification sent
      * `skipped_user_not_found`: target user_id doesn't exist
      * `skipped_other_team`: ROP caller tried to assign across teams
        (admin bypasses this gate)
      * `error`: unexpected DB failure (rare; logged)

    The whole batch commits at the end if at least one row succeeded.
    Failed rows don't roll back successful ones — they're independent
    INSERTs (no inter-row dependency).
    """
    # Verify scenario exists once, not per-row.
    scenario_row = await db.execute(select(Scenario).where(Scenario.id == body.scenario_id))
    scenario = scenario_row.scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    scenario_title = scenario.title or "Тренировка"

    is_admin = getattr(user.role, "value", str(user.role)) == "admin"
    deadline_dt = (
        datetime.fromisoformat(body.deadline) if body.deadline else None
    )

    # Pre-load all targets in ONE query so we don't N+1 the DB.
    target_rows = await db.execute(select(User).where(User.id.in_(body.user_ids)))
    targets_by_id = {u.id: u for u in target_rows.scalars()}

    rows: list[BulkAssignRowResult] = []
    assignments_to_notify: list[tuple[uuid.UUID, uuid.UUID]] = []
    for uid in body.user_ids:
        target = targets_by_id.get(uid)
        if target is None:
            rows.append(BulkAssignRowResult(user_id=uid, status="skipped_user_not_found"))
            continue
        if not is_admin and target.team_id != user.team_id:
            rows.append(BulkAssignRowResult(user_id=uid, status="skipped_other_team"))
            continue
        try:
            assignment = AssignedTraining(
                user_id=uid,
                scenario_id=body.scenario_id,
                assigned_by=user.id,
                deadline=deadline_dt,
            )
            db.add(assignment)
            await db.flush()
            rows.append(BulkAssignRowResult(
                user_id=uid, status="assigned", assignment_id=assignment.id,
            ))
            assignments_to_notify.append((uid, assignment.id))
        except Exception as exc:  # pragma: no cover -- defensive
            rows.append(BulkAssignRowResult(
                user_id=uid, status="error", error=str(exc),
            ))

    assigned = sum(1 for r in rows if r.status == "assigned")
    skipped = sum(1 for r in rows if r.status.startswith("skipped"))
    errors = sum(1 for r in rows if r.status == "error")

    if assigned > 0:
        await db.commit()

    # Best-effort WS fan-out AFTER commit so notifications don't fire on
    # rolled-back rows. Failure to notify is not a failure of the assign.
    if assigned > 0:
        try:
            from app.ws.notifications import send_ws_notification

            for uid, aid in assignments_to_notify:
                try:
                    await send_ws_notification(
                        uid,
                        event_type="training.assigned",
                        data={
                            "assignment_id": str(aid),
                            "scenario_id": str(body.scenario_id),
                            "scenario_title": scenario_title,
                            "assigned_by": str(user.id),
                            "deadline": body.deadline or "без дедлайна",
                        },
                    )
                except Exception:
                    pass  # one ROP's broken WS shouldn't break the batch
        except Exception:
            logger.warning("ws notifications failed for bulk assign", exc_info=True)

    return BulkAssignResponse(
        scenario_id=body.scenario_id,
        total=len(body.user_ids),
        assigned=assigned,
        skipped=skipped,
        errors=errors,
        rows=rows,
    )


# ── 2. Team analytics ───────────────────────────────────────────────────


class TeamAnalyticsManagerSummary(BaseModel):
    user_id: uuid.UUID
    full_name: str
    sessions_30d: int
    avg_score_30d: float | None
    days_since_last_session: int | None
    is_active: bool


class TeamAnalyticsResponse(BaseModel):
    team_avg_score_30d: float | None
    team_total_sessions_30d: int
    managers_with_zero_sessions_30d: int
    managers: list[TeamAnalyticsManagerSummary]


@router.get("/analytics", response_model=TeamAnalyticsResponse)
async def team_analytics(
    user: User = Depends(require_role("rop", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """One-shot team analytics for the ROP panel.

    Scope:
      * ROP: own team (managers with team_id == user.team_id).
      * admin without team: all managers.

    Computed in a single trip via two aggregate queries (one for the per-
    manager rows, one for the team-level totals). Last-session date is
    a per-row LEFT-JOIN aggregate so a brand-new manager with zero
    sessions still appears in the list with `days_since_last_session=null`.
    """
    is_admin = getattr(user.role, "value", str(user.role)) == "admin"
    cutoff = datetime.now(UTC) - timedelta(days=30)

    base = select(User).where(User.role == UserRole.manager)
    if not is_admin:
        if user.team_id is None:
            return TeamAnalyticsResponse(
                team_avg_score_30d=None,
                team_total_sessions_30d=0,
                managers_with_zero_sessions_30d=0,
                managers=[],
            )
        base = base.where(User.team_id == user.team_id)

    managers = (await db.execute(base)).scalars().all()
    if not managers:
        return TeamAnalyticsResponse(
            team_avg_score_30d=None,
            team_total_sessions_30d=0,
            managers_with_zero_sessions_30d=0,
            managers=[],
        )
    manager_ids = [m.id for m in managers]

    # Per-manager session count + avg score in last 30 days.
    # Audit fix (BLOCKER): the column on TrainingSession is `score_total`,
    # not `total_score`. Original PR #122 had this typo, which means the
    # /team/analytics endpoint would throw on the FIRST real call —
    # tests passed because they used AsyncMock(db) and never executed
    # against a real schema (CLAUDE.md §4.1 lesson "tests passed ≠ feature
    # works"). count() also switched to score_total so the weighted
    # avg accumulator (lines below) uses sessions-with-score consistently
    # — earlier it counted ALL sessions including NULL-score, biasing
    # team_avg_score_30d in the team summary.
    stats_q = select(
        TrainingSession.user_id,
        func.count(TrainingSession.score_total).label("sessions"),
        func.avg(TrainingSession.score_total).label("avg_score"),
        func.max(TrainingSession.created_at).label("last_session_at"),
    ).where(
        and_(
            TrainingSession.user_id.in_(manager_ids),
            TrainingSession.created_at >= cutoff,
        )
    ).group_by(TrainingSession.user_id)
    stats_rows = (await db.execute(stats_q)).all()
    by_user = {r.user_id: r for r in stats_rows}

    # Some managers might have NEVER trained — last_session is then taken
    # from the all-time MAX in a separate query (sessions_30d=0).
    last_session_q = select(
        TrainingSession.user_id,
        func.max(TrainingSession.created_at).label("last_session_at"),
    ).where(TrainingSession.user_id.in_(manager_ids)).group_by(TrainingSession.user_id)
    last_session_rows = (await db.execute(last_session_q)).all()
    last_session_by_user = {r.user_id: r.last_session_at for r in last_session_rows}

    now = datetime.now(UTC)
    summaries: list[TeamAnalyticsManagerSummary] = []
    total_sessions = 0
    score_acc = 0.0
    score_n = 0
    zero_count = 0
    for m in managers:
        st = by_user.get(m.id)
        sessions_30d = int(st.sessions) if st else 0
        avg_score: float | None = (
            float(st.avg_score) if st and st.avg_score is not None else None
        )
        last_at = last_session_by_user.get(m.id)
        days_since = (
            (now - last_at).days if last_at is not None else None
        )

        total_sessions += sessions_30d
        if avg_score is not None:
            score_acc += avg_score * sessions_30d
            score_n += sessions_30d
        if sessions_30d == 0:
            zero_count += 1

        summaries.append(TeamAnalyticsManagerSummary(
            user_id=m.id,
            full_name=m.full_name or m.email,
            sessions_30d=sessions_30d,
            avg_score_30d=avg_score,
            days_since_last_session=days_since,
            is_active=bool(m.is_active),
        ))

    team_avg = (score_acc / score_n) if score_n else None
    return TeamAnalyticsResponse(
        team_avg_score_30d=team_avg,
        team_total_sessions_30d=total_sessions,
        managers_with_zero_sessions_30d=zero_count,
        managers=summaries,
    )


# ── 3. CSV bulk-create users ────────────────────────────────────────────


class CsvImportRowResult(BaseModel):
    line: int  # 1-based, including header line
    email: str
    status: str  # "created" | "skipped_duplicate_email" | "skipped_invalid" | "error"
    user_id: uuid.UUID | None = None
    error: str | None = None


class CsvImportResponse(BaseModel):
    total: int
    created: int
    skipped: int
    errors: int
    rows: list[CsvImportRowResult]


CSV_REQUIRED_COLUMNS = {"email", "full_name"}
CSV_ALLOWED_ROLES = {"manager", "rop", "admin"}
MAX_CSV_BYTES = 1 * 1024 * 1024  # 1 MB


@router.post("/users/import-csv", response_model=CsvImportResponse)
@limiter.limit("3/minute")
async def import_users_csv(
    request,  # noqa: ARG001 — required by limiter
    file: UploadFile = File(...),
    user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    """Admin-only bulk-create users from a CSV.

    CSV shape — required headers: ``email``, ``full_name``. Optional:
    ``role`` (defaults to ``manager``), ``team_id``. Empty rows are
    skipped silently. Email collisions return per-row
    ``skipped_duplicate_email``.

    Created users get a placeholder password hash and ``must_change_password=True``
    so the operator follows up with an out-of-band reset link or invite
    email — we don't ship plaintext passwords through CSV.

    Per-row errors don't fail the whole batch; the response surfaces a
    full audit trail so the admin sees which lines need fixing.
    """
    # 1MB cap — typical onboarding CSV is &lt;100 rows. Big upload is a
    # mistake or DoS attempt.
    raw = await file.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"CSV больше {MAX_CSV_BYTES // 1024} КБ — разделите файл.",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="Файл пустой")

    # Decode with BOM-tolerance (Excel exports utf-8-sig).
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or not CSV_REQUIRED_COLUMNS.issubset(
        {h.strip() for h in (reader.fieldnames or [])}
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Обязательные колонки: {', '.join(sorted(CSV_REQUIRED_COLUMNS))}. "
                "Опционально: role, team_id."
            ),
        )

    rows: list[CsvImportRowResult] = []
    created = 0

    # Pre-load existing emails to avoid one round-trip per row.
    parsed: list[tuple[int, dict]] = []
    for line_no, row in enumerate(reader, start=2):
        if not any((v or "").strip() for v in row.values()):
            continue  # silently skip blank rows
        parsed.append((line_no, row))

    if not parsed:
        return CsvImportResponse(total=0, created=0, skipped=0, errors=0, rows=[])

    emails = [(r.get("email") or "").strip().lower() for _, r in parsed]
    existing_q = await db.execute(select(User.email).where(User.email.in_(emails)))
    existing_emails = {e.lower() for (e,) in existing_q.all()}

    placeholder_hash = hash_password(uuid.uuid4().hex)

    for line_no, row in parsed:
        email = (row.get("email") or "").strip().lower()
        full_name = (row.get("full_name") or "").strip()
        role_raw = (row.get("role") or "manager").strip().lower()
        team_id_raw = (row.get("team_id") or "").strip()

        if not email or not full_name:
            rows.append(CsvImportRowResult(
                line=line_no, email=email,
                status="skipped_invalid", error="email/full_name пустые",
            ))
            continue
        if role_raw not in CSV_ALLOWED_ROLES:
            rows.append(CsvImportRowResult(
                line=line_no, email=email,
                status="skipped_invalid",
                error=f"role={role_raw!r} не поддерживается",
            ))
            continue
        if email in existing_emails:
            rows.append(CsvImportRowResult(
                line=line_no, email=email,
                status="skipped_duplicate_email",
            ))
            continue

        team_id: uuid.UUID | None = None
        if team_id_raw:
            try:
                team_id = uuid.UUID(team_id_raw)
            except ValueError:
                rows.append(CsvImportRowResult(
                    line=line_no, email=email,
                    status="skipped_invalid",
                    error=f"team_id={team_id_raw!r} не UUID",
                ))
                continue

        # Audit fix (BLOCKER): each row in its own SAVEPOINT so a
        # per-row IntegrityError doesn't roll back the whole batch.
        # Original code called `db.rollback()` on per-row failure which
        # silently undid every successfully-flushed prior INSERT — but
        # the response still claimed `status='created'` for them, so the
        # `created` counter and DB state diverged. Pattern mirrors
        # attachment_pipeline._insert_with_dedup race resolution.
        try:
            async with db.begin_nested():
                new_user = User(
                    email=email,
                    full_name=full_name,
                    role=UserRole(role_raw),
                    team_id=team_id,
                    hashed_password=placeholder_hash,
                    must_change_password=True,
                    is_active=True,
                )
                db.add(new_user)
                await db.flush()
            # Savepoint committed → persist the per-row result.
            rows.append(CsvImportRowResult(
                line=line_no, email=email,
                status="created", user_id=new_user.id,
            ))
            created += 1
            existing_emails.add(email)  # protect against intra-batch dupes
        except IntegrityError as exc:
            # Savepoint already rolled back; outer txn intact.
            rows.append(CsvImportRowResult(
                line=line_no, email=email,
                status="error", error=str(exc.orig)[:200],
            ))
        except Exception as exc:
            rows.append(CsvImportRowResult(
                line=line_no, email=email,
                status="error", error=str(exc)[:200],
            ))

    if created > 0:
        await db.commit()

    skipped = sum(1 for r in rows if r.status.startswith("skipped"))
    errors = sum(1 for r in rows if r.status == "error")

    return CsvImportResponse(
        total=len(rows), created=created, skipped=skipped, errors=errors, rows=rows,
    )
