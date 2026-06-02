import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Compass API
    compass_api_key: str = ""
    base_url: str = "https://api.core42.ai/v1"

    # Paths
    database_path: str = "app/database/sample.db"
    database_dir: str = "app/database"
    default_db_name: str = "sample"
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

    def outputs_path_for(self, db_name: str | None) -> Path:
        """Return a per-database output directory under ``output_dir``.

        Outputs are isolated per registered database so multiple DBs can be
        analysed without overwriting each other's artifacts.
        """
        name = db_name or self.default_db_name
        p = Path(self.output_dir) / name
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
