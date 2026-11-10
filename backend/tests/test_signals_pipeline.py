"""Backfill and refresh on recorded responses: rows, idempotence, isolation of a failure.

Every response comes from tests/fixtures/signals/ (recorded live by
tools/record_signal_fixtures.py); the conftest guard refuses any network access, and each
test checks that every request it made was answered from a fixture.
"""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select, update

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
from app.signals.catalog import load_catalog
from app.signals.http import FetchError, SignalHttp
from app.signals.pipeline import upsert_observations
from app.signals.redact import Redactor
from app.signals.replay import ReplayTransport
from app.signals.sources import FetchContext, NewsTopic, Window, fetch_window, month_windows, parse_article
from tests.signals_fixture import FIXTURES, catalog_data, recording, runner, test_catalog


def _counts(db) -> dict[str, int]:
    rows = db.execute(select(SignalSeries.key, func.count(SignalObservation.id))
                      .join(SignalObservation, isouter=True).group_by(SignalSeries.key)).all()
    return dict(rows)


def _status(db, code: str) -> FetchStatus:
    db.expire_all()
    return db.scalars(select(SignalSource).where(SignalSource.code == code)).one().last_status


def test_backfill_fills_every_series_from_the_start(engine, db, tmp_path):
    replay = ReplayTransport(FIXTURES)
    reports = runner(engine, tmp_path, replay=replay).run()
    assert replay.misses == []
    assert {r.source: r.status for r in reports} == {c: FetchStatus.OK for c in
                                                     ("open_meteo", "fred", "wikimedia", "gdelt")}
    now, start = recording()
    counts = _counts(db)
    days = (now.date() - timedelta(days=1) - start).days + 1  # through yesterday
    for city in ("IN-DL-NDL", "IN-TN-CHE"):
        assert counts[f"weather.tmax.{city}"] == counts[f"weather.rain.{city}"] == days
        assert counts[f"weather.tmax_forecast.{city}"] == 16
    assert counts["wiki.Diwali"] == counts["wiki.Evaporative_cooler"] == days
    assert counts["fred.PCOPPUSDM"] >= 1  # monthly, dated the 1st (FRED includes the start's month)
    assert counts["fred.DCOILBRENTEU"] > 20  # trading days
    tmax = db.scalars(select(SignalSeries).where(SignalSeries.key == "weather.tmax.IN-DL-NDL")).one()
    first = db.scalar(select(func.min(SignalObservation.observed_on)).where(SignalObservation.series_id == tmax.id))
    assert first == start
    # Provenance: every row names the fetch that wrote it, and that fetch its source.
    assert db.scalar(select(func.count()).select_from(SignalObservation)
                     .where(SignalObservation.fetch_id.is_(None))) == 0
    assert db.scalar(select(func.count()).select_from(NewsItem)) > 0
    assert db.scalar(select(func.count()).select_from(NewsItemCategory)) >= db.scalar(
        select(func.count()).select_from(NewsItem))
    for series in db.scalars(select(SignalSeries)):
        assert series.last_success_at == now and series.last_error is None, series.key


def test_refresh_twice_changes_nothing_the_second_time(engine, db, tmp_path):
    runner(engine, tmp_path).run()
    runner(engine, tmp_path, FetchMode.REFRESH).run()
    snapshot = sorted(db.execute(select(SignalObservation.series_id, SignalObservation.observed_on,
                                        SignalObservation.value, SignalObservation.fetched_at,
                                        SignalObservation.fetch_id)).all())
    news = sorted(db.execute(select(NewsItem.url_hash, NewsItem.title, NewsItem.fetched_at)).all())
    replay = ReplayTransport(FIXTURES)
    reports = runner(engine, tmp_path, FetchMode.REFRESH, replay=replay).run()
    assert replay.misses == []
    assert all(r.status is FetchStatus.OK for r in reports)
    assert sum(r.counts.changed for r in reports) == 0
    assert sum(r.counts.unchanged for r in reports) > 0
    db.expire_all()
    assert sorted(db.execute(select(SignalObservation.series_id, SignalObservation.observed_on,
                                    SignalObservation.value, SignalObservation.fetched_at,
                                    SignalObservation.fetch_id)).all()) == snapshot
    assert sorted(db.execute(select(NewsItem.url_hash, NewsItem.title, NewsItem.fetched_at)).all()) == news
    fetches = db.scalars(select(SignalFetch).order_by(SignalFetch.id.desc()).limit(4)).all()
    assert all(f.mode is FetchMode.REFRESH and f.inserted == f.updated == f.deleted == 0 for f in fetches)


