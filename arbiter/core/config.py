"""
ARBITER Global Configuration and Settings
"""

from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    app_name: str = "ARBITER"
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    arbiter_secret_key: str = "dev-secret-key-change-in-production"

    # Database
    database_url: str = "sqlite+aiosqlite:///./arbiter.db"

    # MAB (Multi-Armed Bandit) Settings
    mab_default_strategy: str = "auto"
    mab_exploration_rate: float = 0.15
    mab_decay_half_life_hours: float = 72.0
    mab_min_trials: int = 5

    # Provider & Routing Thresholds
    consensus_timeout_seconds: float = 15.0
    stream_multiplexer_min_timeout_seconds: float = 4.0
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_seconds: float = 30.0

    # API Keys (Optional - falls back to Mock if missing)
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    default_fallback_provider: str = "mock"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
