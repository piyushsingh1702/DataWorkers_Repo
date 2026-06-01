import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Compass API
    compass_api_key: str = ""
    base_url: str = "https://api.core42.ai/v1"

    # Paths
    database_path: str = "app/database/sample.db"
    output_dir: str = "app/outputs"

    # App
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def db_path(self) -> Path:
        return Path(self.database_path)

    @property
    def outputs_path(self) -> Path:
        p = Path(self.output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
