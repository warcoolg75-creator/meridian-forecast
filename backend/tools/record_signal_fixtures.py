"""Record the API responses the signals tests replay (tests/fixtures/signals/).

    cd backend && python tools/record_signal_fixtures.py

Runs the real pipeline on a trimmed catalog (2 cities, 2 FRED series, 2 articles, 1 news
topic) as of a fixed moment, CLOCK (1 Dec 2023, from START), into a throwaway SQLite
database: a backfill, then a refresh twice. Every distinct request is recorded once (a
repeat is answered from the recording, so the second refresh sees exactly what the first
did), with its URL stored without the FRED key.

- Open-Meteo, FRED and Wikimedia are fetched live.
- GDELT is never fetched live here. It blocks an address for hours after a few quick
  requests (2026-11-10), so its answers come from the pipeline's own raw cache
  (backend/.cache/signals/gdelt/, written by a real backfill, URLs and bodies as received).
  CLOCK and START are chosen so that the trimmed catalog asks exactly the requests the
  2026-11-10 backfill made for Kitchen Appliances: October and November 2023. A request
  the cache cannot answer fails the recording.
- GDELT bodies under the record cap keep their 6 newest articles (a capped window would
  keep everything, so the replay splits it the same way).
- FRED's real answer to an unregistered key is recorded once, for the redaction test.

Needs FRED_API_KEY in .env.
"""

import json
import shutil
import sys
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import BACKEND_DIR, get_settings  # noqa: E402
from app.db import create_db_engine  # noqa: E402
from app.models import FetchMode, FetchStatus  # noqa: E402
from app.signals.catalog import CATALOG_PATH, build_catalog  # noqa: E402
from app.signals.pipeline import Runner  # noqa: E402
from app.signals.replay import canonical  # noqa: E402

OUT = BACKEND_DIR / "tests" / "fixtures" / "signals"
RAW_CACHE = BACKEND_DIR / ".cache" / "signals"
START = date(2023, 10, 9)  # the backfill start: the first day of the sales history
CLOCK = datetime(2023, 12, 1, tzinfo=UTC)  # "now" for the recorded runs
CITIES = {"IN-DL-NDL", "IN-TN-CHE"}
SERIES = {"fred.PCOPPUSDM", "fred.DCOILBRENTEU", "wiki.Diwali", "wiki.Evaporative_cooler"}
TOPICS = {"Kitchen Appliances"}
FROM_CACHE_ONLY = {"api.gdeltproject.org"}
KEEP_ARTICLES = 6


def trimmed_catalog() -> dict:
    import fnmatch

    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    data["weather"]["cities"] = [c for c in data["weather"]["cities"] if c["region"] in CITIES]
    data["series"] = [s for s in data["series"] if s["key"] in SERIES]
    data["news"]["topics"] = [t for t in data["news"]["topics"] if t["category"] in TOPICS]
    data["news"]["window_months"] = 1  # the cached GDELT answers are monthly windows
    keys = {s["key"] for s in data["series"]} | {
        f"weather.{v['key']}.{c['region']}" for v in data["weather"]["variables"] for c in data["weather"]["cities"]}
    mappings = []
    for m in data["mappings"]:
        series = [p for p in m["series"] if fnmatch.filter(sorted(keys), p)]
        if series:
            mappings.append({**m, "series": series})
    data["mappings"] = mappings
    data["about"] = "Trimmed copy of app/signals/catalog.json for the tests (tools/record_signal_fixtures.py)."
    return data


def cached_answers() -> dict[str, tuple[int, bytes]]:
    """Every response in the raw cache, by canonical request (the cache stores URLs redacted)."""
    out: dict[str, tuple[int, bytes]] = {}
    for index in RAW_CACHE.glob("*/*/index.jsonl"):
        for line in index.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            body = index.parent / entry["file"]
            if body.exists():
                out[canonical("GET", entry["url"].replace("api_key=***", ""))] = (entry["status"], body.read_bytes())
    return out


