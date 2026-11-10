"""Backfill and refresh: sync the catalog, then run each source on its own.

One failing source never blocks the others or the app: each source runs in its own
session and transaction, inside its own try/except, and a failure is recorded (redacted)
on the source, on its series and on its signal_fetches row. The app reads whatever is
stored and marks a series stale when its last attempt failed or its last success is too
old (app/services/market.py).

Upserts compare values: a new day is inserted, a changed value updated, an equal one left
alone (its fetched_at does not move), so a second refresh right after a first writes no
observation or news row. Forecast series are replaced whole by the latest forecast.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import BACKEND_DIR, Settings
from app.models import (
    FetchMode,
    FetchStatus,
    NewsItem,
    NewsItemCategory,
    SignalFetch,
    SignalObservation,
    SignalSeries,
    SignalSource,
)
from app.models.base import utcnow
from app.signals.catalog import Catalog, load_catalog, sync_catalog
from app.signals.http import RawCache, SignalHttp
from app.signals.redact import Redactor, secret_values
from app.signals.replay import ReplayTransport
from app.signals.sources import (
    OBSERVATION_FETCHERS,
    Article,
    FetchContext,
    NewsBatch,
    SeriesResult,
    fetch_news,
)

# The first day of the pinned sales history (seed/ground_truth.py: 3 years to 2026-10-08).
BACKFILL_START = date(2023, 10, 9)
INSERT_CHUNK = 1000
ERROR_LENGTH = 480


@dataclass
class Counts:
    inserted: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0

    def add(self, other: "Counts") -> None:
        self.inserted += other.inserted
        self.updated += other.updated
        self.deleted += other.deleted
        self.unchanged += other.unchanged

    @property
    def changed(self) -> int:
        return self.inserted + self.updated + self.deleted


@dataclass
class SourceReport:
    source: str
    status: FetchStatus
    counts: Counts = field(default_factory=Counts)
    requests: int = 0
    errors: list[str] = field(default_factory=list)
    fetch_id: int | None = None


def _clip(text: str) -> str:
    return text if len(text) <= ERROR_LENGTH else text[:ERROR_LENGTH - 1] + "…"


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


# --------------------------------------------------------------------------- upserts

def upsert_observations(session: Session, series_id: int, points: dict[date, float], fetch_id: int,
                        now: datetime, replace: bool = False) -> Counts:
    counts = Counts()
    query = select(SignalObservation.id, SignalObservation.observed_on, SignalObservation.value).where(
        SignalObservation.series_id == series_id)
    if not replace:
        if not points:
            return counts
        query = query.where(SignalObservation.observed_on.between(min(points), max(points)))
    existing = {day: (row_id, value) for row_id, day, value in session.execute(query)}
    inserts, updates = [], []
    for day, value in sorted(points.items()):
        if day not in existing:
            inserts.append(dict(series_id=series_id, observed_on=day, value=value, fetched_at=now,
                                fetch_id=fetch_id))
        elif not _same(existing[day][1], value):
            updates.append(dict(id=existing[day][0], value=value, fetched_at=now, fetch_id=fetch_id))
        else:
            counts.unchanged += 1
    stale_ids = [row_id for day, (row_id, _) in existing.items() if replace and day not in points]
    for i in range(0, len(inserts), INSERT_CHUNK):
        session.execute(insert(SignalObservation), inserts[i:i + INSERT_CHUNK])
    if updates:
        session.execute(update(SignalObservation), updates)
    for i in range(0, len(stale_ids), INSERT_CHUNK):
        session.execute(delete(SignalObservation).where(SignalObservation.id.in_(stale_ids[i:i + INSERT_CHUNK])))
    counts.inserted, counts.updated, counts.deleted = len(inserts), len(updates), len(stale_ids)
    return counts


def upsert_news(session: Session, source_id: int, category: str, articles: list[Article], fetch_id: int,
                now: datetime) -> Counts:
    counts = Counts()
    unique = {a.url_hash: a for a in articles}
    if not unique:
        return counts
    existing: dict[str, tuple[int, str, str, str]] = {}
    hashes = list(unique)
    for i in range(0, len(hashes), 500):
        for row_id, url_hash, title, language, publisher in session.execute(
                select(NewsItem.id, NewsItem.url_hash, NewsItem.title, NewsItem.language, NewsItem.publisher)
                .where(NewsItem.url_hash.in_(hashes[i:i + 500]))):
            existing[url_hash] = (row_id, title, language, publisher)
    new = [a for h, a in unique.items() if h not in existing]
    for a in new:
        item = NewsItem(source_id=source_id, url=a.url, url_hash=a.url_hash, title=a.title,
                        published_at=a.published_at, language=a.language, publisher=a.publisher,
                        source_country=a.source_country, fetched_at=now, fetch_id=fetch_id)
        session.add(item)
        session.flush()
        existing[a.url_hash] = (item.id, a.title, a.language, a.publisher)
    counts.inserted = len(new)
    new_hashes = {a.url_hash for a in new}
    for h, a in unique.items():
        if h in new_hashes:
            continue
        row_id, title, language, publisher = existing[h]
        if (title, language, publisher) != (a.title, a.language, a.publisher):
            session.execute(update(NewsItem).where(NewsItem.id == row_id).values(
                title=a.title, language=a.language, publisher=a.publisher, fetched_at=now, fetch_id=fetch_id))
            counts.updated += 1
        else:
            counts.unchanged += 1
    ids = [existing[h][0] for h in unique]
    linked = set(session.scalars(select(NewsItemCategory.news_item_id).where(
        NewsItemCategory.category == category, NewsItemCategory.news_item_id.in_(ids))))
    missing = [i for i in ids if i not in linked]
    if missing:
        session.execute(insert(NewsItemCategory), [dict(news_item_id=i, category=category) for i in missing])
        counts.inserted += len(missing)
    return counts


# --------------------------------------------------------------------------- runner

@dataclass
class Runner:
    sessions: sessionmaker[Session]
    settings: Settings
    mode: FetchMode
    catalog: Catalog = field(default_factory=load_catalog)
    transport: Callable[[str], httpx.BaseTransport | None] = lambda _source: None
    sleep: Callable[[float], None] | None = None
    clock: Callable[[], datetime] = utcnow
    progress: Callable[[str], None] = lambda _msg: None
    fail_fast: bool = False
    start: date = BACKFILL_START
    news_from_start: bool = False  # news from `start` too, not only the last news.backfill_days

    def __post_init__(self) -> None:
        self.redactor = Redactor(secret_values(self.settings))
        if self.settings.signals_replay_dir:  # recorded responses only, never the network
            replay = ReplayTransport(self.settings.signals_replay_dir)
            self.transport = lambda _source: replay
            self.sleep = self.sleep or (lambda _seconds: None)  # nothing to be polite to
        root = Path(self.settings.signals_cache_dir) if self.settings.signals_cache_dir else Path(".cache/signals")
        self.cache = RawCache(root if root.is_absolute() else BACKEND_DIR / root)

    def run(self, only: list[str] | None = None) -> list[SourceReport]:
        with self.sessions() as session, session.begin():
            sync_catalog(session, self.catalog)
        reports = []
        for code in self.catalog.sources:
            if only and code not in only:
                continue
            reports.append(self.run_source(code))
        return reports

    def _http(self, code: str) -> SignalHttp:
        kwargs = {} if self.sleep is None else {"sleep": self.sleep, "clock": lambda: 0.0}
        return SignalHttp(code, self.catalog.sources[code].http, self.redactor,
                          user_agent=self.settings.signals_user_agent, transport=self.transport(code),
                          cache=self.cache, on_retry=self.progress, **kwargs)

    def run_source(self, code: str) -> SourceReport:
        now = self.clock()
        spec = self.catalog.sources[code]
        with self.sessions() as session, session.begin():
            source = session.scalars(select(SignalSource).where(SignalSource.code == code)).one()
            # A run that never finished (stopped, or the machine slept) is closed as failed.
            # Its committed rows and finished windows stay: a backfill resumes after them.
            session.execute(update(SignalFetch).where(
                SignalFetch.source_id == source.id, SignalFetch.status == FetchStatus.RUNNING).values(
                status=FetchStatus.FAILED, finished_at=now, error="Interrupted before it finished"))
            fetch = SignalFetch(source_id=source.id, mode=self.mode, status=FetchStatus.RUNNING, started_at=now)
            session.add(fetch)
            session.flush()
            fetch_id, source_id = fetch.id, source.id
        report = SourceReport(code, FetchStatus.RUNNING, fetch_id=fetch_id)
        self.progress(f"{code}: {self.mode.value}")

        if spec.requires_key and not self.settings.fred_api_key:
            report.status = FetchStatus.NOT_CONFIGURED
            report.errors.append("FRED_API_KEY is not set in .env")
            self._finish(code, report, now)
            return report

        http = self._http(code)
        try:
            if code == "gdelt":
                self._run_news(http, source_id, report, now)
            else:
                self._run_observations(code, http, source_id, report, now)
        except Exception as exc:  # isolation: one source failing never stops the others
            if self.fail_fast:
                raise
            report.status = FetchStatus.FAILED
            report.errors.append(_clip(self.redactor.redact(f"{type(exc).__name__}: {exc}")))
            with self.sessions() as session, session.begin():
                for series in session.scalars(select(SignalSeries).where(SignalSeries.source_id == source_id)):
                    series.last_attempt_at, series.last_error = now, report.errors[-1]
        finally:
            report.requests = http.requests
            cache_dirs = sorted(str(p) for p in http.cache_dirs)
            http.close()
        self._finish(code, report, now, cache_dirs[-1] if cache_dirs else None)
        return report

    def _context(self, http: SignalHttp, latest: dict) -> FetchContext:
        now = self.clock()
        return FetchContext(catalog=self.catalog, http=http, today=now.date(),
                            backfill=self.mode is FetchMode.BACKFILL, start=self.start, latest=latest,
                            api_key=self.settings.fred_api_key, progress=self.progress,
                            news_from_start=self.news_from_start)

    def _run_observations(self, code: str, http: SignalHttp, source_id: int, report: SourceReport,
                          now: datetime) -> None:
        specs = self.catalog.series_of(code)
        with self.sessions() as session:
            rows = {s.key: s for s in session.scalars(select(SignalSeries).where(SignalSeries.source_id == source_id))}
            latest = {key: row.latest_observed_on for key, row in rows.items()}
        results: list[SeriesResult] = OBSERVATION_FETCHERS[code](self._context(http, latest), specs)
        if not results and specs:
            raise RuntimeError("the fetcher returned nothing")
        with self.sessions() as session, session.begin():
            for result in results:
                series = session.scalars(select(SignalSeries).where(SignalSeries.key == result.key)).one()
                series.last_attempt_at = now
                if result.error:
                    series.last_error = _clip(self.redactor.redact(result.error))
                    report.errors.append(f"{result.key}: {series.last_error}")
                    continue
                report.counts.add(upsert_observations(session, series.id, result.points, report.fetch_id, now,
                                                      replace=result.replace))
                series.last_success_at, series.last_error = now, None
                series.latest_observed_on = session.scalar(
                    select(func.max(SignalObservation.observed_on)).where(SignalObservation.series_id == series.id))
        failed = sum(1 for r in results if r.error)
        if failed and self.fail_fast:
            raise RuntimeError(report.errors[0])
        report.status = (FetchStatus.OK if failed == 0 else
                         FetchStatus.FAILED if failed == len(results) else FetchStatus.PARTIAL)

    def _run_news(self, http: SignalHttp, source_id: int, report: SourceReport, now: datetime) -> None:
        with self.sessions() as session:
            done: set[str] = set()
            for detail in session.scalars(select(SignalFetch.detail).where(
                    SignalFetch.source_id == source_id, SignalFetch.detail.is_not(None))):
                done.update((detail or {}).get("windows_done", []))
            latest = {category: session.scalar(
                select(func.max(NewsItem.published_at)).join(NewsItemCategory).where(
                    NewsItemCategory.category == category))
                for category in (t.category for t in self.catalog.file.news.topics)}
        latest = {k: (v.replace(tzinfo=UTC) if v is not None and v.tzinfo is None else v) for k, v in latest.items()}
        windows_done, capped, failed, total = [], [], 0, 0
        for item in fetch_news(self._context(http, {}), done, latest, now.replace(microsecond=0)):
            total += 1
            if isinstance(item, tuple):
                category, window, error = item
                failed += 1
                report.errors.append(_clip(self.redactor.redact(f"{category} {window.label}: {error}")))
                if self.fail_fast:
                    raise RuntimeError(report.errors[-1])
                if "HTTP 429" in error:  # circuit breaker: GDELT keeps this address blocked for long
                    report.errors.append("Stopped: GDELT is rate-limiting this address. The finished windows "
                                         "are kept; run the backfill again later and it resumes after them.")
                    self.progress(f"  gdelt: {report.errors[-1]}")
                    break
                continue
            batch: NewsBatch = item
            with self.sessions() as session, session.begin():
                report.counts.add(upsert_news(session, source_id, batch.category, batch.articles,
                                              report.fetch_id, now))
                windows_done.append(f"{batch.category}|{batch.window.label}")
                if batch.capped:
                    capped.append(f"{batch.category}|{batch.window.label}")
                fetch = session.get(SignalFetch, report.fetch_id)
                fetch.detail = {"windows_done": list(windows_done), "capped": list(capped)}
                fetch.inserted, fetch.updated = report.counts.inserted, report.counts.updated
                fetch.unchanged = report.counts.unchanged
            self.progress(f"    {batch.category} {batch.window.start:%Y-%m-%d}..{batch.window.end:%Y-%m-%d}: "
                          f"{len(batch.articles)} headlines" + (" (capped)" if batch.capped else ""))
        report.status = (FetchStatus.OK if failed == 0 else
                         FetchStatus.FAILED if failed == total else FetchStatus.PARTIAL)

    def _finish(self, code: str, report: SourceReport, now: datetime, cache_dir: str | None = None) -> None:
        with self.sessions() as session, session.begin():
            source = session.scalars(select(SignalSource).where(SignalSource.code == code)).one()
            fetch = session.get(SignalFetch, report.fetch_id)
            error = _clip("; ".join(report.errors)) if report.errors else None
            fetch.status, fetch.finished_at, fetch.requests = report.status, self.clock(), report.requests
            fetch.inserted, fetch.updated = report.counts.inserted, report.counts.updated
            fetch.deleted, fetch.unchanged = report.counts.deleted, report.counts.unchanged
            fetch.error, fetch.cache_dir = error, cache_dir
            source.last_attempt_at, source.last_status, source.last_error = now, report.status, error
            if report.status in (FetchStatus.OK, FetchStatus.PARTIAL):
                source.last_success_at = now
        self.progress(f"{code}: {report.status.value}, {report.requests} requests, "
                      f"{report.counts.inserted} inserted, {report.counts.updated} updated, "
                      f"{report.counts.deleted} deleted, {report.counts.unchanged} unchanged"
                      + (f"; {len(report.errors)} errors" if report.errors else ""))
        for error in report.errors[:10]:
            self.progress(f"  error: {error}")


def run_signals(sessions: sessionmaker[Session], settings: Settings, mode: FetchMode, *,
                only: list[str] | None = None, **kwargs) -> list[SourceReport]:
    return Runner(sessions=sessions, settings=settings, mode=mode, **kwargs).run(only)
