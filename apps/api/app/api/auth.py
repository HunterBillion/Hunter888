import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.rate_limit import limiter

from app.config import settings
from app.core import errors as err
from app.core.redis_pool import get_redis

_logger = logging.getLogger(__name__)
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models.user import User
from app.models.subscription import UserSubscription, PlanType
from fastapi.responses import JSONResponse

from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


def _make_csrf_token() -> str:
    """Generate a CSRF token using a cryptographically random value.

    Uses secrets.token_hex so each session gets a unique token.
    The csrf_secret in settings is used as an extra entropy source via HMAC.
    """
    import secrets as _sec
    import hmac as _hmac
    import hashlib as _hs
    nonce = _sec.token_hex(16)
    sig = _hmac.new(
        settings.csrf_secret.encode(),
        nonce.encode(),
        _hs.sha256,
    ).hexdigest()
    return f"{nonce}.{sig}"


def _set_auth_cookies(response: JSONResponse, tokens: TokenResponse) -> JSONResponse:
    """Set httpOnly cookies for access and refresh tokens + CSRF token cookie.

    Also injects ``csrf_token`` into the JSON response body so the frontend can
    set the cookie via ``document.cookie`` — cross-origin ``Set-Cookie`` headers
    are silently dropped by browsers when port differs (localhost:3000 → :8000).
    """
    is_prod = settings.app_env == "production"
    csrf_value = _make_csrf_token()

    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=settings.jwt_access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=is_prod,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/api/auth/refresh",
    )
    # Marker cookie for middleware/JS — NOT httpOnly so frontend can check presence
    response.set_cookie(
        key="vh_authenticated",
        value="1",
        httponly=False,
        secure=is_prod,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/",
    )
    # CSRF token cookie — NOT httpOnly (frontend JS must be able to read and send it).
    # Validated by CSRFMiddleware on state-changing requests via X-CSRF-Token header.
    response.set_cookie(
        key="csrf_token",
        value=csrf_value,
        httponly=False,
        secure=is_prod,
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 86400,
        path="/",
    )

    # Inject csrf_token into response body so frontend can set it via document.cookie
    # (cross-origin Set-Cookie is unreliable between localhost:3000 and :8000).
    import json as _json
    body = _json.loads(response.body)
    body["csrf_token"] = csrf_value
    response.body = _json.dumps(body).encode()
    # Update Content-Length to match new body
    response.headers["content-length"] = str(len(response.body))

    return response


def _clear_auth_cookies(response: JSONResponse) -> JSONResponse:
    """Clear auth cookies on logout.

    IMPORTANT: Each cookie must be deleted with the SAME path it was set with,
    otherwise the browser won't recognize the deletion and the cookie persists.
    """
    response.delete_cookie(key="access_token", path="/")
    # refresh_token is set with path="/api/auth/refresh" — must match for deletion
    response.delete_cookie(key="refresh_token", path="/api/auth/refresh")
    response.delete_cookie(key="vh_authenticated", path="/")
    response.delete_cookie(key="csrf_token", path="/")
    return response


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy.exc import IntegrityError

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        _logger.warning(
            "auth.register.duplicate email=%s ip=%s",
            body.email, request.client.host if request.client else "unknown",
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err.EMAIL_ALREADY_REGISTERED)

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        preferences={},  # Required: should be filled via onboarding
    )
    db.add(user)
    # Race-safe: if two concurrent requests pass the check above,
    # the DB UNIQUE constraint on email catches the second insert.
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err.EMAIL_ALREADY_REGISTERED)

    # Auto-create free-tier subscription in the same transaction.
    # Without this, entitlement checks find no active subscription and block
    # access to training / RAG features for brand-new users.
    subscription = UserSubscription(
        user_id=user.id,
        plan_type=PlanType.scout.value,  # free forever — scout tier
        expires_at=None,  # no expiry for free tier
    )
    db.add(subscription)
    await db.flush()
    await db.commit()

    _logger.info(
        "auth.register.success user_id=%s email=%s plan=%s ip=%s",
        user.id, body.email, PlanType.scout.value,
        request.client.host if request.client else "unknown",
    )
    tokens = await _create_tokens(str(user.id), user.role)
    # New users need onboarding to fill required profile fields
    response_data = tokens.model_dump()
    response_data["needs_onboarding"] = True
    response = JSONResponse(content=response_data, status_code=201)
    return _set_auth_cookies(response, tokens)


