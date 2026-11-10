"""Running the signals pipeline on recorded responses (tests/fixtures/signals/).

The fixtures were recorded from the live APIs by tools/record_signal_fixtures.py, on a
trimmed catalog and a short window. Replaying them needs the same clock and start, which
recording.json keeps. Nothing here opens a socket: the conftest guard would refuse it.
"""

import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.models import FetchMode
from app.signals.catalog import Catalog, build_catalog
from app.signals.pipeline import Runner
from app.signals.replay import ReplayTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "signals"
FAKE_FRED_KEY = "f4kefredkey0123456789abcdefghijk"  # 32 characters, like a real key, planted by the tests


def recording() -> tuple[datetime, date]:
    data = json.loads((FIXTURES / "recording.json").read_text(encoding="utf-8"))
    return datetime.fromisoformat(data["recorded_at"]), date.fromisoformat(data["start"])


def catalog_data() -> dict:
    return json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))


def test_catalog(data: dict | None = None) -> Catalog:
    return build_catalog(data or catalog_data())


test_catalog.__test__ = False  # a helper, not a test


def settings(tmp_path: Path, **overrides) -> Settings:
    values = dict(fred_api_key=FAKE_FRED_KEY, signals_cache_dir=str(tmp_path / "signals-cache"),
                  database_url="sqlite://", test_database_url="", jwt_secret="test")
    values.update(overrides)
    return Settings(_env_file=None, **values)


def runner(engine: Engine, tmp_path: Path, mode: FetchMode = FetchMode.BACKFILL, *, catalog: Catalog | None = None,
           replay: ReplayTransport | None = None, **settings_overrides) -> Runner:
    now, start = recording()
    replay = replay or ReplayTransport(FIXTURES)
    return Runner(sessions=sessionmaker(bind=engine, expire_on_commit=False),
                  settings=settings(tmp_path, **settings_overrides), mode=mode, catalog=catalog or test_catalog(),
                  transport=lambda _source: replay, clock=lambda: now, start=start, sleep=lambda _s: None)
