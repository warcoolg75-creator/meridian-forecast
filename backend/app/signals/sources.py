"""The four fetchers: Open-Meteo, FRED, Wikimedia pageviews and GDELT.

Each observation fetcher takes the series it should fill and the date range to ask for
(per series: the backfill start, or the latest stored day minus the source's revision
window) and returns one SeriesResult per series. A failed request fails only the series
it served; the others in the same source still come back.

GDELT is different: news arrives in windows, so fetch_news yields one batch per finished
window and the pipeline commits each, which lets an interrupted backfill resume.
"""

import hashlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlsplit

from app.signals.catalog import Catalog, NewsTopic, SeriesDef
from app.signals.http import FetchError, SignalHttp


@dataclass
class SeriesResult:
    key: str
    points: dict[date, float] = field(default_factory=dict)
    error: str | None = None
    replace: bool = False  # a forecast series: the fetched days replace everything stored
    missing: int = 0  # days the source itself reported as missing (FRED ".", Open-Meteo null)


@dataclass
class FetchContext:
    catalog: Catalog
    http: SignalHttp
    today: date  # UTC
    backfill: bool
    start: date  # the backfill start (the first day of the sales history)
    latest: dict[str, date | None]  # series key -> latest stored day
    api_key: str = ""
    progress: Callable[[str], None] = lambda _msg: None
    news_from_start: bool = False  # news from `start`, not the last news.backfill_days

    def from_day(self, key: str, revision_days: int) -> date:
        latest = self.latest.get(key)
        if self.backfill or latest is None:
            return self.start
        return max(self.start, latest - timedelta(days=revision_days))


# --------------------------------------------------------------------------- Open-Meteo

def fetch_weather(ctx: FetchContext, series: list[SeriesDef]) -> list[SeriesResult]:
    weather = ctx.catalog.file.weather
    results: list[SeriesResult] = []
    by_city: dict[str, list[SeriesDef]] = {}
    for s in series:
        by_city.setdefault(s.geography, []).append(s)
    end = ctx.today - timedelta(days=1)  # today is not over yet: its maximum is not final
    for city, specs in by_city.items():
        observed = [s for s in specs if not s.is_forecast]
        forecast = [s for s in specs if s.is_forecast]
        lat, lon = specs[0].params["latitude"], specs[0].params["longitude"]
        if observed:
            start = min(ctx.from_day(s.key, weather.revision_days) for s in observed)
            results += _open_meteo_call(ctx, weather.archive_url, observed, dict(
                latitude=lat, longitude=lon, start_date=start.isoformat(), end_date=end.isoformat(),
                daily=",".join(s.params["variable"] for s in observed), timezone=weather.timezone))
        if forecast:
            results += _open_meteo_call(ctx, weather.forecast_url, forecast, dict(
                latitude=lat, longitude=lon, forecast_days=weather.forecast_days,
                daily=",".join(s.params["variable"] for s in forecast), timezone=weather.timezone),
                replace=True)
        ctx.progress(f"  open_meteo {city}: {len(specs)} series")
    return results


def _open_meteo_call(ctx: FetchContext, url: str, specs: list[SeriesDef], params: dict,
                     replace: bool = False) -> list[SeriesResult]:
    try:
        daily = ctx.http.get(url, params).json()["daily"]
        days = [date.fromisoformat(d) for d in daily["time"]]
    except (FetchError, KeyError, TypeError, ValueError) as exc:
        message = str(exc) if isinstance(exc, FetchError) else f"Unexpected response: {type(exc).__name__}"
        return [SeriesResult(s.key, error=message, replace=replace) for s in specs]
    out = []
    for s in specs:
        result = SeriesResult(s.key, replace=replace)
        values = daily.get(s.params["variable"])
        if values is None or len(values) != len(days):
            result.error = f"Unexpected response: no {s.params['variable']}"
        else:
            for day, value in zip(days, values, strict=True):
                if value is None:
                    result.missing += 1
                else:
                    result.points[day] = float(value)
        out.append(result)
    return out


