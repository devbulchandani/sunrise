from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),  # later files take precedence
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://sunrise:sunrise@localhost:5432/sunrise"
    redis_url: str = "redis://localhost:6379"

    llm_provider: str = "openai"  # openai | anthropic | bedrock
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""  # optional OpenAI-compatible gateway (OpenRouter, NIM, ...)
    llm_bedrock_region: str = "us-east-1"
    llm_no_think: bool = False  # prepend /no_think for Nemotron-style reasoning models

    # Cognito protects future account/trading APIs; public market-data reads remain public.
    cognito_region: str = "us-east-1"
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    trading_enabled: bool = False

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""

    demo_mode: bool = False
    admin_token: str = ""
    # Comma-separated Cognito emails allowed to use admin/debug endpoints.
    # The frontend never receives an admin secret; it authenticates with the
    # user's Cognito access token instead.
    admin_emails: str = ""

    # Browser origins allowed to call the API directly (the Worker strips
    # Origin, so this only affects direct access).
    cors_origins: str = (
        "https://sunrise-dashboard.pages.dev,"
        "http://localhost:5173,http://127.0.0.1:5173"
    )

    # scraping behaviour
    request_timeout: float = 25.0
    min_request_interval_seconds: float = 3.0
    snapshot_retention_per_source: int = 5
    article_retention_days: int = 30
    event_retention_days: int = 30
    source_lock_seconds: int = 300

    # run live market-context research for events at/above this urgency
    market_research_min_urgency: int = 50

    # clustering
    clustering_candidate_limit: int = 500
    clustering_similarity_threshold: float = 66.0
    clustering_jaccard_floor: float = 0.3

    # notification floors (anti-spam)
    telegram_min_urgency: int = 61
    email_min_urgency: int = 41

    # healing thresholds
    heal_after_consecutive_failures: int = 2
    min_healing_score: float = 70.0
    healing_stale_minutes: int = 30

    # analysis retries
    analysis_max_attempts: int = 5

    # ops alerting: Telegram the owner when pipeline failures spike
    ops_alert_failure_threshold: int = 5
    ops_alert_window_minutes: int = 10
    ops_alert_cooldown_minutes: int = 30
    ops_source_failure_threshold: int = 5

    @property
    def admin_email_set(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.admin_emails.split(",")
            if email.strip()
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
