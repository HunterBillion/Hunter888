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
    # 2026-04-18 (FIND-016): 5 → 15 min. At 5-min TTL, 50 active users each
    # generate ~24 refresh/hour → 20 req/s on /auth/refresh, straining
    # Redis SETNX atomic revocation. 15 min cuts that to ~7 req/s while
    # keeping the security window within OWASP recommendation (<30 min).
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7
    # Concurrent refresh grace window: when two tabs / mobile burst fire
    # /auth/refresh with the same refresh_token within this many seconds,
    # the second caller gets the same reissued pair instead of being
    # treated as a replay attack. Outside the window, SETNX loss is
    # replay and the user is blacklisted. 30s covers normal multi-tab
    # and SW prefetch races without widening the attack surface.
    refresh_concurrent_grace_seconds: int = 30

    # CSRF
    csrf_secret: str = ""

    # LLM
    claude_api_key: str = ""
    # 2026-04-21 unified LLM policy (owner directive):
    #   primary   = gpt-5.4           (fast, reliable, default route)
    #   secondary = claude-opus-4.7   (best fallback on navy.api — the
    #                                  highest-tier 4.7 Anthropic model
    #                                  reachable; sonnet-4.7 does NOT
    #                                  exist on navy, only sonnet-4.6)
    # All mini/nano/older models are banned ("остальное мусор").
    # Both routed through navy.api proxy (LOCAL_LLM_URL); direct
    # Anthropic/OpenAI/Gemini keys stay off.
    # Note navy dot-notation: "claude-opus-4.7" not "claude-opus-4-7".
    claude_model: str = "claude-opus-4.7"
    openai_api_key: str = ""
    # 2026-04-21 unified LLM policy — see claude_model docstring.
    llm_primary_model: str = "gpt-5.4"
    llm_fallback_model: str = "claude-opus-4.7"
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
    # Context window of the local LLM — controls when auto-router pushes to cloud.
    # 128K fits Claude/GPT-4/Gemini Pro via navy.api. Set to 6000 for local Gemma 4 (limited).
    local_llm_context_window: int = 128000
    local_embedding_model: str = ""  # Embedding model on local LLM (e.g. "text-embedding-nomic-embed-text-v1.5")
    # Optional separate URL ONLY for embeddings. If empty, embeddings fall back to local_llm_url when local_llm_enabled.
    # Use this to run embeddings on a different Ollama instance (e.g. localhost) while keeping LLM chat on another host (e.g. Mac Mini).
    local_embedding_url: str = ""
    # Optional separate API key for embedding endpoint (e.g. navy.api Bearer key).
    # If empty, falls back to local_llm_api_key (Ollama legacy).
    local_embedding_api_key: str = ""

    # Concurrency control (prevents API rate limit hits)
    max_concurrent_llm_calls: int = 15

    # Hybrid LLM Router
    constitution_enabled: bool = True  # Inject constitution.md into every system prompt
    constitution_path: str = "constitution.md"  # Path relative to prompts/ dir
    llm_auto_cloud_threshold_tokens: int = 5000  # system_prompt > this → prefer cloud
    llm_local_max_tokens_simple: int = 400  # max_tokens for simple/structured tasks on local
    gemini_rpm_limit: int = 15  # Free tier limit, used by RPM counter to avoid 429

    # Lorebook (personality RAG — replaces monolithic character prompts)
    use_lorebook: bool = True  # Feature flag: True=lorebook+RAG (dynamic context), False=old 25K prompts

    # 2026-04-18: Knowledge quiz v2 — case-driven narrative. Off by default,
    # turn on with USE_QUIZ_V2=true in .env. Legacy path stays intact as
    # rollback. See apps/api/app/services/quiz_v2/ + docs/RAG_ARENA_REDESIGN_TZ.md.
    use_quiz_v2: bool = False

    # Tier B (template+LLM fill) and Tier C (full LLM gen) flags — allow
    # disabling individually if LLM billing needs to be capped. When False
    # the router falls back to Tier A seed pool exclusively.
    use_quiz_v2_tier_b: bool = True
    use_quiz_v2_tier_c: bool = True

    # ── Phase 1.5-1.8 (2026-04-18) MCP tool-calling ────────────────────────
    # Off by default: Phase 1 only registers the infrastructure (@tool decorator,
    # ToolRegistry, executor, WS events). Phase 2 flips this to True after
    # ``generate_image`` / ``get_geolocation_context`` / ``fetch_archetype_profile``
    # are implemented and the pilot run smokes clean.
    mcp_enabled: bool = False
    # Hard ceiling on handler execution, independent of per-tool timeouts.
    mcp_tool_timeout_s: int = 30
    # Navy.api settings for the first real MCP tool (image generation).
    # Token kept separate from other LLM keys because navy.api has its own
    # per-key quotas and we want to rotate them independently.
    navy_api_key: str = ""
    navy_base_url: str = "https://api.navy/v1"
    navy_image_model: str = "nano-banana-2"

    # ── Phase 3.5-3.10 (2026-04-19) quality upgrades ───────────────────────
    # Answer-validation second-opinion. When True, knowledge-quiz runs
    # ``knowledge_quiz_validator_v2.validate_semantic`` after the primary
    # judge and upgrades false→partial/equivalent where appropriate.
    rollout_relaxed_validation: bool = False
    # RAG: fetch user-supplied URLs (legalacts.ru/consultant.ru/sudact.ru)
    # into the retrieval pool at query time.
    rag_url_fetch_enabled: bool = True
    # Maximum chars per retrieval chunk (bumped from 3000 → 8000 in Phase 3).
    rag_chunk_max_chars: int = 8000

    lorebook_max_entry_tokens: int = 700  # Max tokens for lorebook entries per turn (baseline+keyword)
    lorebook_max_examples: int = 3  # Max few-shot RAG examples per turn
    lorebook_history_messages: int = 10  # Sliding window size for local LLM

    # ── TZ-1 Unified Client Domain (foundation flags) ─────────────────────
    # Phase 2 (dual-write) is ON by default once the migration is applied.
    # Phase 5 (cutover read path) stays OFF until parity is confirmed.
    client_domain_dual_write_enabled: bool = True
    client_domain_cutover_read_enabled: bool = False
    # Strictness during rollout: when True, any DomainEvent emit failure
    # rolls the whole business transaction back. When False (pilot default),
    # emit failures are logged and the legacy write still commits.
    client_domain_strict_emit: bool = False

    # ── TZ-2 §8 Phase 4 deferred guard flags (default OFF) ────────────────
    # Each guard ships dark, then is enabled per-environment after 24h of
    # observing ``runtime_blocked_starts_total`` on staging. Flip to True
    # via env var (TZ2_GUARD_*_ENABLED=1) → restart api container.
    #
    # * lead_client_access — RBAC on session start. Already enforced inline
    #   at api/training.py:464-475 today; the guard formalises it through
    #   the engine + metrics. Keep OFF here (would double-check); flip ON
    #   only after the inline check is removed.
    # * session_uniqueness — refuses a 2nd active session on the same
    #   (user, real_client). Catches duplicate-tab races. Default OFF
    #   because pilot users sometimes legitimately reopen a hung tab.
    # * runtime_status — refuses to finalize a session that is already
    #   terminal. Belt-and-suspenders to completion_policy idempotent skip.
    # * projection_safe_commit — refuses to finalize when the LeadClient
    #   target is missing/archived (would crash projector mid-finalize).
    tz2_guard_lead_client_access_enabled: bool = False
    tz2_guard_session_uniqueness_enabled: bool = False
    tz2_guard_runtime_status_enabled: bool = False
    tz2_guard_projection_safe_commit_enabled: bool = False

    # ── TZ-4 §10 / §12.3.1 Conversation Policy Engine ─────────────────────
    # The engine ships in WARN-ONLY mode by default — every check produces
    # a `conversation.policy_violation_detected` event for observability,
    # but no message is blocked. The D7 cutover (after 7 days of warn-only
    # data + FP rate < 5%) flips this flag to True per spec §12.3.1.
    #
    # Flip via env var CONVERSATION_POLICY_ENFORCE_ENABLED=1 + restart api.
    conversation_policy_enforce_enabled: bool = False

    # ── Sprint 0 (2026-04-29) Call humanization V2 — staged rollout ───────
    # Master flag for the call-mode realism pipeline:
    #   1) max_tokens really propagates to providers (call default = 300)
    #   2) active_factors / pad_state plumbed into every TTS call site
    #   3) sentence-gate scrubs AI-tells BEFORE chunks reach UI / TTS
    # Default OFF → behaviour is bit-for-bit identical to today. Flip per-env
    # with CALL_HUMANIZED_V2=1; the chat path is never affected.
    call_humanized_v2: bool = False
    # Output budget (in tokens) for call/voice mode when V2 is on. Short by
    # design — long answers in voice always sound like a dictating assistant.
    # Ignored when call_humanized_v2 is off (legacy 800/1200 hardcode wins).
    #
    # 2026-04-29 (Bug 1 fix): dropped from 300 to 80. Field-reported that
    # AI replies were ~8s of audio. 300 tokens × ~1.5 words/token = ~200
    # words ≈ 80s of speech — far too verbose for a phone interaction.
    # 80 tokens ≈ 50-55 words ≈ 15-20s max, with the in-prompt instruction
    # below pushing the model toward 1-2 sentences. Tune up if pilots
    # report mid-sentence cutoffs.
    call_humanized_v2_max_tokens: int = 80
    # Sentence-gate scrub mode for the AI-tell phrase scanner. Three modes:
    #   "warn"  — detect + log + emit WS event, audio still goes through
    #             unchanged. Safe default; collects FP/TP rate for tuning.
    #   "strip" — if the AI-tell sits at the very start of the sentence
    #             (within first ~30 chars), strip it; if the residue is
    #             too short to be a meaningful utterance, drop TTS.
    #   "drop"  — skip TTS for any sentence containing an AI-tell.
    # Only consulted when call_humanized_v2 is on.
    call_humanized_v2_scrub_mode: str = "warn"
    # Bug B fix (auto-opener): when V2 is on AND the session mode is call,
    # the AI sends a short "Алло?" / "Да, слушаю" within the first second
    # so the manager isn't greeted by silence. Defaults to True under V2.
    call_humanized_v2_auto_opener: bool = True

    # ── P0 (2026-04-29) Call Arc — decouple AI from manager script ────────
    # Two-axis architecture: AI gets per-call role (CallArcStep), not per-stage
    # behaviour directives. StageTracker keeps running for scoring/UI.
    # When True: training.py skips StageTracker.build_stage_prompt() injection
    # and uses build_arc_prompt() instead. Reality block is also injected.
    # When False (default): bit-for-bit identical to today.
    call_arc_v1: bool = False
    # When True AND call_arc_v1 is on: inject the always-loaded reality block
    # (apps/api/prompts/reality_ru_2026.md) into the call-mode system prompt.
    # Separate flag so we can A/B the arc and reality independently.
    call_arc_inject_reality: bool = True

    # ── Phase 1 (Roadmap) ConversationCompletionPolicy flags ──────────────
    # When False (default during rollout): legacy terminal side-effect
    # blocks still own the writes; policy only VALIDATES + stamps the new
    # columns. When True (post-parity): policy is authoritative and legacy
    # producers must short-circuit (they will, once strict mode is on).
    # Off initially so every PR pushing wiring is a no-op behavioural
    # change — you can always revert by flipping one env var.
    completion_policy_strict: bool = False
    # Emits a ``DomainEvent`` ``session.completed`` for every finalize()
    # so observability/alerts can track completion cadence even when
    # strict mode is off. Free to keep on — volume is 1 event per session.
    completion_policy_emit_event: bool = True

    # RAG retrieval
    rag_min_similarity: float = 0.40  # Min cosine similarity for RAG retrieval (standard mode)
    rag_min_similarity_blitz: float = 0.35  # Min cosine similarity for blitz mode

    # Embeddings
    embeddings_service_url: str = "http://localhost:8002"  # Legacy local service
    gemini_embedding_api_key: str = ""  # Free Gemini API key for embeddings
    gemini_embedding_model: str = "gemini-embedding-001"

    # ElevenLabs TTS (natural AI voice for client character)
    elevenlabs_api_key: str = ""  # Get key: https://elevenlabs.io/app/settings/api-keys
    # Optional: override ElevenLabs endpoint. Point at a proxy like navy.api
    # (https://api.navy/v1/elevenlabs) to route TTS via an aggregator. Empty
    # string → hit api.elevenlabs.io directly.
    elevenlabs_base_url: str = ""
    elevenlabs_voice_ids: str = ""  # Comma-separated voice IDs (legacy, used as fallback)
    elevenlabs_voice_ids_male: str = ""  # Comma-separated MALE voice IDs (Russian)
    elevenlabs_voice_ids_female: str = ""  # Comma-separated FEMALE voice IDs (Russian)
    elevenlabs_model: str = "eleven_v3"  # eleven_v3 = best quality, Russian support
    elevenlabs_timeout_seconds: int = 10
    elevenlabs_enabled: bool = False  # Enable when API key is set
    # Navy/OpenAI-compat TTS (fallback when ElevenLabs is down/exhausted)
    # Base URL uses local_llm_url if empty. Example: https://api.navy/v1, key = local_llm_api_key.
    navy_tts_enabled: bool = False
    navy_tts_model: str = "tts-1"
    navy_tts_voice: str = "alloy"  # alloy, echo, fable, onyx, nova, shimmer
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
    whisper_api_key: str = ""  # Bearer token for cloud Whisper proxy (navy.api, OpenAI). Empty = self-hosted.

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

    @field_validator("google_redirect_uri", "yandex_redirect_uri")
    @classmethod
    def _validate_oauth_redirect_uri(cls, v: str) -> str:
        """
        OAuth redirect_uri must point to the FRONTEND callback route
        (apps/web/src/app/auth/callback/page.tsx), not the backend API
        endpoint. Google/Yandex redirect the browser back to this URL; the
        page then POSTs the auth code to /api/auth/{provider}/callback.

        Historical pain: prod ran with redirect_uri=.../api/auth/google/callback
        for weeks, causing silent redirect_uri_mismatch 400s that looked like
        random OAuth flakiness. This validator refuses to boot the API with
        an obviously-broken value.
        """
        if not v:
            return v  # empty is fine — code falls back to frontend_url + "/auth/callback"
        if "/api/" in v:
            raise ValueError(
                f"OAuth redirect_uri must NOT contain '/api/' — Google redirects the "
                f"browser to a FRONTEND page, not a backend endpoint. Got: {v!r}. "
                f"Expected shape: https://<your-domain>/auth/callback"
            )
        if not v.rstrip("/").endswith("/auth/callback"):
            raise ValueError(
                f"OAuth redirect_uri must end with '/auth/callback' to match the "
                f"frontend route apps/web/src/app/auth/callback/page.tsx. Got: {v!r}"
            )
        return v

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
    # 2026-04-20: local timezone for daily streak / daily-goal windows.
    # The B2B audience is Russian lawyers — UTC would flip "today" at
    # 03:00 MSK and break streak counting for anyone who does the warm-up
    # after 00:00 MSK. Override via APP_TZ env if needed.
    app_tz: str = "Europe/Moscow"

    # Logging
    log_level: str = "info"
    log_format: str = "text"  # "text" for dev, "json" for production (docker logs)

    # Metrics — 2026-04-18 (FIND-012): gate /metrics behind flag. In production,
    # additionally restrict via nginx IP allowlist (VPN/internal only) so
    # Prometheus-format request-latency and session data does not leak.
    metrics_enabled: bool = False

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

    # Payment (YooKassa / Stripe)
    payment_provider: str = "yookassa"  # "yookassa" | "stripe"
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    payment_return_url: str = "http://localhost:3000/subscription/success"

    @property
    def payment_configured(self) -> bool:
        if self.payment_provider == "stripe":
            return bool(self.stripe_secret_key)
        return bool(self.yookassa_shop_id and self.yookassa_secret_key)

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
        """
        CSRF_SECRET must survive container restarts, otherwise every redeploy
        invalidates all existing csrf_token cookies — every logged-in user gets
        403 on the next POST/PUT/DELETE until they re-login.

        Journal #5 (class A): previously empty CSRF_SECRET fell through to
        `secrets.token_hex(32)` on every process start, producing a fresh
        random value per container. In production this is a silent footgun:
        the app works right after deploy (new secret signs new cookies), but
        any session that predates the deploy breaks until reauth.

        Policy: in production, CSRF_SECRET MUST be set in env and 32+ chars.
        In development, auto-generate with a warning so local work isn't
        blocked.
        """
        env = os.getenv("APP_ENV", "development").lower()
        _placeholders = {
            "",
            "change-me-in-production",
            "change-me-in-production-use-openssl-rand-hex-32",
            "secret",
            "csrf_secret",
            "your-secret-here",
        }
        if env == "production":
            if not v or v.lower().strip() in _placeholders:
                raise ValueError(
                    "CRITICAL: CSRF_SECRET is not set or is using a placeholder value. "
                    "Generate a secure secret with: openssl rand -hex 32 — "
                    "then set it permanently in .env.production (container restarts "
                    "must not re-randomise it or all existing sessions 403 on next POST)."
                )
            if len(v) < 32:
                raise ValueError(
                    f"CSRF_SECRET must be at least 32 characters in production "
                    f"(current: {len(v)} chars). Generate with: openssl rand -hex 32"
                )
            return v
        # Development: warn about placeholder, auto-generate if empty.
        if v and v.lower().strip() in _placeholders:
            import logging
            logging.getLogger(__name__).warning(
                "CSRF_SECRET is a placeholder value — auto-generating. "
                "Set CSRF_SECRET in .env before production deploy."
            )
            return secrets.token_hex(32)
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
            # Database URL must contain password
            from urllib.parse import urlparse
            _db_parsed = urlparse(self.database_url.replace("+asyncpg", ""))
            if not _db_parsed.password:
                issues.append(
                    "CRITICAL: database_url has no password in production. "
                    "Use format: postgresql+asyncpg://user:PASSWORD@host:5432/db"
                )

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

        # Always warn about missing LLM keys — accept navy.api (local_llm_api_key) as valid
        # since platform routes all LLM/embedding/STT/TTS through navy by default.
        _has_any_llm = any([
            self.gemini_api_key,
            self.claude_api_key,
            self.openai_api_key,
            self.local_llm_api_key and self.local_llm_enabled,
        ])
        if not _has_any_llm:
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
