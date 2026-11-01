from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRAFFIC_SURVEILLANCE_",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database: str = "data/surveillance.sqlite3"
    api_key: str | None = None

    @model_validator(mode="after")
    def require_api_key_for_remote_bind(self) -> "Settings":
        if self.host not in {"127.0.0.1", "::1", "localhost"} and not self.api_key:
            raise ValueError("TRAFFIC_SURVEILLANCE_API_KEY is required for remote binding.")
        if self.environment == "production" and not self.api_key:
            raise ValueError("TRAFFIC_SURVEILLANCE_API_KEY is required in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
