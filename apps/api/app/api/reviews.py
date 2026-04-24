"""Reviews API — public submission with moderation queue."""

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, require_role, security
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.review import Review
from app.models.user import User
from app.services.content_filter import filter_user_input

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Schemas ────────────────────────────────────────────────────────────


class ReviewCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    role: str = Field(..., min_length=2, max_length=200)
    text: str = Field(..., min_length=10, max_length=2000)
    rating: int = Field(5, ge=1, le=5)


class ReviewOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str
    text: str
    rating: int
    approved: bool
    deleted: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReviewPublic(BaseModel):
    """Lighter schema for public carousel — no id/approved."""
    name: str
    role: str
    text: str
    rating: int

    class Config:
        from_attributes = True


# ── Public endpoints ───────────────────────────────────────────────────


@router.get("/reviews", response_model=list[ReviewPublic])
async def get_approved_reviews(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Get approved, non-deleted reviews for the landing page carousel."""
    result = await db.execute(
        select(Review).where(  # noqa: E712
            Review.approved == True,
            Review.deleted == False,
        )
        .order_by(Review.created_at.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all()


async def get_optional_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
    access_token: str | None = Cookie(default=None),
) -> User | None:
    """Return the current user when a valid token is present, otherwise anonymous.

    The landing review form is public. Invalid or expired visitor cookies must not
    turn a moderated public submission into a 401.
    """
    try:
        return await get_current_user(
            request=request,
            credentials=credentials,
            db=db,
            access_token=access_token,
        )
    except HTTPException:
        return None


# ── Public submission endpoint ─────────────────────────────────────────


@router.post("/reviews", status_code=201)
@limiter.limit("3/minute")
async def create_review(
    request: Request,
    body: ReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
):
    """Submit a new review. Public endpoint; always goes to moderation queue."""
    filtered_text, violations = filter_user_input(body.text)
    if violations:
        logger.warning(
            "Review from user %s filtered: %s",
            user.id if user else "anonymous",
            violations,
        )

    filtered_name, _ = filter_user_input(body.name)
    filtered_role, _ = filter_user_input(body.role)

    review = Review(
        name=filtered_name,
        role=filtered_role,
        text=filtered_text,
        rating=body.rating,
        approved=False,
        user_id=user.id if user else None,
    )
    db.add(review)
    await db.commit()
    return {"status": "ok", "message": "Отзыв отправлен на модерацию"}


# ── Admin endpoints ────────────────────────────────────────────────────


@router.get("/reviews/pending", response_model=list[ReviewOut])
async def get_pending_reviews(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Admin-only: list reviews awaiting moderation (paginated)."""
    result = await db.execute(
        select(Review).where(  # noqa: E712
            Review.approved == False,
            Review.deleted == False,
        )
        .order_by(Review.created_at.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.get("/reviews/all", response_model=list[ReviewOut])
async def get_all_reviews(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """Admin-only: list all reviews, including pending and hidden."""
    result = await db.execute(
        select(Review)
        .order_by(Review.created_at.desc())
        .limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.patch("/reviews/{review_id}/approve", status_code=200)
async def approve_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Admin-only: approve a pending review and make it public."""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.approved = True
    review.deleted = False
    await db.commit()
    await db.refresh(review)
    return review


@router.patch("/reviews/{review_id}/reject", status_code=200)
async def reject_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Admin-only: return a review back to the moderation queue."""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    review.approved = False
    review.deleted = False
    await db.commit()
    await db.refresh(review)
    return review


# ── Delete (hide) endpoint ───────────────────────────────────────────

@router.delete("/reviews/{review_id}", status_code=200)
async def delete_review(
    review_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    """Admin-only: hide a review (soft delete)."""
    result = await db.execute(select(Review).where(Review.id == review_id))
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    review.approved = False
    review.deleted = True
    await db.commit()
    return {"status": "ok", "message": "Отзыв скрыт"}
