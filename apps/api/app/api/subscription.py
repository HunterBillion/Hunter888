"""Subscription & Entitlement API — S3-03.

Endpoints:
  GET  /subscription            — current plan, usage, limits
  GET  /subscription/plans      — plan comparison for pricing page
  POST /subscription/upgrade    — upgrade plan (pilot: direct, prod: payment)
  POST /subscription/checkout   — create payment session (YooKassa/Stripe)
  POST /subscription/webhook/yookassa  — YooKassa webhook
  POST /subscription/webhook/stripe    — Stripe webhook
"""

import ipaddress
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


class UpgradeRequest(BaseModel):
    plan: str  # "ranger", "hunter", "master"
    payment_token: str | None = None  # Future: Stripe/YooKassa token


class CheckoutRequest(BaseModel):
    plan: str         # "ranger", "hunter", "master"
    period: str = "monthly"  # "monthly" | "yearly"


@router.get("")
async def get_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current subscription status, usage counters, and limits."""
    from app.services.entitlement import get_entitlement

    ent = await get_entitlement(user.id, db)

    return {
        "plan": ent.plan.value,
        "is_trial": ent.is_trial,
        "trial_days_remaining": ent.trial_days_remaining,
        "is_seed_account": ent.is_seed_account,
        "expires_at": ent.subscription_expires.isoformat() if ent.subscription_expires else None,
        "usage": {
            "sessions_today": ent.sessions_used_today,
            "sessions_limit": ent.limits.sessions_per_day,
            "pvp_today": ent.pvp_used_today,
            "pvp_limit": ent.limits.pvp_matches_per_day,
            "rag_today": ent.rag_used_today,
            "rag_limit": ent.limits.rag_queries_per_day,
        },
        "features": {
            "ai_coach": ent.limits.ai_coach,
            "wiki_full_access": ent.limits.wiki_full_access,
            "export_reports": ent.limits.export_reports,
            "voice_cloning": ent.limits.voice_cloning,
            "team_management": ent.limits.team_management,
            "team_challenge": ent.limits.team_challenge,
            "priority_matchmaking": ent.limits.priority_matchmaking,
            "analytics": ent.limits.analytics,
            "tournaments": ent.limits.tournaments,
            "llm_priority": ent.limits.llm_priority.value,
        },
    }


@router.get("/plans")
async def get_plans():
    """Get plan comparison data for pricing page. Public endpoint."""
    from app.services.entitlement import get_plan_comparison
    return {"plans": get_plan_comparison()}


@router.post("/upgrade")
@limiter.limit("5/minute")
async def upgrade_plan(
    body: UpgradeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upgrade user's subscription plan.

    For now: direct upgrade without payment (pilot mode).
    When payment is integrated: validate payment_token → create subscription.
    """
    from app.models.subscription import UserSubscription, PlanType
    from app.services.entitlement import PlanType as EntPlanType, PLAN_LIMITS

    # Validate plan
    try:
        target_plan = EntPlanType(body.plan)
    except ValueError:
        raise HTTPException(400, f"Invalid plan: {body.plan}. Valid: scout, ranger, hunter, master")

    if target_plan == EntPlanType.scout:
        raise HTTPException(400, "Cannot downgrade to Scout via upgrade endpoint")

    # Check if user already has this or higher plan
    sub_r = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    existing = sub_r.scalar_one_or_none()

    plan_order = {EntPlanType.scout: 0, EntPlanType.ranger: 1, EntPlanType.hunter: 2, EntPlanType.master: 3}

    if existing:
        try:
            current = EntPlanType(existing.plan_type)
            if plan_order.get(current, 0) >= plan_order.get(target_plan, 0):
                raise HTTPException(400, f"Already on {current.value} plan (same or higher)")
        except ValueError:
            pass

        # Update existing subscription
        existing.plan_type = target_plan.value
        existing.started_at = datetime.now(timezone.utc)
        existing.expires_at = None  # Unlimited for pilot
        existing.payment_id = body.payment_token
    else:
        # Create new subscription
        sub = UserSubscription(
            user_id=user.id,
            plan_type=target_plan.value,
            expires_at=None,  # Unlimited for pilot
            payment_id=body.payment_token,
        )
        db.add(sub)

    await db.flush()
    await db.commit()

    from app.services.entitlement import invalidate_entitlement_cache
    await invalidate_entitlement_cache(user.id)

    limits = PLAN_LIMITS[target_plan]

    return {
        "status": "upgraded",
        "plan": target_plan.value,
        "sessions_per_day": limits.sessions_per_day,
        "pvp_per_day": limits.pvp_matches_per_day,
        "message": f"Subscription upgraded to {target_plan.value}. Enjoy!",
    }