def test_a_broken_url_fails_only_its_source(engine, db, tmp_path, client, auth_headers):
    data = catalog_data()
    data["wikimedia"]["url"] = data["wikimedia"]["url"].replace("per-article", "per-artikel")  # broken
    replay = ReplayTransport(FIXTURES)
    reports = runner(engine, tmp_path, catalog=test_catalog(data), replay=replay).run()
    statuses = {r.source: r.status for r in reports}
    assert statuses == {"open_meteo": FetchStatus.OK, "fred": FetchStatus.OK, "wikimedia": FetchStatus.FAILED,
                        "gdelt": FetchStatus.OK}
    assert replay.misses and all("per-artikel" in m for m in replay.misses)
    counts = _counts(db)
    assert counts["wiki.Diwali"] == 0 and counts["weather.tmax.IN-DL-NDL"] > 0

    from app.models import UserRole
    from app.models.base import utcnow

    # The recording is dated 2023-12-01; freshness is judged against today, so move every
    # success to now. The failure stays a failure.
    db.execute(update(SignalSource).where(SignalSource.last_success_at.is_not(None)).values(last_success_at=utcnow()))
    db.execute(update(SignalSeries).where(SignalSeries.last_success_at.is_not(None)).values(last_success_at=utcnow()))
    db.commit()
    headers = auth_headers(UserRole.VIEWER)
    response = client.get("/api/v1/market/overview", headers=headers)
    assert response.status_code == 200
    body = response.json()
    by_source = {s["code"]: s for s in body["sources"]}
    assert by_source["wikimedia"]["status"] == "stale" and "HTTP 404" in by_source["wikimedia"]["status_reason"]
    assert by_source["open_meteo"]["status"] == "fresh"
    series = {m["series"]["key"]: m["series"] for c in body["categories"]
              for m in c["demand_context"] + c["input_cost"]}
    assert series["wiki.Evaporative_cooler"]["status"] == "stale"
    assert series["weather.tmax.IN-DL-NDL"]["status"] == "fresh"
    assert client.get("/api/v1/market/series", params={"keys": ["weather.tmax.IN-DL-NDL"]},
                      headers=headers).json()["items"][0]["points"]


def test_without_a_fred_key_fred_is_not_configured_and_the_rest_runs(engine, db, tmp_path):
    reports = runner(engine, tmp_path, fred_api_key="").run()
    statuses = {r.source: r.status for r in reports}
    assert statuses["fred"] is FetchStatus.NOT_CONFIGURED
    assert statuses["open_meteo"] is FetchStatus.OK
    assert _counts(db)["fred.DCOILBRENTEU"] == 0


def test_an_exception_inside_a_source_is_isolated(engine, db, tmp_path, monkeypatch):
    import app.signals.sources as sources

    def explode(_ctx, _series):
        raise ValueError("boom")

    monkeypatch.setitem(sources.OBSERVATION_FETCHERS, "fred", explode)
    reports = runner(engine, tmp_path).run()
    assert {r.source: r.status for r in reports}["fred"] is FetchStatus.FAILED
    assert _status(db, "open_meteo") is FetchStatus.OK
    copper = db.scalars(select(SignalSeries).where(SignalSeries.key == "fred.PCOPPUSDM")).one()
    assert copper.last_error == "ValueError: boom"


def test_a_forecast_series_is_replaced_whole_and_values_are_updated_not_duplicated(engine, db, tmp_path):
    runner(engine, tmp_path).run()
    fetch_id = db.scalar(select(func.max(SignalFetch.id)))
    series = db.scalars(select(SignalSeries).where(SignalSeries.key == "weather.tmax_forecast.IN-DL-NDL")).one()
    now = datetime.now(UTC)
    days = sorted(db.scalars(select(SignalObservation.observed_on).where(SignalObservation.series_id == series.id)))
    newer = {d: 30.0 for d in days[2:]} | {days[-1] + timedelta(days=1): 31.0}
    counts = upsert_observations(db, series.id, newer, fetch_id, now, replace=True)
    assert (counts.inserted, counts.updated, counts.deleted) == (1, len(days) - 2, 2)
    observed = db.scalars(select(SignalSeries).where(SignalSeries.key == "weather.tmax.IN-DL-NDL")).one()
    first = db.scalar(select(SignalObservation.observed_on).where(SignalObservation.series_id == observed.id)
                      .order_by(SignalObservation.observed_on))
    counts = upsert_observations(db, observed.id, {first: -99.0}, fetch_id, now)
    assert (counts.inserted, counts.updated, counts.deleted) == (0, 1, 0)  # never deletes observed days
    db.commit()