_LOGIN_FAIL_MAX = 5
_LOGIN_FAIL_TTL = 15 * 60  # 15 minutes in seconds


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    _ip = request.client.host if request.client else "unknown"
    _lockout_key = f"login_fail:{body.email}"

    # Check if account is locked out due to too many failed attempts
    try:
        r = get_redis()
        fail_count = await r.get(_lockout_key)
        if fail_count is not None and int(fail_count) >= _LOGIN_FAIL_MAX:
            _logger.warning(
                "auth.login.locked email=%s ip=%s",
                body.email, _ip,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Аккаунт временно заблокирован. Попробуйте через 15 минут",
            )
    except aioredis.RedisError as exc:
        _logger.warning("Redis error checking login lockout for %s: %s", body.email, exc)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Timing attack mitigation: always run verify_password even if user doesn't exist.
    # bcrypt.checkpw takes ~100ms; skipping it on non-existent users leaks email existence.
    _DUMMY_HASH = "$2b$12$LJ3m4ys3Lg2FEOn.0dRG9eKPlDFtMiAqfZIbXYMQKxNBb1DRPGLXK"
    _pw_valid = verify_password(body.password, user.hashed_password if user else _DUMMY_HASH)
    if not user or not _pw_valid:
        # Increment failed login counter in Redis
        try:
            r = get_redis()
            pipe = r.pipeline()
            pipe.incr(_lockout_key)
            pipe.expire(_lockout_key, _LOGIN_FAIL_TTL)
            await pipe.execute()
        except aioredis.RedisError as exc:
            _logger.warning("Redis error incrementing login failures for %s: %s", body.email, exc)

        _logger.warning(
            "auth.login.failed email=%s ip=%s reason=invalid_credentials",
            body.email, _ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=err.INVALID_CREDENTIALS
        )

    if not user.is_active:
        _logger.warning(
            "auth.login.failed email=%s ip=%s reason=account_disabled",
            body.email, _ip,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err.ACCOUNT_DISABLED)

    # Clear failed login attempts on successful login
    try:
        r = get_redis()
        await r.delete(_lockout_key)
    except aioredis.RedisError as exc:
        _logger.warning("Redis error clearing login failures for %s: %s", body.email, exc)

    # Clear any blacklist from previous logout so new login works
    try:
        r = get_redis()
        await r.delete(f"blacklist:user:{user.id}")
    except aioredis.RedisError as exc:
        _logger.warning("Redis error clearing blacklist on login for user %s: %s", user.id, exc)

    _logger.info(
        "auth.login.success user_id=%s email=%s ip=%s",
        user.id, body.email, _ip,
    )

    # Record fingerprint for multi-account detection
    try:
        from app.services.anti_cheat import record_fingerprint
        _ua = request.headers.get("user-agent")
        await record_fingerprint(user_id=user.id, ip_address=_ip, user_agent=_ua, event_type="login", db=db)
        await db.commit()
    except Exception:
        _logger.debug("Failed to record login fingerprint for %s", user.id)

    tokens = await _create_tokens(str(user.id), user.role)
    tokens.must_change_password = user.must_change_password
    response = JSONResponse(content=tokens.model_dump())
    return _set_auth_cookies(response, tokens)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh(request: Request, body: RefreshRequest | None = None, db: AsyncSession = Depends(get_db)):
    # Accept refresh token from JSON body OR httpOnly cookie (page reload fallback).
    token = (body.refresh_token if body and body.refresh_token else None) or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err.INVALID_REFRESH_TOKEN)
    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err.INVALID_REFRESH_TOKEN)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=err.INVALID_REFRESH_TOKEN)
    old_jti = payload.get("jti")

    from app.core.deps import _is_user_blacklisted

    if await _is_user_blacklisted(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=err.TOKEN_REVOKED_RELOGIN,
        )

    # Atomic revocation gate: use SETNX to atomically check-and-revoke the old
    # refresh token in a single Redis call. This eliminates the TOCTOU race
    # where two concurrent refresh requests could both pass a separate
    # _is_token_revoked() check before either writes the revocation key.
    #
    # Concurrent-refresh grace window (A10 v2): multi-tab browsers, mobile
    # background fetches, and SW prefetch can legitimately race two refreshes
    # with the same refresh_token within a few hundred ms. To avoid
    # blacklisting a legitimate user the winner reserves the cache slot
    # IMMEDIATELY with a "PENDING" sentinel (before the slow DB lookup +
    # token creation) so concurrent losers see it and poll, instead of
    # racing past an empty cache and triggering replay-detect. Once the
    # winner finishes it overwrites the slot with the real reissued pair.
    # Outside the grace window SETNX loss remains a true replay.
    r = None
    ttl = settings.jwt_refresh_token_expire_days * 86400
    grace = settings.refresh_concurrent_grace_seconds
    reissued_key = f"token:reissued:{old_jti}" if old_jti else None
    _PENDING = "PENDING"

    if old_jti:
        try:
            r = get_redis()
            was_set = await r.set(f"token:revoked:{old_jti}", "1", nx=True, ex=ttl)
        except aioredis.RedisError as exc:
            _logger.error(
                "auth.refresh.redis_error jti=%s: %s — denying refresh (fail closed)",
                old_jti, exc,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=err.SERVICE_TEMPORARILY_UNAVAILABLE,
            )

        if was_set:
            # Winner — reserve the cache slot BEFORE doing the slow DB lookup
            # so concurrent losers can poll instead of falling through to
            # blacklist when they read an empty cache.
            try:
                await r.setex(reissued_key, grace, _PENDING)
            except aioredis.RedisError:
                # Cache reservation failure is non-critical — losers within
                # the same Redis-down window will see _is_user_blacklisted
                # check fail closed earlier and not reach here.
                pass
        else:
            # Loser — SETNX failed. Either a concurrent legitimate refresh
            # is in flight (cache holds PENDING or final payload), or this
            # is a true replay after the grace window expired (cache empty).
            cached_str = await _wait_for_reissued_pair(r, reissued_key)

            if cached_str is not None and cached_str != _PENDING:
                try:
                    cached_tokens = TokenResponse.model_validate_json(cached_str)
                except Exception as exc:
                    _logger.warning(
                        "auth.refresh.cache_decode_fail jti=%s: %s",
                        old_jti, exc,
                    )
                    cached_tokens = None
                if cached_tokens is not None:
                    _logger.info(
                        "auth.refresh.concurrent_grace_hit user_id=%s jti=%s",
                        user_id, old_jti,
                    )
                    response = JSONResponse(content=cached_tokens.model_dump())
                    return _set_auth_cookies(response, cached_tokens)

            _logger.warning(
                "auth.refresh.replay_detected user_id=%s jti=%s — blacklisting user",
                user_id, old_jti,
            )
            try:
                await r.setex(f"blacklist:user:{user_id}", ttl, "1")
            except aioredis.RedisError:
                pass
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=err.TOKEN_REVOKED_RELOGIN,
            )

    # Fetch current role and must_change_password from DB for the new access token
    from app.models.user import User as UserModel
    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    db_user = result.scalar_one_or_none()
    user_role = db_user.role if db_user else "manager"
    must_change = db_user.must_change_password if db_user else False

    tokens = await _create_tokens(user_id, user_role)
    tokens.must_change_password = must_change

    # Winner publishes the real reissued pair so any in-flight losers
    # finish their poll loop and return it.
    if r is not None and reissued_key:
        try:
            await r.setex(reissued_key, grace, tokens.model_dump_json())
        except aioredis.RedisError:
            pass

    response = JSONResponse(content=tokens.model_dump())
    return _set_auth_cookies(response, tokens)


