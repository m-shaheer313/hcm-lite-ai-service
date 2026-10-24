"""App settings. Every value comes from environment variables (a local .env file).

The app fails fast at startup if a required variable is missing.
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

# Company rules from the brief (constants, not settings — they do not change per env).
OFFICE_TIMEZONE = "Asia/Karachi"
LATE_AFTER = "09:15"  # office 09:00 + 15 min grace
WEEKEND_DAYS = frozenset({5, 6})  # Saturday=5, Sunday=6
MIN_FULL_DAY_HOURS = 5.0  # less than this is a half day
GROSS_MULTIPLIER_NUM = 3  # gross = 1.5 x basic, kept as 3/2 in integer paisa
GROSS_MULTIPLIER_DEN = 2


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Required: the app refuses to start without these.
    database_url: str
    jwt_secret: str

    # First-run Admin bootstrap (used from Task 3).
    admin_email: str | None = None
    admin_password: str | None = None
    company_name: str = "HCM Lite"

    # Auth
    jwt_expires_minutes: int = 240  # 4 hours; short for a hackathon demo

    # AI settings (used from Task 6 on).
    ai_api_key: str | None = None
    ai_model: str = "gpt-4o-mini"  # small and cheap, per the brief
    ai_timeout_seconds: float = 15.0
    max_turns: int = 5
    max_output_tokens: int = 800
    rate_limit_per_hour: int = 20

    def model_post_init(self, __context: object, /) -> None:
        """Map AI_API_KEY to the env name the OpenAI Agents SDK expects."""
        if self.ai_api_key:
            os.environ.setdefault("OPENAI_API_KEY", self.ai_api_key)


def get_settings() -> Settings:
    """Build Settings from the environment. Raises a clear error if required vars are missing."""
    return Settings()  # type: ignore[call-arg]