# --------------------------------------------------------------------------- FRED

def fetch_fred(ctx: FetchContext, series: list[SeriesDef]) -> list[SeriesResult]:
    fred = ctx.catalog.file.fred
    results = []
    for s in series:
        result = SeriesResult(s.key)
        try:
            data = ctx.http.get(fred.url, dict(
                series_id=s.external_id, api_key=ctx.api_key, file_type="json",
                observation_start=ctx.from_day(s.key, fred.revision_days).isoformat(),
                observation_end=ctx.today.isoformat())).json()
            for obs in data["observations"]:
                if obs["value"] in (".", ""):
                    result.missing += 1
                else:
                    result.points[date.fromisoformat(obs["date"])] = float(obs["value"])
        except FetchError as exc:
            result.error = str(exc)
        except (KeyError, TypeError, ValueError) as exc:
            result.error = f"Unexpected response: {type(exc).__name__}"
        results.append(result)
        ctx.progress(f"  fred {s.external_id}: {len(result.points)} observations"
                     + (f" (failed: {result.error})" if result.error else ""))
    return results


# --------------------------------------------------------------------------- Wikimedia

def fetch_pageviews(ctx: FetchContext, series: list[SeriesDef]) -> list[SeriesResult]:
    wiki = ctx.catalog.file.wikimedia
    end = ctx.today - timedelta(days=1)
    results = []
    for s in series:
        result = SeriesResult(s.key)
        start = ctx.from_day(s.key, wiki.revision_days)
        try:
            data = ctx.http.get(f"{wiki.url}/{s.external_id}/daily/{start:%Y%m%d}00/{end:%Y%m%d}00").json()
            for item in data["items"]:
                stamp = item["timestamp"]
                result.points[date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:8]))] = float(item["views"])
        except FetchError as exc:
            result.error = str(exc)
        except (KeyError, TypeError, ValueError) as exc:
            result.error = f"Unexpected response: {type(exc).__name__}"
        results.append(result)
        ctx.progress(f"  wikimedia {s.external_id}: {len(result.points)} days"
                     + (f" (failed: {result.error})" if result.error else ""))
    return results


# --------------------------------------------------------------------------- GDELT

@dataclass(frozen=True)
class Window:
    start: datetime  # UTC, inclusive
    end: datetime  # UTC, exclusive

    @property
    def label(self) -> str:
        return f"{self.start:%Y%m%d%H%M%S}-{self.end:%Y%m%d%H%M%S}"

    def halves(self) -> tuple["Window", "Window"]:
        middle = self.start + (self.end - self.start) / 2
        middle = middle.replace(minute=0, second=0, microsecond=0)
        return Window(self.start, middle), Window(middle, self.end)


@dataclass
class Article:
    url: str
    url_hash: str
    title: str
    published_at: datetime
    language: str
    publisher: str
    source_country: str


@dataclass
class NewsBatch:
    category: str
    window: Window
    articles: list[Article]
    capped: bool = False  # the window still hit max_records at the smallest size


def month_windows(start: datetime, end: datetime, months: int = 1) -> list[Window]:
    """Windows on calendar-month boundaries, `months` long (the first may start mid-month)."""
    out, cursor = [], start
    while cursor < end:
        nxt = cursor
        for _ in range(months):
            nxt = (nxt.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0)
        out.append(Window(cursor, min(nxt, end)))
        cursor = nxt
    return out