async def _wait_for_reissued_pair(
    r,
    reissued_key: str,
    *,
    max_attempts: int = 25,
    sleep_seconds: float = 0.08,
) -> str | None:
    """Poll the reissued cache slot for up to ~2s, waiting for the SETNX
    winner to publish its token pair.

    Returns the cached JSON payload, the literal "PENDING" sentinel
    (caller should treat as "no payload yet"), or None on Redis failure
    / true cache-miss (true replay).

    25 × 80ms ≈ 2s is shorter than the network round-trip for most
    real refreshes from mobile, and bounded so a slow winner doesn't
    pin a request thread forever.
    """
    cached_str: str | None = None
    for _ in range(max_attempts):
        try:
            raw = await r.get(reissued_key)
        except aioredis.RedisError:
            return None
        if raw is None:
            return cached_str
        cached_str = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
        if cached_str != "PENDING":
            return cached_str
        await asyncio.sleep(sleep_seconds)
    return cached_str


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    payload = {c.name: getattr(user, c.name) for c in user.__table__.columns}
    payload["team_id"] = str(user.team_id) if user.team_id else None
    return UserResponse.model_validate(payload)


@limiter.limit("10/minute")
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, user: User = Depends(get_current_user)):
    """Invalidate the current user's refresh token by blacklisting in Redis."""
    try:
        r = get_redis()
        # Blacklist the user's tokens for the duration of refresh token lifetime
        ttl = settings.jwt_refresh_token_expire_days * 86400
        await r.setex(f"blacklist:user:{user.id}", ttl, "1")
    except aioredis.RedisError as exc:
        _logger.error("Redis error during logout blacklist for user %s: %s", user.id, exc)
    _logger.info(
        "auth.logout user_id=%s ip=%s",
        user.id, request.client.host if request.client else "unknown",
    )
    response = JSONResponse(content=None, status_code=204)
    return _clear_auth_cookies(response)


