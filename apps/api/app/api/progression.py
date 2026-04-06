"""Progression API — Hunter Score, Arena Points, Catch-Up (DOC_14/DOC_13/DOC_04)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────────────

class HunterScoreResponse(BaseModel):
    user_id: str
    hunter_score: float


class APBalanceResponse(BaseModel):
    arena_points: int
    shop_items: list[dict]


class APPurchaseRequest(BaseModel):
    item_id: str


class APPurchaseResponse(BaseModel):
    success: bool
    remaining_ap: int
    item_id: str
    message: str


class StuckCheckpointResponse(BaseModel):
    checkpoint_code: str
    days_stuck: int
    hint: str | None
    can_soften: bool


class SoftenResponse(BaseModel):
    success: bool
    checkpoint_code: str
    action: str
    message: str


# ─── Hunter Score ────────────────────────────────────────────────────────────

@router.get("/hunter-score", response_model=HunterScoreResponse)
async def get_hunter_score(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's Hunter Score composite metric."""
    from app.services.hunter_score import update_hunter_score

    score = await update_hunter_score(db, user.id)
    return HunterScoreResponse(user_id=str(user.id), hunter_score=score)


@router.post("/hunter-score/recalculate", response_model=HunterScoreResponse)
async def recalculate_hunter_score(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Force recalculate and persist Hunter Score."""
    from app.services.hunter_score import update_hunter_score

    score = await update_hunter_score(db, user.id)
    await db.commit()
    return HunterScoreResponse(user_id=str(user.id), hunter_score=score)


# ─── Arena Points ────────────────────────────────────────────────────────────

@router.get("/arena-points", response_model=APBalanceResponse)
async def get_arena_points(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current AP balance and available shop items."""
    from sqlalchemy import select

    from app.models.progress import ManagerProgress
    from app.services.arena_points import AP_SHOP_ITEMS

    result = await db.execute(
        select(ManagerProgress).where(ManagerProgress.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    balance = profile.arena_points if profile else 0

    items = [
        {"id": k, "cost": v["cost"], "type": v["type"], "permanent": v["permanent"]}
        for k, v in AP_SHOP_ITEMS.items()
    ]

    return APBalanceResponse(arena_points=balance, shop_items=items)


@router.post("/arena-points/purchase", response_model=APPurchaseResponse)
async def purchase_ap_item(
    body: APPurchaseRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Purchase an item from the AP Shop."""
    from app.services.arena_points import purchase_item

    try:
        result = await purchase_item(db, user.id, body.item_id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return APPurchaseResponse(
        success=True,
        remaining_ap=result.get("remaining_ap", 0),
        item_id=body.item_id,
        message=result.get("message", "Purchase successful"),
    )


# ─── Season Pass ─────────────────────────────────────────────────────────────

@router.get("/season-pass")
async def get_season_pass(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current season pass progress, tier, and rewards."""
    from app.services.season_pass import get_season_progress

    return await get_season_progress(user.id, db)


# ─── Catch-Up ────────────────────────────────────────────────────────────────

@router.get("/catch-up", response_model=list[StuckCheckpointResponse])
async def list_stuck_checkpoints(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List stuck checkpoints eligible for catch-up hints or softening."""
    from app.services.catch_up_manager import CatchUpManager

    mgr = CatchUpManager(db)
    actions = await mgr.check_and_apply(user.id)

    return [
        StuckCheckpointResponse(
            checkpoint_code=a.get("checkpoint_code", "unknown"),
            days_stuck=a.get("days_stuck", 0),
            hint=a.get("hint"),
            can_soften=a.get("can_soften", False),
        )
        for a in actions
    ]


@router.post("/catch-up/{checkpoint_code}/soften", response_model=SoftenResponse)
async def soften_checkpoint(
    checkpoint_code: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply softening (requirement reduction) to a stuck checkpoint."""
    from sqlalchemy import select

    from app.models.checkpoint import CheckpointDefinition, UserCheckpoint
    from app.services.catch_up_manager import CatchUpManager, REDUCTION_RULES

    # Find the user checkpoint
    result = await db.execute(
        select(UserCheckpoint, CheckpointDefinition)
        .join(CheckpointDefinition, UserCheckpoint.checkpoint_id == CheckpointDefinition.id)
        .where(
            UserCheckpoint.user_id == user.id,
            CheckpointDefinition.code == checkpoint_code,
            UserCheckpoint.is_completed == False,  # noqa: E712
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Checkpoint not found or already completed")

    ucp, cp_def = row
    if ucp.is_softened:
        raise HTTPException(status_code=400, detail="Checkpoint already softened")

    from datetime import datetime

    days_stuck = (datetime.utcnow() - (ucp.updated_at or ucp.created_at)).days
    if days_stuck < 14:
        raise HTTPException(status_code=400, detail=f"Checkpoint not eligible yet (stuck {days_stuck} days, need 14)")

    # Apply softening
    conditions = cp_def.conditions or {}
    reduced_keys = []
    for param, rule in REDUCTION_RULES.items():
        if param in conditions:
            old_val = conditions[param]
            new_val = max(rule["min"], old_val + rule["delta"])
            if new_val != old_val:
                conditions[param] = new_val
                reduced_keys.append(param)

    if reduced_keys:
        cp_def.conditions = conditions
        ucp.is_softened = True
        await db.commit()

    return SoftenResponse(
        success=bool(reduced_keys),
        checkpoint_code=checkpoint_code,
        action="softened" if reduced_keys else "no_reduction_possible",
        message=f"Reduced: {', '.join(reduced_keys)}" if reduced_keys else "No parameters eligible for reduction",
    )