def test_the_raw_cache_holds_every_body_without_the_key(engine, db, tmp_path):
    from tests.signals_fixture import FAKE_FRED_KEY

    runner(engine, tmp_path).run()
    files = [p for p in (tmp_path / "signals-cache").rglob("*") if p.is_file()]
    assert len([p for p in files if p.name != "index.jsonl"]) >= 10  # every backfill request
    for path in files:
        assert FAKE_FRED_KEY not in path.read_text(encoding="utf-8")
    index = "".join(p.read_text(encoding="utf-8") for p in files if p.name == "index.jsonl")
    assert "api_key=***" in index


# --------------------------------------------------------------------------- GDELT units

def test_month_windows_and_halves():
    start = datetime(2023, 10, 9, tzinfo=UTC)
    windows = month_windows(start, datetime(2024, 1, 15, tzinfo=UTC))
    assert [(w.start.date(), w.end.date()) for w in windows] == [
        (date(2023, 10, 9), date(2023, 11, 1)), (date(2023, 11, 1), date(2023, 12, 1)),
        (date(2023, 12, 1), date(2024, 1, 1)), (date(2024, 1, 1), date(2024, 1, 15))]
    a, b = windows[1].halves()
    assert a.start == windows[1].start and b.end == windows[1].end and a.end == b.start


def test_a_refresh_rereads_news_from_the_first_of_the_month_holding_its_overlap():
    from app.signals.sources import news_windows

    ctx = FetchContext(catalog=load_catalog(), http=None, today=date(2026, 11, 10), backfill=False,
                       start=date(2023, 10, 9), latest={})
    topic = NewsTopic(category="Cooling", query="x")
    now = datetime(2026, 11, 10, 6, tzinfo=UTC)
    windows = news_windows(ctx, topic, set(), datetime(2026, 11, 9, 12, tzinfo=UTC), now)
    assert [(w.start, w.end) for w in windows] == [(datetime(2026, 11, 1, tzinfo=UTC), now)]
    # Two days back crosses into October: October is read again too.
    windows = news_windows(ctx, topic, set(), datetime(2026, 11, 1, 12, tzinfo=UTC), now)
    assert [w.start.date() for w in windows] == [date(2026, 10, 1), date(2026, 11, 1)]


def test_a_news_backfill_reads_the_last_90_days_unless_asked_for_everything(engine, tmp_path):
    from app.signals.sources import news_windows

    now = datetime(2026, 11, 10, 6, tzinfo=UTC)
    topic = NewsTopic(category="Cooling", query="x")

    def ctx(**kwargs) -> FetchContext:
        return FetchContext(catalog=load_catalog(), http=None, today=now.date(), start=date(2023, 10, 9),
                            latest={}, **kwargs)

    assert load_catalog().file.news.backfill_days == 90
    # 90 days back is 12 Aug: from 1 Aug, in the catalog's quarterly windows. Two requests a topic.
    recent = news_windows(ctx(backfill=True), topic, set(), None, now)
    assert [(w.start, w.end) for w in recent] == [
        (datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 11, 1, tzinfo=UTC)), (datetime(2026, 11, 1, tzinfo=UTC), now)]
    everything = news_windows(ctx(backfill=True, news_from_start=True), topic, set(), None, now)
    assert len(everything) == 13 and everything[0].start == datetime(2023, 10, 9, tzinfo=UTC)
    assert everything[-1].end == now
    # A refresh whose newest headline is years old starts at the same 90 days, month by month.
    old = news_windows(ctx(backfill=False), topic, set(), datetime(2023, 11, 30, tzinfo=UTC), now)
    assert [w.start.date() for w in old] == [date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)]
    # The CLI flag reaches the fetchers.
    flagged = runner(engine, tmp_path)
    assert flagged._context(None, {}).news_from_start is False
    flagged.news_from_start = True
    assert flagged._context(None, {}).news_from_start is True