async def _create_tokens(user_id: str, role: str = "manager") -> TokenResponse:
    from app.core.security import get_role_version
    rv = await get_role_version(user_id)
    return TokenResponse(
        access_token=create_access_token({"sub": user_id, "role": role}, role_version=rv),
        refresh_token=create_refresh_token({"sub": user_id}),
    )


# ─── Password reset ─────────────────────────────────────────────────────────

_auth_logger = _logger  # alias for backward compat within this module


async def _send_reset_email(to_email: str, user_name: str, reset_url: str) -> None:
    """Send password-reset email via SMTP. Falls back to logging if SMTP not configured."""
    if not settings.smtp_configured:
        _auth_logger.warning(
            "SMTP not configured — reset link logged instead of emailed. "
            "Set SMTP_HOST / SMTP_USER / SMTP_PASSWORD in .env to enable email."
        )
        _auth_logger.info("Password reset link for %s: %s", to_email, reset_url)
        return

    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    subject = "Сброс пароля — Hunter888"
    html_body = (
        f"<p>Здравствуйте, {user_name}!</p>"
        f"<p>Вы запросили сброс пароля. Перейдите по ссылке ниже (действительна 1 час):</p>"
        f'<p><a href="{reset_url}">{reset_url}</a></p>'
        f"<p>Если вы не запрашивали сброс — просто проигнорируйте это письмо.</p>"
        f"<p>— Команда Hunter888</p>"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_user}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
        )
        _auth_logger.info("Reset email sent to %s", to_email)
    except Exception as exc:
        _auth_logger.error("Failed to send reset email to %s: %s", to_email, exc)
        # Still log the link as fallback so the reset isn't lost
        _auth_logger.info("Fallback — reset link for %s: %s", to_email, reset_url)


