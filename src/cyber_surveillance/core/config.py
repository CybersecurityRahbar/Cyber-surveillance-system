from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CYBER_SURVEILLANCE_",
        env_file=".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    api_key: str | None = None
    max_memory_events: int = Field(default=10_000, ge=100, le=1_000_000)
    auth_failure_threshold: int = Field(default=5, ge=2, le=100)
    auth_failure_window_seconds: int = Field(default=300, ge=10, le=86_400)

    @model_validator(mode="after")
    def require_auth_for_non_local_bind(self) -> "Settings":
        loopback_hosts = {"127.0.0.1", "::1", "localhost"}
        if self.host not in loopback_hosts and not self.api_key:
            raise ValueError(
                "CYBER_SURVEILLANCE_API_KEY is required when binding beyond loopback."
            )
        if self.environment == "production" and not self.api_key:
            raise ValueError("CYBER_SURVEILLANCE_API_KEY is required in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
