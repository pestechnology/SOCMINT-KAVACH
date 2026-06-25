"""VERTEX configuration — reads .env via pydantic-settings."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings, loaded from environment / .env file."""

    DATA_MODE: Literal["live", "mock"] = "mock"
    DB_PATH: Path = Path("vertex.db")
    LOG_LEVEL: str = "INFO"
    CACHE_ENABLED: bool = True
    CACHE_TTL_HOURS: int = 24
    GITHUB_TOKEN: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