from pydantic import BaseModel, Field, field_validator


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        from app.schemas.auth import _check_password_strength
        return _check_password_strength(v)


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Request password reset link. Sends email with reset token.

    Always returns 200 regardless of whether email exists (prevents enumeration).
    Token stored in Redis with 1-hour TTL.
    """
    import secrets

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user:
        # Generate reset token, store HASH in Redis (token itself goes to email)
        import hashlib
        reset_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(reset_token.encode()).hexdigest()

        # Store hash → user_id in Redis, 1 hour TTL
        try:
            r = get_redis()
            await r.setex(f"reset_token:{token_hash}", 3600, str(user.id))
        except aioredis.RedisError as exc:
            _logger.error("Redis error storing reset token: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=err.SERVICE_TEMPORARILY_UNAVAILABLE,
            )

        reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"
        await _send_reset_email(body.email, user.full_name or body.email, reset_url)

    # Always return success (don't reveal if email exists)
    return {"message": "Если указанный email зарегистрирован, на него отправлена ссылка для сброса пароля."}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using token from email link."""
    # Look up token hash in Redis (only hash is stored, not the token)
    import hashlib
    token_hash = hashlib.sha256(body.token.encode()).hexdigest()
    try:
        r = get_redis()
        # Atomic GET+DELETE via Lua to prevent TOCTOU race condition:
        # two concurrent requests could both read the same token before either deletes it.
        _lua_get_del = """
        local val = redis.call("GET", KEYS[1])
        if val then
            redis.call("DEL", KEYS[1])
            return val
        else
            return nil
        end
        """
        user_id_str = await r.eval(_lua_get_del, 1, f"reset_token:{token_hash}")
    except aioredis.RedisError as exc:
        _logger.error("Redis error during password reset: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=err.SERVICE_TEMPORARILY_UNAVAILABLE)

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка для сброса пароля недействительна или истекла.",
        )

    import uuid
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.USER_NOT_FOUND)

    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    db.add(user)
    await db.commit()

    # Blacklist all existing tokens so user must re-login with new password
    try:
        r = get_redis()
        await r.setex(f"blacklist:user:{user.id}", 7 * 24 * 3600, "password_changed")
    except aioredis.RedisError as exc:
        _logger.warning("Redis error blacklisting user after password reset %s: %s", user.id, exc)

    _logger.info("auth.password_reset.success user_id=%s", user.id)
    return {"message": "Пароль успешно изменён. Войдите с новым паролем."}


# ─── OAuth ───────────────────────────────────────────────────────────────────

import httpx
import secrets as _secrets


class OAuthCallbackRequest(BaseModel):
    code: str = Field(..., min_length=1)
    state: str | None = None


# --- OAuth status (tells frontend which providers are configured) ---

@router.get("/oauth/status")
async def oauth_status():
    """Return which OAuth providers are configured."""
    return {
        "google": settings.google_oauth_configured,
        "yandex": settings.yandex_oauth_configured,
    }


# --- Google OAuth ---

@router.get("/google/login")
async def google_login():
    """Generate Google OAuth consent URL."""
    if not settings.google_oauth_configured:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google OAuth не настроен")

    state = _secrets.token_urlsafe(32)
    state_key = f"google:{state}"

    # Store state in Redis for CSRF validation (5 min TTL)
    try:
        r = get_redis()
        await r.setex(f"oauth_state:{state_key}", 300, "1")
    except aioredis.RedisError as exc:
        _logger.error("Redis error storing Google OAuth state: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=err.SERVICE_TEMPORARILY_UNAVAILABLE)

    redirect_uri = settings.google_redirect_uri or f"{settings.frontend_url}/auth/callback"
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state_key,
        "access_type": "offline",
        "prompt": "consent",
    }
    from urllib.parse import urlencode
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"url": url, "state": state_key}


