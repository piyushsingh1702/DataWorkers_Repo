import os
from pathlib import Path

from pydantic_settings import BaseSettings


def _resolve_env_files() -> tuple[str, ...]:
    """Decide which dotenv files Pydantic should load.

    Reads ``MODE`` (from the real environment first, falling back to the
    committed ``.env``) and:

    * ``MODE=local``  → load ``.env`` then ``.env.local``. Values in
      ``.env.local`` (including ``COMPASS_API_KEY``) win.
    * anything else → load only ``.env``. The ``COMPASS_API_KEY`` set there
      is used as-is.
    """
    mode = os.environ.get("MODE")
    if mode is None:
        # Tiny manual parse of `.env` so we can read MODE before
        # pydantic-settings even constructs the Settings object.
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key.strip() == "MODE":
                    mode = value.strip().strip('"').strip("'")
                    break
    mode = (mode or "").lower()
    if mode == "local":
        return (".env", ".env.local")
    return (".env",)


class Settings(BaseSettings):
    # Resolution mode (local vs anything else); see _resolve_env_files.
    mode: str = "prod"

    # Compass API
    compass_api_key: str = ""
    base_url: str = "https://api.core42.ai/v1"

    # Paths
    database_path: str = "app/database/sample.db"
    database_dir: str = "app/database"
    default_db_name: str = "sample"
    output_dir: str = "app/outputs"
    log_dir: str = "logs"

    # App
    log_level: str = "INFO"

    # Inter-agent completeness gate. Each agent's output is scored 0..1; if
    # the score is below this threshold the orchestrator halts the pipeline
    # and publishes the issues rather than feeding a degraded artifact into
    # the next agent. Override via env var ``COMPLETENESS_THRESHOLD``.
    completeness_threshold: float = 0.8

    class Config:
        # Files are evaluated left-to-right; later files override earlier ones.
        env_file = _resolve_env_files()
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

    @property
    def logs_path(self) -> Path:
        p = Path(self.log_dir)
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
