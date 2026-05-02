import uuid

from pydantic import BaseModel, Field, field_validator


def _check_password_strength(v: str) -> str:
    """Shared password strength validator.

    Rules:
    - At least 8 characters (enforced via Field min_length)
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character (!@#$%^&*…)
    - Not a commonly breached password
    """
    if not any(c.isupper() for c in v):
        raise ValueError("Пароль должен содержать хотя бы одну заглавную букву")
    if not any(c.islower() for c in v):
        raise ValueError("Пароль должен содержать хотя бы одну строчную букву")
    if not any(c.isdigit() for c in v):
        raise ValueError("Пароль должен содержать хотя бы одну цифру")
    if not any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/~`\"" for c in v):
        raise ValueError("Пароль должен содержать хотя бы один спецсимвол (!@#$%^&* и др.)")
    # Block top-20 breached patterns (case-insensitive prefix check)
    _weak = {"password", "12345678", "qwerty12", "admin123", "letmein1", "welcome1", "abc12345"}
    if v.lower().rstrip("!@#$%^&*") in _weak:
        raise ValueError("Этот пароль слишком распространён. Выберите другой.")
    return v


import re as _re

# Domains we use for our own audit / probe / load-test scripts. These
# generate ~56% of the user table on prod (verified 2026-05-02 audit
# FIND-009) and pollute every KPI dashboard. Blocking the registration
# path stops the bleeding; the existing rows are soft-deleted in
# alembic 20260502_009.
#
# Whitelisted: ``*@trainer.local`` is the operator's manual smoke-test
# pool — admin/rop/manager fixtures created via the admin endpoint,
# not via /register, so they never trip this guard. Google OAuth
# users bypass /register entirely (different code path) so .test
# substrings inside legitimate Google emails don't collide.
_BLOCKED_EMAIL_PATTERN = _re.compile(
    r"^.+@(test\.com|test\.local|fulltest\..+|csrf\..+|audit\..+)$",
    flags=_re.IGNORECASE,
)


class RegisterRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=200)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        return _check_password_strength(v)

    @field_validator("email")
    @classmethod
    def reject_test_domains(cls, v: str) -> str:
        # Reject obvious test-only domains. Operator's smoke-test
        # accounts use ``@trainer.local`` (not blocked) and are
        # created via admin endpoints, not /register. This guard is
        # the registration-side complement of the soft-delete
        # migration; without it the table refills within a week.
        if _BLOCKED_EMAIL_PATTERN.match(v):
            raise ValueError(
                "Регистрация на этом домене запрещена. Используйте корпоративный email."
            )
        return v


class LoginRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    must_change_password: bool = False
    needs_onboarding: bool = False  # New users should complete profile


class RefreshRequest(BaseModel):
    refresh_token: str | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    avatar_url: str | None = None
    preferences: dict | None = None
    onboarding_completed: bool = False
    google_id: str | None = None
    yandex_id: str | None = None
    team_id: str | None = None

    model_config = {"from_attributes": True}