class Recorder(httpx.BaseTransport):
    def __init__(self, cached: dict[str, tuple[int, bytes]]):
        self.live = httpx.HTTPTransport()
        self.cached = cached
        self.entries: dict[str, dict] = {}
        self.bodies: dict[str, bytes] = {}
        self.unanswered: list[str] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        key = canonical(request.method, str(request.url))
        if key not in self.entries:
            if request.url.host in FROM_CACHE_ONLY:
                if key not in self.cached:
                    self.unanswered.append(key)
                    return httpx.Response(599, text="not in the raw cache", request=request)
                status, content = self.cached[key]
            else:
                response = self.live.handle_request(request)
                response.read()
                status, content = response.status_code, response.content
            source = request.url.host.split(".")[-2]
            name = f"responses/{source}-{len(self.entries) + 1:03d}.json"
            self.entries[key] = {"request": key, "status": status, "file": name}
            self.bodies[key] = content
        entry = self.entries[key]
        return httpx.Response(entry["status"], content=self.bodies[key], request=request)


def migrate(url: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["configure_logger"] = False
    engine = create_db_engine(url)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()


def trim_gdelt(body: bytes, cap: int) -> bytes:
    text = body.decode("utf-8", errors="replace").strip()
    if not text.startswith("{"):
        return body
    data = json.loads(text, strict=False)
    articles = data.get("articles", [])
    if len(articles) >= cap:
        return body
    data["articles"] = sorted(articles, key=lambda a: a.get("seendate", ""), reverse=True)[:KEEP_ARTICLES]
    return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")


def main() -> int:
    settings = get_settings()
    if not settings.fred_api_key:
        print("FRED_API_KEY is not set in .env", file=sys.stderr)
        return 1
    catalog_data = trimmed_catalog()
    catalog = build_catalog(catalog_data)
    recorder = Recorder(cached_answers())
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        url = f"sqlite:///{(Path(tmp) / 'record.db').as_posix()}"
        migrate(url)
        engine = create_db_engine(url)
        sessions = sessionmaker(bind=engine, expire_on_commit=False)
        quiet = settings.model_copy(update={"signals_cache_dir": str(Path(tmp) / "cache")})
        try:
            for mode in (FetchMode.BACKFILL, FetchMode.REFRESH, FetchMode.REFRESH):
                reports = Runner(sessions=sessions, settings=quiet, mode=mode, catalog=catalog,
                                 transport=lambda _s: recorder, clock=lambda: CLOCK, start=START,
                                 sleep=lambda _s: None, progress=print).run()
                failed = [r.source for r in reports if r.status is not FetchStatus.OK]
                if failed:  # never replace good fixtures with an outage or a gap in the cache
                    print(f"Not recorded: {', '.join(failed)} did not succeed ({mode.value}); "
                          f"unanswered from the cache: {recorder.unanswered}", file=sys.stderr)
                    return 1
        finally:
            engine.dispose()

        bad = httpx.get(catalog.file.fred.url, params=dict(series_id="DCOILBRENTEU", api_key="0" * 32,
                                                           file_type="json"), timeout=30)

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "responses").mkdir(parents=True)
    cap = catalog.file.news.max_records
    for key, entry in recorder.entries.items():
        body = recorder.bodies[key]
        if "gdeltproject" in key:
            body = trim_gdelt(body, cap)
        (OUT / entry["file"]).write_bytes(body)
    manifest = {"about": "Recorded by tools/record_signal_fixtures.py; URLs without the FRED key. GDELT "
                         "answers come from a real backfill's raw cache (2026-11-10).",
                "responses": list(recorder.entries.values())}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    (OUT / "catalog.json").write_text(json.dumps(catalog_data, indent=1, ensure_ascii=False) + "\n",
                                      encoding="utf-8")
    (OUT / "recording.json").write_text(json.dumps(
        {"recorded_at": CLOCK.isoformat(), "start": START.isoformat(), "requests": len(recorder.entries),
         "recorded_on": datetime.now(UTC).date().isoformat()}, indent=1) + "\n", encoding="utf-8")
    error_dir = OUT / "fred-error"
    error_dir.mkdir()
    (error_dir / "fred_bad_key.json").write_bytes(bad.content)
    (error_dir / "manifest.json").write_text(json.dumps({
        "about": "FRED's recorded answer to an unregistered api_key, served for any observations call.",
        "responses": [{"request": "GET https://api.stlouisfed.org/fred/series/observations", "match": "prefix",
                       "status": bad.status_code, "file": "fred_bad_key.json"}]}, indent=1) + "\n",
        encoding="utf-8")
    print(f"recorded {len(recorder.entries)} responses (+ FRED bad key: HTTP {bad.status_code}) as of "
          f"{CLOCK:%Y-%m-%d} into {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
