from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_SQLITE_URL = f"sqlite:///{(BACKEND_DIR / 'meridian.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # PostgreSQL 16 is the target, e.g. postgresql+psycopg://user:pass@localhost:5432/meridian.
    # When DATABASE_URL is unset we fall back to a SQLite file next to the backend.
    database_url: str = DEFAULT_SQLITE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()