@router.post("/google/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def google_callback(request: Request, body: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)):
    """Exchange Google auth code for tokens, find or create user."""
    if not settings.google_oauth_configured:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google OAuth не настроен")

    # Validate OAuth state to prevent CSRF
    if not body.state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.MISSING_OAUTH_STATE)
    try:
        r = get_redis()
        stored = await r.get(f"oauth_state:{body.state}")
        await r.delete(f"oauth_state:{body.state}")
    except aioredis.RedisError as exc:
        _logger.error("Redis error validating Google OAuth state: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=err.SERVICE_TEMPORARILY_UNAVAILABLE)
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.INVALID_OAUTH_STATE)

    redirect_uri = settings.google_redirect_uri or f"{settings.frontend_url}/auth/callback"

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": body.code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            _body_preview = token_resp.text[:500]
            _logger.warning(
                "oauth.google.token_exchange_failed status=%s redirect_uri=%s body=%s",
                token_resp.status_code, redirect_uri, _body_preview,
            )
            # Parse Google's structured error body so the UI can show the
            # real reason (redirect_uri_mismatch / invalid_client / etc.)
            # instead of a generic message.
            _provider_error: str | None = None
            _provider_error_description: str | None = None
            try:
                _pj = token_resp.json()
                _provider_error = _pj.get("error")
                _provider_error_description = _pj.get("error_description")
            except Exception:  # noqa: BLE001
                pass
            _hint_ru = {
                "redirect_uri_mismatch": (
                    f"redirect_uri, отправленный на Google ({redirect_uri!r}), не совпадает "
                    "ни с одним из Authorized redirect URIs в Google OAuth Client. "
                    "Добавь именно это значение в Console или обнови GOOGLE_REDIRECT_URI в .env."
                ),
                "invalid_client": "GOOGLE_CLIENT_ID или GOOGLE_CLIENT_SECRET не совпадают с Console.",
                "invalid_grant": "Код авторизации устарел или уже использовался. Попробуй ещё раз.",
                "unauthorized_client": "OAuth-клиенту запрещён grant_type=authorization_code.",
            }.get(_provider_error or "", None)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "oauth_exchange_failed",
                    "provider": "google",
                    "provider_status": token_resp.status_code,
                    "provider_error": _provider_error,
                    "provider_error_description": _provider_error_description,
                    "redirect_uri_sent": redirect_uri,
                    "message": (
                        _hint_ru
                        or _provider_error_description
                        or "Google отклонил запрос. См. provider_error для деталей."
                    ),
                },
            )
        token_data = token_resp.json()

        # Get user info
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            _logger.warning(
                "oauth.google.userinfo_failed status=%s body=%s",
                userinfo_resp.status_code, userinfo_resp.text[:300],
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "oauth_userinfo_failed",
                    "provider": "google",
                    "provider_status": userinfo_resp.status_code,
                    "message": "Не удалось получить профиль Google",
                },
            )
        userinfo = userinfo_resp.json()

    google_id = userinfo.get("id")
    email = userinfo.get("email", "")
    name = userinfo.get("name", email.split("@")[0])

    if not google_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google не вернул ID пользователя")

    return await _oauth_find_or_create(db, provider="google", provider_id=google_id, email=email, name=name)


# --- Yandex OAuth ---

