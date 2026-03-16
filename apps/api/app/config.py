from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://trainer:trainer_pass@localhost:5432/trainer_db"
    database_url_sync: str = "postgresql://trainer:trainer_pass@localhost:5432/trainer_db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # LLM
    claude_api_key: str = ""
    openai_api_key: str = ""
    llm_primary_model: str = "claude-sonnet-4-20250514"
    llm_fallback_model: str = "gpt-4o-mini"
    llm_timeout_seconds: int = 5
    llm_max_history_messages: int = 20

    # STT
    whisper_url: str = "http://localhost:8001"
    whisper_model: str = "large-v3"
    whisper_language: str = "ru"

    # App
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    # Rate Limits
    max_sessions_per_day: int = 10
    max_session_duration_minutes: int = 30
    max_messages_per_session: int = 200

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
