"""Prompt Registry CRUD API — Methodologist/Admin prompt management (DOC_16)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role
from app.database import get_db
from app.models.prompt_version import PromptVersion
from app.models.user import User
from app.services.prompt_registry import PROMPT_TYPES

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────────────

class PromptResponse(BaseModel):
    prompt_type: str
    prompt_key: str
    version: str
    content: str
    is_active: bool
    metrics: dict | None = None


class PromptUpdateRequest(BaseModel):
    content: str
    version: str = "v2"
    is_active: bool = True
    metrics: dict | None = None


class PromptUpdateResponse(BaseModel):
    prompt_type: str
    prompt_key: str
    version: str
    is_active: bool
    created: bool  # True if new record, False if updated existing


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/{prompt_type}/{prompt_key}", response_model=PromptResponse)
async def get_active_prompt(
    prompt_type: str,
    prompt_key: str,
    _user: User = Depends(require_role("methodologist", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Get the currently active prompt by type and key."""
    if prompt_type not in PROMPT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid prompt_type. Valid: {PROMPT_TYPES}")

    result = await db.execute(
        select(PromptVersion)
        .where(
            PromptVersion.prompt_type == prompt_type,
            PromptVersion.prompt_key == prompt_key,
            PromptVersion.is_active == True,  # noqa: E712
        )
        .order_by(PromptVersion.created_at.desc())
        .limit(1)
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    return PromptResponse(
        prompt_type=prompt.prompt_type,
        prompt_key=prompt.prompt_key,
        version=prompt.version,
        content=prompt.content,
        is_active=prompt.is_active,
        metrics=prompt.metrics,
    )


@router.put("/{prompt_type}/{prompt_key}", response_model=PromptUpdateResponse)
async def upsert_prompt(
    prompt_type: str,
    prompt_key: str,
    body: PromptUpdateRequest,
    _user: User = Depends(require_role("methodologist", "admin")),
    db: AsyncSession = Depends(get_db),
):
    """Create or update a prompt version. Methodologist/Admin only."""
    if prompt_type not in PROMPT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid prompt_type. Valid: {PROMPT_TYPES}")

    # Check if exact version exists
    result = await db.execute(
        select(PromptVersion).where(
            PromptVersion.prompt_type == prompt_type,
            PromptVersion.prompt_key == prompt_key,
            PromptVersion.version == body.version,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.content = body.content
        existing.is_active = body.is_active
        if body.metrics is not None:
            existing.metrics = body.metrics
        created = False
    else:
        new_prompt = PromptVersion(
            prompt_type=prompt_type,
            prompt_key=prompt_key,
            version=body.version,
            content=body.content,
            is_active=body.is_active,
            metrics=body.metrics,
        )
        db.add(new_prompt)
        created = True

    await db.commit()

    return PromptUpdateResponse(
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        version=body.version,
        is_active=body.is_active,
        created=created,
    )
