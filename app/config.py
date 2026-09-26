from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, sourced from environment variables / .env.

    Never put secrets (API keys, tokens) in source or version control —
    only reference them here as env vars backed by a local .env file.
    """

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LABELFORGE_")

    db_path: str = "./data/labelforge.db"
    user_name: str = "local"

    # Unprefixed, matching the Anthropic SDK's own default env var name.
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-haiku-4-5-20251001"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
