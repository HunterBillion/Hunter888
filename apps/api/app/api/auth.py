from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

import redis.asyncio as aioredis

from app.config import settings
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
from fastapi.responses import JSONResponse

from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


def _set_auth_cookies(response: JSONResponse, tokens: TokenResponse) -> JSONResponse:
    """Set httpOnly cookies for access and refresh tokens."""
    is_prod = settings.app_env == "production"
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
    return response


def _clear_auth_cookies(response: JSONResponse) -> JSONResponse:
    """Clear auth cookies on logout."""
    for key in ("access_token", "refresh_token", "vh_authenticated"):
        response.delete_cookie(key=key, path="/")
    return response


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()

    tokens = _create_tokens(str(user.id))
    response = JSONResponse(content=tokens.model_dump(), status_code=201)
    return _set_auth_cookies(response, tokens)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(request: Request, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    # Clear any blacklist from previous logout so new login works
    try:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis.delete(f"blacklist:user:{user.id}")
        await redis.aclose()
    except Exception:
        pass  # Non-blocking — login should work even if Redis hiccups

    tokens = _create_tokens(str(user.id))
    tokens.must_change_password = user.must_change_password
    response = JSONResponse(content=tokens.model_dump())
    return _set_auth_cookies(response, tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload["sub"]

    # Check if user was logged out (token blacklisted)
    from app.core.deps import _is_user_blacklisted
    if await _is_user_blacklisted(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please login again.",
        )

    tokens = _create_tokens(user_id)
    response = JSONResponse(content=tokens.model_dump())
    return _set_auth_cookies(response, tokens)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User = Depends(get_current_user)):
    """Invalidate the current user's refresh token by blacklisting in Redis."""
    try:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        # Blacklist the user's tokens for the duration of refresh token lifetime
        ttl = settings.jwt_refresh_token_expire_days * 86400
        await redis.setex(f"blacklist:user:{user.id}", ttl, "1")
        await redis.aclose()
    except Exception:
        pass  # Logout should not fail even if Redis is down
    response = JSONResponse(content=None, status_code=204)
    return _clear_auth_cookies(response)


def _create_tokens(user_id: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token({"sub": user_id}),
        refresh_token=create_refresh_token({"sub": user_id}),
    )


# ─── Password reset ─────────────────────────────────────────────────────────

import logging as _logging

_auth_logger = _logging.getLogger(__name__)


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


from pydantic import BaseModel, Field


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)


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
        # Generate reset token
        reset_token = secrets.token_urlsafe(32)

        # Store in Redis: token → user_id, 1 hour TTL
        try:
            redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await redis.setex(f"reset_token:{reset_token}", 3600, str(user.id))
            await redis.aclose()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service temporarily unavailable",
            )

        reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"
        await _send_reset_email(body.email, user.full_name or body.email, reset_url)

    # Always return success (don't reveal if email exists)
    return {"message": "Если указанный email зарегистрирован, на него отправлена ссылка для сброса пароля."}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password using token from email link."""
    # Look up token in Redis
    try:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        user_id_str = await redis.get(f"reset_token:{body.token}")
        if user_id_str:
            await redis.delete(f"reset_token:{body.token}")  # One-time use
        await redis.aclose()
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service temporarily unavailable")

    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ссылка для сброса пароля недействительна или истекла.",
        )

    import uuid
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    db.add(user)
    await db.commit()

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
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.setex(f"oauth_state:{state_key}", 300, "1")
        await r.aclose()
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service temporarily unavailable")

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
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + "&".join(f"{k}={v}" for k, v in params.items())
    return {"url": url, "state": state_key}


@router.post("/google/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def google_callback(request: Request, body: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)):
    """Exchange Google auth code for tokens, find or create user."""
    if not settings.google_oauth_configured:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Google OAuth не настроен")

    # Validate OAuth state to prevent CSRF
    if not body.state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OAuth state parameter")
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await r.get(f"oauth_state:{body.state}")
        await r.delete(f"oauth_state:{body.state}")
        await r.aclose()
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service temporarily unavailable")
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state (possible CSRF)")

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ошибка авторизации Google")
        token_data = token_resp.json()

        # Get user info
        userinfo_resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось получить профиль Google")
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
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.setex(f"oauth_state:{state_key}", 300, "1")
        await r.aclose()
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service temporarily unavailable")

    redirect_uri = settings.yandex_redirect_uri or f"{settings.frontend_url}/auth/callback"
    params = {
        "client_id": settings.yandex_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "state": state_key,
    }
    url = "https://oauth.yandex.ru/authorize?" + "&".join(f"{k}={v}" for k, v in params.items())
    return {"url": url, "state": state_key}


@router.post("/yandex/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def yandex_callback(request: Request, body: OAuthCallbackRequest, db: AsyncSession = Depends(get_db)):
    """Exchange Yandex auth code for tokens, find or create user."""
    if not settings.yandex_oauth_configured:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Yandex OAuth не настроен")

    # Validate OAuth state to prevent CSRF
    if not body.state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OAuth state parameter")
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        stored = await r.get(f"oauth_state:{body.state}")
        await r.delete(f"oauth_state:{body.state}")
        await r.aclose()
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service temporarily unavailable")
    if not stored:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state (possible CSRF)")

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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ошибка авторизации Yandex")
        token_data = token_resp.json()

        # Get user info
        userinfo_resp = await client.get(
            "https://login.yandex.ru/info?format=json",
            headers={"Authorization": f"OAuth {token_data['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не удалось получить профиль Yandex")
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
) -> TokenResponse:
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
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.delete(f"blacklist:user:{user.id}")
        await r.aclose()
    except Exception:
        pass

    return _create_tokens(str(user.id))


# --- Disconnect OAuth provider ---

@router.post("/{provider}/disconnect")
async def disconnect_oauth(
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
    return {"message": f"{provider.capitalize()} отвязан от аккаунта"}