def test_parse_article_keeps_only_http_links_with_a_title():
    good = {"url": "https://example.in/a", "title": "  A   title ", "seendate": "20241020T131500Z",
            "language": "Hindi", "domain": "example.in", "sourcecountry": "India"}
    article = parse_article(good)
    assert article.title == "A title" and article.published_at == datetime(2024, 10, 20, 13, 15, tzinfo=UTC)
    assert parse_article({**good, "url": "javascript:alert(1)"}) is None
    assert parse_article({**good, "title": ""}) is None
    assert parse_article({**good, "seendate": "yesterday"}) is None


def _gdelt_ctx(handler) -> FetchContext:
    catalog = load_catalog()
    http = SignalHttp("gdelt", catalog.sources["gdelt"].http, Redactor(), user_agent="test",
                      transport=httpx.MockTransport(handler), sleep=lambda _s: None, clock=lambda: 0.0)
    return FetchContext(catalog=catalog, http=http, today=date(2026, 11, 10), backfill=True,
                        start=date(2023, 10, 9), latest={})


def _articles(n: int, day: str) -> dict:
    return {"articles": [{"url": f"https://example.in/{day}/{i}", "title": f"Headline {i}",
                          "seendate": f"{day}T120000Z", "language": "English", "domain": "example.in",
                          "sourcecountry": "India"} for i in range(n)]}


def test_a_full_window_is_split_until_it_fits_or_reaches_a_day():
    # Constructed responses (no live call): a window answers 250 until it spans 2 days or less.
    def handler(request: httpx.Request) -> httpx.Response:
        start = datetime.strptime(request.url.params["startdatetime"], "%Y%m%d%H%M%S")
        end = datetime.strptime(request.url.params["enddatetime"], "%Y%m%d%H%M%S")
        n = 250 if end - start > timedelta(days=2) else 10
        return httpx.Response(200, json=_articles(n, f"{start:%Y%m%d}"))

    ctx = _gdelt_ctx(handler)
    batch = fetch_window(ctx, NewsTopic(category="Cooling", query="x"),
                         Window(datetime(2024, 5, 1, tzinfo=UTC), datetime(2024, 5, 9, tzinfo=UTC)))
    assert not batch.capped and ctx.http.requests == 7  # 8 days -> 4 + 4 -> four 2-day windows
    assert len({a.url for a in batch.articles}) == 40


def test_gdelt_plain_text_answers_and_429s_are_errors_not_empty_results():
    def text_handler(_request):
        return httpx.Response(200, text="Your search contained a phrase that was too short.")

    with pytest.raises(FetchError, match="GDELT refused the query"):
        fetch_window(_gdelt_ctx(text_handler), NewsTopic(category="Cooling", query="x"),
                     Window(datetime(2024, 5, 1, tzinfo=UTC), datetime(2024, 5, 2, tzinfo=UTC)))

    def busy(_request):
        return httpx.Response(429, text="Please limit requests to one every 5 seconds")

    ctx = _gdelt_ctx(busy)
    with pytest.raises(FetchError, match="HTTP 429.*after 2 attempts"):
        fetch_window(ctx, NewsTopic(category="Cooling", query="x"),
                     Window(datetime(2024, 5, 1, tzinfo=UTC), datetime(2024, 5, 2, tzinfo=UTC)))
    assert ctx.http.requests == 2


def test_gdelt_stops_at_the_first_window_it_is_rate_limited_on(engine, db, tmp_path, monkeypatch):
    import app.signals.sources as sources

    calls = []

    def blocked(_ctx, topic, window):
        calls.append((topic.category, window.label))
        raise FetchError("HTTP 429: Please limit requests from https://api.gdeltproject.org/x, after 4 attempts")

    monkeypatch.setattr(sources, "fetch_window", blocked)
    reports = runner(engine, tmp_path).run(["gdelt"])
    assert reports[0].status is FetchStatus.FAILED
    assert len(calls) == 1  # no hammering: every later window would be refused too
    assert "rate-limiting this address" in reports[0].errors[-1]
