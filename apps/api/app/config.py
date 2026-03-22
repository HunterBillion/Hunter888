import os
import secrets
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

# Resolve .env paths relative to THIS file, not CWD
_THIS_DIR = Path(__file__).resolve().parent  # apps/api/app/
_API_DIR = _THIS_DIR.parent  # apps/api/
_PROJECT_ROOT = _API_DIR.parent.parent  # project root

_ENV_FILES = []
for p in [_API_DIR / ".env", _PROJECT_ROOT / ".env"]:
    if p.exists():
        _ENV_FILES.append(str(p))


class Settings(BaseSettings):
    # Database (no default credentials — must come from .env)
    database_url: str = "postgresql+asyncpg://localhost:5432/trainer_db"
    database_url_sync: str = "postgresql://localhost:5432/trainer_db"

    # Redis (no default password — must come from .env)
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # CSRF
    csrf_secret: str = ""

    # LLM
    claude_api_key: str = ""
    openai_api_key: str = ""
    llm_primary_model: str = "gemini-2.5-flash"
    llm_fallback_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 15
    llm_max_history_messages: int = 20

    # Gemini Direct API (primary for pilot — free 1500 req/day)
    gemini_api_key: str = ""  # Get free: https://aistudio.google.com/apikey
    gemini_model: str = "gemini-2.5-flash"

    # Local LLM (LM Studio / Ollama / CLIProxyAPI — OpenAI-compatible API)
    local_llm_url: str = "http://localhost:8317/v1"
    local_llm_model: str = "gemini-2.5-flash"
    local_llm_enabled: bool = False  # Disabled by default; enable for local dev
    local_llm_api_key: str = ""  # CLIProxyAPI API key — set in .env

    # Concurrency control (prevents API rate limit hits)
    # FIX: 5 was too low for 1000 users/day (~50-100 concurrent).
    # Gemini free tier = 15 RPM; paid tier = 1000+ RPM. Adjust per plan.
    max_concurrent_llm_calls: int = 15

    # Embeddings
    embeddings_service_url: str = "http://localhost:8002"  # Legacy local service
    gemini_embedding_api_key: str = ""  # Free Gemini API key for embeddings
    gemini_embedding_model: str = "gemini-embedding-001"

    # ElevenLabs TTS (natural AI voice for client character)
    elevenlabs_api_key: str = ""  # Get key: https://elevenlabs.io/app/settings/api-keys
    elevenlabs_voice_ids: str = ""  # Comma-separated voice IDs (legacy, used as fallback)
    elevenlabs_voice_ids_male: str = ""  # Comma-separated MALE voice IDs (Russian)
    elevenlabs_voice_ids_female: str = ""  # Comma-separated FEMALE voice IDs (Russian)
    elevenlabs_model: str = "eleven_v3"  # eleven_v3 = best quality, Russian support
    elevenlabs_timeout_seconds: int = 10
    elevenlabs_enabled: bool = False  # Enable when API key is set
    elevenlabs_proxy: str = ""  # HTTP/SOCKS5 proxy for geo-blocked regions, e.g. socks5://127.0.0.1:1080

    @property
    def elevenlabs_voice_list(self) -> list[str]:
        """Parse comma-separated voice IDs into a list (all voices combined)."""
        all_ids = []
        for field in [self.elevenlabs_voice_ids_male, self.elevenlabs_voice_ids_female, self.elevenlabs_voice_ids]:
            if field:
                all_ids.extend(v.strip() for v in field.split(",") if v.strip())
        # Deduplicate while preserving order
        seen = set()
        result = []
        for vid in all_ids:
            if vid not in seen:
                seen.add(vid)
                result.append(vid)
        return result

    @property
    def elevenlabs_male_voices(self) -> list[str]:
        """Parse comma-separated MALE voice IDs."""
        if not self.elevenlabs_voice_ids_male:
            return []
        return [v.strip() for v in self.elevenlabs_voice_ids_male.split(",") if v.strip()]

    @property
    def elevenlabs_female_voices(self) -> list[str]:
        """Parse comma-separated FEMALE voice IDs."""
        if not self.elevenlabs_voice_ids_female:
            return []
        return [v.strip() for v in self.elevenlabs_voice_ids_female.split(",") if v.strip()]

    # Email / SMTP (for password reset etc.)
    smtp_host: str = ""  # e.g. smtp.gmail.com, smtp.yandex.ru
    smtp_port: int = 587
    smtp_user: str = ""  # sender email
    smtp_password: str = ""  # app password (not main password!)
    smtp_from_name: str = "Hunter888"
    smtp_use_tls: bool = True

    @property
    def smtp_configured(self) -> bool:
        """True if SMTP is ready to send."""
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    # STT
    whisper_url: str = "http://localhost:8001"
    whisper_model: str = "large-v3"
    whisper_language: str = "ru"
    whisper_timeout_seconds: int = 30

    # OAuth (Google)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""  # e.g. http://localhost:3000/auth/callback

    # OAuth (Yandex)
    yandex_client_id: str = ""
    yandex_client_secret: str = ""
    yandex_redirect_uri: str = ""  # e.g. http://localhost:3000/auth/callback

    @property
    def google_oauth_configured(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def yandex_oauth_configured(self) -> bool:
        return bool(self.yandex_client_id and self.yandex_client_secret)

    # App
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Web Push (VAPID)
    vapid_public_key: str = ""   # Base64url-encoded VAPID public key
    vapid_private_key: str = ""  # Base64url-encoded VAPID private key
    vapid_subject: str = ""      # mailto: or https:// contact for push service

    @property
    def web_push_configured(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key and self.vapid_subject)

    # Rate Limits
    max_sessions_per_day: int = 10
    max_session_duration_minutes: int = 30
    max_messages_per_session: int = 200

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        values = info.data
        env = values.get("app_env", "development")
        if env == "production" and (not v or v == "change-me-in-production"):
            raise ValueError("JWT_SECRET must be set to a secure value in production")
        if env == "production" and len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters in production")
        # Auto-generate for development if not set
        if not v:
            return secrets.token_hex(32)
        return v

    @field_validator("csrf_secret")
    @classmethod
    def validate_csrf_secret(cls, v: str) -> str:
        if not v:
            return secrets.token_hex(32)
        return v

    model_config = {"env_file": _ENV_FILES or [".env", "../../.env"], "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
