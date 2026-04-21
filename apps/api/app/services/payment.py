"""Payment Service — Stripe & YooKassa integration.

Supports two providers:
  - YooKassa (ЮKassa) — primary for Russian market
  - Stripe — fallback / international

Configuration via env:
  PAYMENT_PROVIDER=yookassa|stripe
  YOOKASSA_SHOP_ID=...
  YOOKASSA_SECRET_KEY=...
  STRIPE_SECRET_KEY=...
  STRIPE_WEBHOOK_SECRET=...
  PAYMENT_RETURN_URL=https://app.xhunter.ru/subscription/success
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Plan pricing (RUB)
# ═══════════════════════════════════════════════════════════════════════════

PLAN_PRICES: dict[str, dict[str, int]] = {
    "ranger": {"monthly": 990, "yearly": 790 * 12},       # Basic
    "hunter": {"monthly": 2490, "yearly": 1990 * 12},     # Pro
    "master": {"monthly": 14900, "yearly": 12900 * 12},   # Enterprise
}

PLAN_DISPLAY_NAMES: dict[str, str] = {
    "scout": "Free",
    "ranger": "Basic",
    "hunter": "Pro",
    "master": "Enterprise",
}


@dataclass
class PaymentSession:
    """Result of creating a payment session."""
    payment_id: str
    confirmation_url: str  # redirect user here
    provider: str          # "yookassa" | "stripe"
    amount: int            # in RUB (kopecks for Stripe)
    plan: str
    period: str            # "monthly" | "yearly"


@dataclass
class PaymentResult:
    """Result of a webhook notification."""
    success: bool
    payment_id: str
    user_id: uuid.UUID | None
    plan: str
    period: str
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# YooKassa integration
# ═══════════════════════════════════════════════════════════════════════════

async def create_yookassa_payment(
    user_id: uuid.UUID,
    plan: str,
    period: str = "monthly",
    return_url: str | None = None,
) -> PaymentSession:
    """Create a YooKassa payment session.

    Requires: pip install yookassa
    Env: YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
    """
    try:
        from yookassa import Configuration, Payment
    except ImportError:
        raise RuntimeError("yookassa package not installed. Run: pip install yookassa")

    Configuration.account_id = settings.yookassa_shop_id
    Configuration.secret_key = settings.yookassa_secret_key

    price = PLAN_PRICES.get(plan, {}).get(period)
    if not price:
        raise ValueError(f"Invalid plan/period: {plan}/{period}")

    idempotency_key = str(uuid.uuid4())
    display_name = PLAN_DISPLAY_NAMES.get(plan, plan)

    payment = Payment.create(
        {
            "amount": {"value": f"{price}.00", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": return_url or settings.payment_return_url,
            },
            "capture": True,
            "description": f"XHUNTER {display_name} ({period})",
            "metadata": {
                "user_id": str(user_id),
                "plan": plan,
                "period": period,
            },
        },
        idempotency_key,
    )

    return PaymentSession(
        payment_id=payment.id,
        confirmation_url=payment.confirmation.confirmation_url,
        provider="yookassa",
        amount=price,
        plan=plan,
        period=period,
    )


async def handle_yookassa_webhook(body: dict) -> PaymentResult:
    """Process YooKassa webhook notification."""
    event_type = body.get("event")
    payment_obj = body.get("object", {})
    payment_id = payment_obj.get("id", "")
    metadata = payment_obj.get("metadata", {})

    user_id_str = metadata.get("user_id")
    plan = metadata.get("plan", "")
    period = metadata.get("period", "monthly")

    if event_type == "payment.succeeded":
        if not user_id_str:
            return PaymentResult(
                success=False, payment_id=payment_id, user_id=None,
                plan=plan, period=period, error="Missing user_id in metadata",
            )
        return PaymentResult(
            success=True,
            payment_id=payment_id,
            user_id=uuid.UUID(user_id_str),
            plan=plan,
            period=period,
        )

    if event_type == "payment.canceled":
        logger.info("Payment %s canceled", payment_id)
        return PaymentResult(
            success=False, payment_id=payment_id,
            user_id=uuid.UUID(user_id_str) if user_id_str else None,
            plan=plan, period=period, error="Payment canceled",
        )

    logger.warning("Unhandled YooKassa event: %s", event_type)
    return PaymentResult(
        success=False, payment_id=payment_id, user_id=None,
        plan=plan, period=period, error=f"Unhandled event: {event_type}",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Stripe integration
# ═══════════════════════════════════════════════════════════════════════════

async def create_stripe_checkout(
    user_id: uuid.UUID,
    plan: str,
    period: str = "monthly",
    return_url: str | None = None,
) -> PaymentSession:
    """Create a Stripe Checkout session.

    Requires: pip install stripe
    Env: STRIPE_SECRET_KEY
    """
    try:
        import stripe
    except ImportError:
        raise RuntimeError("stripe package not installed. Run: pip install stripe")

    stripe.api_key = settings.stripe_secret_key

    price = PLAN_PRICES.get(plan, {}).get(period)
    if not price:
        raise ValueError(f"Invalid plan/period: {plan}/{period}")

    display_name = PLAN_DISPLAY_NAMES.get(plan, plan)
    base_url = return_url or settings.payment_return_url

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "rub",
                "product_data": {"name": f"XHUNTER {display_name} ({period})"},
                "unit_amount": price * 100,  # kopecks
                "recurring": {"interval": "month" if period == "monthly" else "year"},
            },
            "quantity": 1,
        }],
        mode="subscription",
        success_url=f"{base_url}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base_url}?canceled=true",
        metadata={
            "user_id": str(user_id),
            "plan": plan,
            "period": period,
        },
    )

    return PaymentSession(
        payment_id=session.id,
        confirmation_url=session.url,
        provider="stripe",
        amount=price,
        plan=plan,
        period=period,
    )


async def handle_stripe_webhook(payload: bytes, sig_header: str) -> PaymentResult:
    """Process Stripe webhook."""
    try:
        import stripe
    except ImportError:
        raise RuntimeError("stripe package not installed")

    stripe.api_key = settings.stripe_secret_key

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret,
        )
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        return PaymentResult(
            success=False, payment_id="", user_id=None,
            plan="", period="", error=f"Webhook verification failed: {e}",
        )

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        user_id_str = metadata.get("user_id")
        if not user_id_str:
            return PaymentResult(
                success=False, payment_id=session["id"], user_id=None,
                plan="", period="", error="Missing user_id",
            )
        return PaymentResult(
            success=True,
            payment_id=session["id"],
            user_id=uuid.UUID(user_id_str),
            plan=metadata.get("plan", ""),
            period=metadata.get("period", "monthly"),
        )

    return PaymentResult(
        success=False, payment_id="", user_id=None,
        plan="", period="", error=f"Unhandled event: {event['type']}",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Unified interface
# ═══════════════════════════════════════════════════════════════════════════

async def create_payment(
    user_id: uuid.UUID,
    plan: str,
    period: str = "monthly",
    return_url: str | None = None,
) -> PaymentSession:
    """Create payment session using configured provider."""
    provider = getattr(settings, "payment_provider", "yookassa")
    if provider == "stripe":
        return await create_stripe_checkout(user_id, plan, period, return_url)
    return await create_yookassa_payment(user_id, plan, period, return_url)


async def activate_subscription(
    result: PaymentResult,
    db,
) -> None:
    """Activate subscription after successful payment."""
    from sqlalchemy import select
    from app.models.subscription import UserSubscription
    from app.services.entitlement import invalidate_entitlement_cache

    if not result.success or not result.user_id:
        return

    duration = timedelta(days=365) if result.period == "yearly" else timedelta(days=30)
    expires_at = datetime.now(timezone.utc) + duration

    sub_r = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == result.user_id)
    )
    existing = sub_r.scalar_one_or_none()

    if existing:
        existing.plan_type = result.plan
        existing.started_at = datetime.now(timezone.utc)
        existing.expires_at = expires_at
        existing.payment_id = result.payment_id
        existing.payment_provider = "yookassa"  # or "stripe"
    else:
        sub = UserSubscription(
            user_id=result.user_id,
            plan_type=result.plan,
            expires_at=expires_at,
            payment_id=result.payment_id,
            payment_provider="yookassa",
        )
        db.add(sub)

    await db.flush()
    # No explicit commit — get_db() auto-commits on success.
    # This ensures atomicity: if invalidate_entitlement_cache fails,
    # get_db() rollback will undo the subscription change.
    await invalidate_entitlement_cache(result.user_id)
    logger.info("Subscription activated: user=%s plan=%s period=%s", result.user_id, result.plan, result.period)
