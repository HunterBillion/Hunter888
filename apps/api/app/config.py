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
    llm_timeout_seconds: int = 60  # Gemma 4 on Ollama: first request ~30s (model swap), then ~10-15s
    llm_max_history_messages: int = 20

    # Gemini Direct API (primary for pilot — free 1500 req/day)
    gemini_api_key: str = ""  # Get free: https://aistudio.google.com/apikey
    gemini_model: str = "gemini-2.5-flash"

    # Local LLM (Ollama / LM Studio / CLIProxyAPI — OpenAI-compatible API)
    local_llm_url: str = "http://localhost:11434/v1"
    local_llm_model: str = "gemma4:e2b"
    local_llm_enabled: bool = False  # Disabled by default; enable for local dev
    local_llm_api_key: str = "ollama"  # Ollama doesn't require key; LM Studio may
    local_embedding_model: str = ""  # Embedding model on local LLM (e.g. "text-embedding-nomic-embed-text-v1.5")

    # Concurrency control (prevents API rate limit hits)
    max_concurrent_llm_calls: int = 15

    # Hybrid LLM Router
    constitution_enabled: bool = True  # Inject constitution.md into every system prompt
    constitution_path: str = "constitution.md"  # Path relative to prompts/ dir
    llm_auto_cloud_threshold_tokens: int = 5000  # system_prompt > this → prefer cloud
    llm_local_max_tokens_simple: int = 400  # max_tokens for simple/structured tasks on local
    gemini_rpm_limit: int = 15  # Free tier limit, used by RPM counter to avoid 429

    # Lorebook (personality RAG — replaces monolithic character prompts)
    use_lorebook: bool = False  # Feature flag: False=old 25K prompts, True=lorebook+RAG
    lorebook_max_entry_tokens: int = 400  # Max tokens for keyword-triggered entries per turn
    lorebook_max_examples: int = 3  # Max few-shot RAG examples per turn
    lorebook_history_messages: int = 10  # Sliding window size for local LLM

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

    # STT Provider: "whisper" (batch, self-hosted) | "deepgram" (streaming, cloud)
    stt_provider: str = "whisper"

    # Deepgram STT (streaming Nova-2)
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-2"
    deepgram_language: str = "ru"

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
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Logging
    log_level: str = "info"
    log_format: str = "text"  # "text" for dev, "json" for production (docker logs)

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: str, info) -> str:
        """In production, warn about overly permissive CORS (many localhost ports, wildcards)."""
        env = info.data.get("app_env", "development")
        if env != "production":
            return v
        origins = [o.strip() for o in v.split(",") if o.strip()]
        localhost_count = sum(1 for o in origins if "localhost" in o or "127.0.0.1" in o)
        if localhost_count > 2:
            import logging
            logging.getLogger(__name__).warning(
                "CORS has %d localhost origins in production — this may be a dev config leak. "
                "Consider restricting to your production domain only.", localhost_count
            )
        return v

    # Web Push (VAPID)
    vapid_public_key: str = ""   # Base64url-encoded VAPID public key
    vapid_private_key: str = ""  # Base64url-encoded VAPID private key
    vapid_subject: str = ""      # mailto: or https:// contact for push service

    @property
    def web_push_configured(self) -> bool:
        return bool(self.vapid_public_key and self.vapid_private_key and self.vapid_subject)

    # Pagination — default/max limits for list endpoints; overridden in .env
    pagination_default_limit: int = 50
    pagination_max_limit: int = 200

    # Rate Limits — safe defaults; overridden in .env
    max_sessions_per_day: int = 10
    max_session_duration_minutes: int = 30
    max_messages_per_session: int = 200

    @field_validator("max_sessions_per_day")
    @classmethod
    def clamp_sessions_limit(cls, v: int, info) -> int:
        env = info.data.get("app_env", "development")
        if env == "production" and v > 500:
            import logging
            logging.getLogger(__name__).error(
                "max_sessions_per_day=%d is dangerously high for production — "
                "clamping to 500 to prevent abuse. Check your .env.", v
            )
            return 500
        return v

    @field_validator("max_messages_per_session")
    @classmethod
    def clamp_messages_limit(cls, v: int, info) -> int:
        env = info.data.get("app_env", "development")
        if env == "production" and v > 1000:
            import logging
            logging.getLogger(__name__).error(
                "max_messages_per_session=%d is dangerously high for production — "
                "clamping to 1000 to prevent abuse. Check your .env.", v
            )
            return 1000
        return v

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        values = info.data
        env = values.get("app_env", "development")

        # Known insecure placeholders that MUST be changed before production
        _INSECURE_PLACEHOLDERS = {
            "",
            "change-me-in-production",
            "change-me-in-production-use-openssl-rand-hex-32",
            "secret",
            "jwt_secret",
            "your-secret-here",
        }

        if env == "production":
            if not v or v.lower().strip() in _INSECURE_PLACEHOLDERS:
                raise ValueError(
                    "CRITICAL: JWT_SECRET is not set or is using a placeholder value. "
                    "Generate a secure secret with: openssl rand -hex 32"
                )
            if len(v) < 32:
                raise ValueError(
                    "JWT_SECRET must be at least 32 characters in production "
                    f"(current: {len(v)} chars). Generate with: openssl rand -hex 32"
                )
        else:
            # Development: warn about placeholder, auto-generate if empty
            if v and v.lower().strip() in _INSECURE_PLACEHOLDERS:
                import logging
                logging.getLogger(__name__).warning(
                    "JWT_SECRET is using a placeholder value — auto-generating a random secret. "
                    "Set a proper JWT_SECRET in .env before deploying to production."
                )
                return secrets.token_hex(32)
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

    def validate_production_readiness(self) -> list[str]:
        """Check all critical settings for production. Returns list of warnings/errors.

        Call during startup to surface configuration issues early.
        """
        import logging
        _log = logging.getLogger(__name__)
        issues: list[str] = []

        if self.app_env == "production":
            # Database credentials
            if "trainer_pass" in self.database_url or "localhost" in self.database_url:
                issues.append("CRITICAL: database_url contains default/localhost credentials")

            # Redis credentials
            if "localhost" in self.redis_url:
                issues.append("CRITICAL: redis_url points to localhost in production")
            # Redis must use authentication in production: redis://:password@host:port/db
            if "@" not in self.redis_url:
                issues.append(
                    "CRITICAL: redis_url has no password in production. "
                    "Use format: redis://:PASSWORD@host:6379/0"
                )

            # Rate limits sanity check
            if self.max_sessions_per_day > 1000:
                issues.append(
                    f"WARNING: max_sessions_per_day={self.max_sessions_per_day} — "
                    "looks like test values leaked to production"
                )
            if self.max_messages_per_session > 1000:
                issues.append(
                    f"WARNING: max_messages_per_session={self.max_messages_per_session} — "
                    "looks like test values leaked to production"
                )

            # Debug mode
            if self.app_debug:
                issues.append("WARNING: app_debug=True in production — Swagger UI and debug info exposed")

            # Rate limiter needs proxy-aware IP resolution
            issues.append(
                "INFO: Rate limiting uses request.client.host — if behind a reverse proxy, "
                "configure uvicorn --forwarded-allow-ips and nginx X-Real-IP header"
            )

        # Always warn about missing LLM keys
        if not self.gemini_api_key and not self.claude_api_key and not self.openai_api_key:
            issues.append("WARNING: No LLM API key configured — AI features will not work")

        for issue in issues:
            if issue.startswith("CRITICAL"):
                _log.error(issue)
            else:
                _log.warning(issue)

        return issues


settings = Settings()
# Run startup validation
settings.validate_production_readiness()