@router.get("/yandex/login")
async def yandex_login():
    """Generate Yandex OAuth consent URL."""
    if not settings.yandex_oauth_configured:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Yandex OAuth не настроен")

    state = _secrets.token_urlsafe(32)
    state_key = f"yandex:{state}"

    # Store state in Redis for CSRF validation (5 min TTL)
    try:
        r = get_redis()
        await r.setex(f"oauth_state:{state_key}", 300, "1")
    except aioredis.RedisError as exc:
        _logger.error("Redis error storing Yandex OAuth state: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=err.SERVICE_TEMPORARILY_UNAVAILABLE)

    redirect_uri = settings.yandex_redirect_uri or f"{settings.frontend_url}/auth/callback"
    params = {
        "client_id": settings.yandex_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state_key,
    }
    from urllib.parse import urlencode
    url = "https://oauth.yandex.ru/authorize?" + urlencode(params)
    return {"url": url, "state": state_key}


@router.post("/yandex/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def yandex_callback(request: Request, body: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)):
    """Exchange Yandex auth code for tokens, find or create user."""
    if not settings.yandex_oauth_configured:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Yandex OAuth не настроен")

    # Validate OAuth state to prevent CSRF
    if not body.state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.MISSING_OAUTH_STATE)
    try:
        r = get_redis()
        stored = await r.get(f"oauth_state:{body.state}")
        await r.delete(f"oauth_state:{body.state}")
    except aioredis.RedisError as exc:
        _logger.error("Redis error validating Yandex OAuth state: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=err.SERVICE_TEMPORARILY_UNAVAILABLE)
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.INVALID_OAUTH_STATE)

    redirect_uri = settings.yandex_redirect_uri or f"{settings.frontend_url}/auth/callback"

    # Exchange code for tokens
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            "https://oauth.yandex.ru/token",
            data={
                "code": body.code,
                "client_id": settings.yandex_client_id,
                "client_secret": settings.yandex_client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if token_resp.status_code != 200:
            _body_preview = token_resp.text[:500]
            _logger.warning(
                "oauth.yandex.token_exchange_failed status=%s redirect_uri=%s body=%s",
                token_resp.status_code, redirect_uri, _body_preview,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "oauth_exchange_failed",
                    "provider": "yandex",
                    "provider_status": token_resp.status_code,
                    "message": "Ошибка авторизации Yandex. Проверьте redirect_uri в настройках OAuth-клиента.",
                },
            )
        token_data = token_resp.json()

        # Get user info
        userinfo_resp = await client.get(
            "https://login.yandex.ru/info?format=json",
            headers={"Authorization": f"OAuth {token_data['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            _logger.warning(
                "oauth.yandex.userinfo_failed status=%s body=%s",
                userinfo_resp.status_code, userinfo_resp.text[:300],
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "oauth_userinfo_failed",
                    "provider": "yandex",
                    "provider_status": userinfo_resp.status_code,
                    "message": "Не удалось получить профиль Yandex",
                },
            )
        userinfo = userinfo_resp.json()

    yandex_id = userinfo.get("id")
    email = userinfo.get("default_email", "")
    name = userinfo.get("real_name") or userinfo.get("display_name") or email.split("@")[0]

    if not yandex_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Yandex не вернул ID пользователя")

    return await _oauth_find_or_create(db, provider="yandex", provider_id=yandex_id, email=email, name=name)


# --- Shared OAuth user lookup/creation ---

async def _oauth_find_or_create(
    db: AsyncSession, provider: str, provider_id: str, email: str, name: str,
) -> JSONResponse:
    """Find existing user by OAuth provider ID or email, or create new user."""
    provider_col = User.google_id if provider == "google" else User.yandex_id

    # 1) Try to find by provider ID
    result = await db.execute(select(User).where(provider_col == provider_id))
    user = result.scalar_one_or_none()

    if not user and email:
        # 2) Try to find by email and link account
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user:
            setattr(user, f"{provider}_id", provider_id)
            db.add(user)
            await db.flush()

    if not user:
        # 3) Create new user (OAuth users don't need password)
        user = User(
            email=email or f"{provider}_{provider_id}@oauth.local",
            hashed_password=hash_password(_secrets.token_urlsafe(32)),
            full_name=name,
            **{f"{provider}_id": provider_id},
        )
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Аккаунт деактивирован")

    # Clear blacklist for fresh login
    try:
        r = get_redis()
        await r.delete(f"blacklist:user:{user.id}")
    except aioredis.RedisError as exc:
        _logger.warning("Redis error clearing blacklist during OAuth for user %s: %s", user.id, exc)

    tokens = await _create_tokens(str(user.id), user.role)
    response = JSONResponse(content=tokens.model_dump())
    return _set_auth_cookies(response, tokens)


# --- Disconnect OAuth provider ---

@limiter.limit("5/minute")
@router.post("/{provider}/disconnect")
async def disconnect_oauth(
    request: Request,
    provider: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink an OAuth provider from the current account."""
    if provider not in ("google", "yandex"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Неизвестный провайдер")

    current_value = getattr(user, f"{provider}_id")
    if not current_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Провайдер не привязан")

    setattr(user, f"{provider}_id", None)
    db.add(user)
    await db.commit()
    return {"message": f"{provider.capitalize()} отвязан от аккаунта"}
