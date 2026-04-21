"""152-FZ personal data consent endpoints."""

import uuid
from datetime import datetime

from app.core.rate_limit import limiter
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


from app.core import errors as err
from app.core.deps import get_current_user
from app.database import get_db
from app.models.user import User, UserConsent


router = APIRouter()

# Required consent types that every user must accept before using the platform
REQUIRED_CONSENTS = [
    {"consent_type": "personal_data_processing", "version": "1.0"},
]


# ── Schemas ──────────────────────────────────────────────────────────────────


class AcceptConsentRequest(BaseModel):
    consent_type: str = Field(
        ..., examples=["personal_data_processing"], description="Type of consent"
    )
    version: str = Field(..., examples=["1.0"], description="Consent document version")


class ConsentRecord(BaseModel):
    id: uuid.UUID
    consent_type: str
    version: str
    accepted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConsentStatusResponse(BaseModel):
    all_accepted: bool
    consents: list[ConsentRecord]
    missing: list[dict]


# ── Endpoints ────────────────────────────────────────────────────────────────


@limiter.limit("10/minute")
@router.post("/", response_model=ConsentRecord, status_code=status.HTTP_201_CREATED)
async def accept_consent(
    body: AcceptConsentRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a consent agreement (e.g. 152-FZ personal data processing)."""
    # Check if this exact consent was already accepted
    existing = await db.execute(
        select(UserConsent).where(
            UserConsent.user_id == user.id,
            UserConsent.consent_type == body.consent_type,
            UserConsent.version == body.version,
            UserConsent.accepted == True,  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=err.CONSENT_ALREADY_ACCEPTED,
        )

    # Determine client IP
    client_ip = request.client.host if request.client else None

    consent = UserConsent(
        user_id=user.id,
        consent_type=body.consent_type,
        version=body.version,
        accepted=True,
        ip_address=client_ip,
    )
    db.add(consent)
    await db.flush()

    return consent


@router.get("/status", response_model=ConsentStatusResponse)
async def get_consent_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check which required consents the user has accepted.

    If any required consent is missing, frontend should redirect user to the consent page.
    """
    # Fetch all user consents
    result = await db.execute(
        select(UserConsent)
        .where(UserConsent.user_id == user.id, UserConsent.accepted == True)  # noqa: E712
        .order_by(UserConsent.created_at.desc())
    )
    user_consents = result.scalars().all()

    # Build lookup of accepted consents: (type, version) -> record
    accepted_lookup: dict[tuple[str, str], UserConsent] = {}
    for c in user_consents:
        key = (c.consent_type, c.version)
        if key not in accepted_lookup:
            accepted_lookup[key] = c

    # Determine missing
    missing = []
    for req in REQUIRED_CONSENTS:
        key = (req["consent_type"], req["version"])
        if key not in accepted_lookup:
            missing.append(req)

    consents_out = [
        ConsentRecord(
            id=c.id,
            consent_type=c.consent_type,
            version=c.version,
            accepted=c.accepted,
            created_at=c.created_at,
        )
        for c in user_consents
    ]

    return ConsentStatusResponse(
        all_accepted=len(missing) == 0,
        consents=consents_out,
        missing=missing,
    )


async def check_consent_accepted(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency that enforces consent acceptance.

    Use as a dependency on routes that require the user to have accepted all required consents.
    Returns 403 with a redirect hint if consent is missing.
    """
    for req in REQUIRED_CONSENTS:
        result = await db.execute(
            select(UserConsent).where(
                UserConsent.user_id == user.id,
                UserConsent.consent_type == req["consent_type"],
                UserConsent.version == req["version"],
                UserConsent.accepted == True,  # noqa: E712
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "message": err.REQUIRED_CONSENT_NOT_ACCEPTED,
                    "missing_consent": req,
                    "redirect": "/consent",
                },
            )
    return user
