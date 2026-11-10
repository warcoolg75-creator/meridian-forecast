from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_SQLITE_URL = f"sqlite:///{(BACKEND_DIR / 'meridian.db').as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # PostgreSQL 17 is the target, e.g. postgresql+psycopg://user:pass@localhost:5432/meridian.
    # When DATABASE_URL is unset we fall back to a SQLite file next to the backend.
    database_url: str = DEFAULT_SQLITE_URL
    # Tests only: a disposable PostgreSQL database for the PG / cross-dialect tests.
    test_database_url: str = ""

    # Signs the JWTs. Set JWT_SECRET anywhere shared or deployed; when it is empty a
    # dev-only key is generated once into backend/.jwt-secret (gitignored).
    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # Phase 6a, external market signals (context only, never a forecasting input).
    # FRED_API_KEY: a free key from fredaccount.stlouisfed.org. Read from .env only and never
    # printed: it travels in the request URL, so app/signals/redact.py masks it everywhere.
    fred_api_key: str = ""
    # Raw API responses, cached outside git. Empty = backend/.cache/signals (gitignored).
    signals_cache_dir: str = ""
    # Wikimedia asks every client to identify itself with a contact.
    # A directory of recorded responses (app/signals/replay.py) served instead of the network.
    signals_replay_dir: str = ""
    signals_user_agent: str = (
        "meridian-forecast/0.6 (https://github.com/warcoolg75-creator; non-commercial college project)"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