def parse_article(raw: dict) -> Article | None:
    url = (raw.get("url") or "").strip()
    title = " ".join((raw.get("title") or "").split())
    if not title or urlsplit(url).scheme not in ("http", "https"):  # links are rendered: http(s) only
        return None
    try:
        seen = datetime.strptime(raw["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except (KeyError, ValueError):
        return None
    return Article(url=url, url_hash=hashlib.sha256(url.encode()).hexdigest(), title=title[:500],
                   published_at=seen, language=(raw.get("language") or "Unknown")[:40],
                   publisher=(raw.get("domain") or urlsplit(url).hostname or "")[:200],
                   source_country=(raw.get("sourcecountry") or "")[:60])


MIN_WINDOW = timedelta(days=1)


def fetch_window(ctx: FetchContext, topic: NewsTopic, window: Window) -> NewsBatch:
    """Articles for one topic in one window. A window that returns max_records is split in
    half until it fits or reaches a day; one still full at a day is marked capped."""
    news = ctx.catalog.file.news
    data = ctx.http.get(news.url, dict(
        query=f"{topic.query} sourcecountry:{news.source_country}", mode="artlist", format="json",
        maxrecords=news.max_records, sort="datedesc",
        startdatetime=f"{window.start:%Y%m%d%H%M%S}", enddatetime=f"{window.end:%Y%m%d%H%M%S}"))
    text = data.text.strip()
    if text and not text.startswith("{"):  # GDELT answers a bad query with plain text and HTTP 200
        raise FetchError(f"GDELT refused the query: {' '.join(text[:160].split())}")
    raw = (data.json() if text else {}).get("articles", [])
    if len(raw) >= news.max_records and window.end - window.start > MIN_WINDOW:
        first, second = window.halves()
        a, b = fetch_window(ctx, topic, first), fetch_window(ctx, topic, second)
        return NewsBatch(topic.category, window, a.articles + b.articles, a.capped or b.capped)
    articles = [a for a in (parse_article(r) for r in raw) if a is not None]
    return NewsBatch(topic.category, window, articles, capped=len(raw) >= news.max_records)


def news_start(ctx: FetchContext, now: datetime) -> datetime:
    """Where news begins: the first of the month `news.backfill_days` reach back into (so a
    window's label holds all month and an interrupted backfill resumes), or the backfill
    start (2023-10-09) when asked for everything. The market page shows recent headlines and
    phase 8 classifies recent ones: three years of news are not needed by default."""
    start = datetime(ctx.start.year, ctx.start.month, ctx.start.day, tzinfo=UTC)
    if ctx.news_from_start:
        return start
    back = now - timedelta(days=ctx.catalog.file.news.backfill_days)
    return max(start, back.replace(day=1, hour=0, minute=0, second=0, microsecond=0))


def news_windows(ctx: FetchContext, topic: NewsTopic, done: set[str], latest: datetime | None,
                 now: datetime) -> list[Window]:
    """Backfill: windows of `window_months` calendar months from news_start, skipping those
    a previous backfill finished (the last two days are always fetched again). Refresh:
    monthly windows from the first of the month that holds the latest stored headline less
    two days of overlap (never before news_start), to now. Starting on a month boundary keeps
    a refresh's request the same all month (only its end moves), at one request per topic."""
    start = news_start(ctx, now)
    recent = now - timedelta(days=2)
    months = ctx.catalog.file.news.window_months
    if ctx.backfill or latest is None:
        return [w for w in month_windows(start, now, months)
                if f"{topic.category}|{w.label}" not in done or w.end > recent]
    overlap = (latest - timedelta(days=2)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_windows(max(start, overlap), now)


def fetch_news(ctx: FetchContext, done: set[str], latest: dict[str, datetime | None],
               now: datetime) -> Iterator[NewsBatch | tuple[str, Window, str]]:
    """Yields a NewsBatch per finished window, or (category, window, error) for a failed one."""
    for topic in ctx.catalog.file.news.topics:
        windows = news_windows(ctx, topic, done, latest.get(topic.category), now)
        ctx.progress(f"  gdelt {topic.category}: {len(windows)} windows")
        for window in windows:
            try:
                yield fetch_window(ctx, topic, window)
            except FetchError as exc:
                yield (topic.category, window, str(exc))


OBSERVATION_FETCHERS = {"open_meteo": fetch_weather, "fred": fetch_fred, "wikimedia": fetch_pageviews}