# ═══════════════════════════════════════════════════════════════════════════
# Payment integration (YooKassa / Stripe)
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/checkout")
@limiter.limit("10/minute")
async def create_checkout(
    body: CheckoutRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a payment checkout session. Returns confirmation URL."""
    from app.services.payment import create_payment, PLAN_PRICES

    if not settings.payment_configured:
        raise HTTPException(
            status_code=503,
            detail="Платёжная система не настроена. Обратитесь к администратору.",
        )
    if body.plan not in PLAN_PRICES:
        raise HTTPException(400, f"Invalid plan: {body.plan}. Valid: ranger, hunter, master")
    if body.period not in ("monthly", "yearly"):
        raise HTTPException(400, "Period must be 'monthly' or 'yearly'")

    try:
        session = await create_payment(user.id, body.plan, body.period)
        return {
            "payment_id": session.payment_id,
            "confirmation_url": session.confirmation_url,
            "provider": session.provider,
            "amount": session.amount,
            "plan": session.plan,
            "period": session.period,
        }
    except Exception as e:
        logger.error("Payment creation failed: %s", e)
        raise HTTPException(500, "Payment service unavailable")


# YooKassa webhook IP whitelist (https://yookassa.ru/developers/using-api/webhooks)
_YOOKASSA_IP_RANGES = (
    "185.71.76.0/27",
    "185.71.77.0/27",
    "77.75.153.0/25",
    "77.75.156.11/32",
    "77.75.156.35/32",
    "77.75.154.128/25",
)


def _is_yookassa_ip(ip: str) -> bool:
    """Check if request IP belongs to YooKassa's official IP ranges."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for cidr in _YOOKASSA_IP_RANGES:
        try:
            if addr in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue
    return False


@router.post("/webhook/yookassa")
async def yookassa_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """YooKassa webhook — payment.succeeded / payment.canceled.

    Security: validates source IP against YooKassa whitelist in production.
    """
    client_ip = request.headers.get("X-Real-IP") or (
        request.client.host if request.client else ""
    )
    if settings.app_env == "production" and not _is_yookassa_ip(client_ip):
        logger.warning("YooKassa webhook rejected: untrusted IP %s", client_ip)
        raise HTTPException(403, "Forbidden")

    body = await request.json()
    event_type = body.get("event")
    payment_id = body.get("object", {}).get("id", "")
    logger.info("YooKassa webhook: event=%s payment=%s ip=%s", event_type, payment_id, client_ip)

    from app.services.payment import handle_yookassa_webhook, activate_subscription

    result = await handle_yookassa_webhook(body)
    if result.success:
        await activate_subscription(result, db)
        return {"status": "ok"}
    return {"status": "ignored", "reason": result.error}


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Stripe webhook — checkout.session.completed."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    logger.info("Stripe webhook received")

    from app.services.payment import handle_stripe_webhook, activate_subscription

    result = await handle_stripe_webhook(payload, sig_header)
    if result.success:
        await activate_subscription(result, db)
        return {"status": "ok"}
    return {"status": "ignored", "reason": result.error}
