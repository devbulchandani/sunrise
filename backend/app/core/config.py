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

    llm_provider: str = "openai"  # openai | anthropic
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = ""  # optional OpenAI-compatible gateway (OpenRouter, NIM, ...)
    llm_no_think: bool = False  # prepend /no_think for Nemotron-style reasoning models

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""

    demo_mode: bool = False
    admin_token: str = ""

    # scraping behaviour
    request_timeout: float = 25.0
    min_request_interval_seconds: float = 3.0
    snapshot_retention_per_source: int = 5

    # run live market-context research for events at/above this urgency
    market_research_min_urgency: int = 50

    # healing thresholds
    heal_after_consecutive_failures: int = 2
    min_healing_score: float = 70.0

    # ops alerting: Telegram the owner when pipeline failures spike
    ops_alert_failure_threshold: int = 5
    ops_alert_window_minutes: int = 10
    ops_alert_cooldown_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
