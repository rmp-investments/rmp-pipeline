"""
Configuration settings using Pydantic.

Loads settings from environment variables and .env file.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./pipeline.db"

    # API Keys
    anthropic_api_key: str = ""

    # Gmail Settings
    gmail_email: str = ""
    gmail_app_password: str = ""

    # File Paths
    properties_dir: str = ""
    template_excel: str = ""

    # Authentication
    secret_key: str = "your-secret-key-change-in-production"
    access_token_expire_minutes: int = 1440  # 24 hours
    basic_auth_username: str = "rmp"
    basic_auth_password: str = "change-this-password"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # CORS - include Render URLs for production
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://rmp-pipeline-frontend.onrender.com",
        "https://rmp-pipeline-api.onrender.com",
    ]

    @property
    def async_database_url(self) -> str:
        """Convert database URL to async version if needed."""
        url = self.database_url
        if url.startswith("sqlite://"):
            return url.replace("sqlite://", "sqlite+aiosqlite://")
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://")
        return url

    @property
    def properties_path(self) -> Path:
        """Return properties directory as Path object."""
        return Path(self.properties_dir) if self.properties_dir else Path(".")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
