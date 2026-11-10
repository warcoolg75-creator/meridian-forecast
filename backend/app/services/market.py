"""Reads for the market pages: what is mapped where, how fresh it is, and the values.

Staleness is judged against the real clock (these are real-world feeds, unlike the
synthetic sales): a series is stale when its last attempt failed, or when its last
success is older than its `stale_after_days`. A source that needs a key it was not given
is "not configured", not stale. News is "partial" when its last run stopped early (GDELT's
rate limit) while earlier runs left headlines stored: those are shown, and labelled so.

Weekly and monthly values are aggregated in the database (bucketing.py): the mean for
temperatures and prices, the sum for rainfall and pageviews. A monthly series is never
bucketed finer than a month.
"""

import re
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    FetchStatus,
    NewsItem,
    NewsItemCategory,
    Product,
    SignalMapping,
    SignalObservation,
    SignalSeries,
    SignalSource,
)
from app.models.base import utcnow
from app.schemas.market import (
    CategoryMarket,
    Headline,
    HeadlinesResponse,
    MappedSeries,
    MarketOverview,
    ProductMarket,
    SeriesData,
    SeriesInfo,
    SignalPoint,
    SourceStatus,
)
from app.services.bucketing import Granularity, period_start_expr
from app.services.errors import NotFoundError
from app.services.sales_source import data_bounds
from app.signals.catalog import load_catalog

MAX_SERIES_PER_REQUEST = 40
_URL = re.compile(r"https?://([^/\s?#]+)[^\s]*")


def _readable(error: str | None) -> str | None:
    """An error for the page: each URL shortened to its host (the stored error keeps the
    full, already redacted URL for make signals-status). A 600-character query string in a
    status line widened the market page to 1677px at 360."""
    return _URL.sub(lambda m: m.group(1), error) if error else error


def _age(now: datetime, then: datetime) -> str:
    days = (now - then).days
    return f"{days} days" if days != 1 else "1 day"


def source_status(source: SignalSource, now: datetime, stale_after_days: int) -> tuple[str, str | None]:
    if source.last_status is FetchStatus.NOT_CONFIGURED:
        return "not_configured", "Not configured: FRED_API_KEY is not set, so these series are not fetched."
    if source.last_status is FetchStatus.FAILED:
        when = f" on {source.last_attempt_at:%d %b %Y}" if source.last_attempt_at else ""
        return "stale", f"The last refresh failed{when}: {_readable(source.last_error) or 'unknown error'}"
    if source.last_status is FetchStatus.PARTIAL:  # e.g. GDELT stopped by its rate limit midway
        when = f" on {source.last_attempt_at:%d %b %Y}" if source.last_attempt_at else ""
        return "stale", f"The last refresh{when} was incomplete: {_readable(source.last_error) or 'some requests failed'}"
    if source.last_success_at is None:
        return "never_fetched", "Not fetched yet: run make signals-backfill."
    if now - source.last_success_at > timedelta(days=stale_after_days):
        return "stale", f"Not refreshed for {_age(now, source.last_success_at)}."
    return "fresh", None


def news_status(source: SignalSource, now: datetime, stale_after_days: int, stored: int) -> tuple[str, str | None]:
    """News arrives per category and window, so a run cut short leaves earlier runs' headlines
    in place: partial, not stale. Its reason is written for the page; GDELT's own 429 text
    (an email address and an ngrams pitch) stays in make signals-status."""
    if source.last_status in (FetchStatus.FAILED, FetchStatus.PARTIAL) and stored:
        when = f" on {source.last_attempt_at:%d %b %Y}" if source.last_attempt_at else ""
        why = ("stopped at GDELT's rate limit (HTTP 429)" if "HTTP 429" in (source.last_error or "")
               else "did not finish")
        return "partial", (f"The last news run{when} {why}, so only headlines stored by earlier runs "
                           "are shown.")
    return source_status(source, now, stale_after_days)


def _news_stored(db: Session) -> int:
    return db.scalar(select(func.count(NewsItem.id))) or 0


def series_status(series: SignalSeries, source: SignalSource, now: datetime) -> tuple[str, str | None]:
    if source.last_status is FetchStatus.NOT_CONFIGURED and series.last_success_at is None:
        return "not_configured", "Not configured: FRED_API_KEY is not set, so this series is not fetched."
    if series.last_error:
        when = f" on {series.last_attempt_at:%d %b %Y}" if series.last_attempt_at else ""
        return "stale", f"The last refresh failed{when}: {_readable(series.last_error)}"
    if series.last_success_at is None:
        return "never_fetched", "Not fetched yet: run make signals-backfill."
    if now - series.last_success_at > timedelta(days=series.stale_after_days):
        return "stale", f"Not refreshed for {_age(now, series.last_success_at)}."
    return "fresh", None


def _source_out(source: SignalSource, status: tuple[str, str | None]) -> SourceStatus:
    return SourceStatus(code=source.code, name=source.name, homepage=source.homepage, licence=source.licence,
                        attribution=source.attribution, terms_url=source.terms_url,
                        requires_key=source.requires_key, last_attempt_at=source.last_attempt_at,
                        last_success_at=source.last_success_at, last_error=_readable(source.last_error),
                        status=status[0], status_reason=status[1])


class _Loaded:
    """Every series and source, read once per request."""

    def __init__(self, db: Session, now: datetime):
        self.now = now
        self.sources = {s.id: s for s in db.scalars(select(SignalSource))}
        self.series = {s.id: s for s in db.scalars(select(SignalSeries))}
        self.by_key = {s.key: s for s in self.series.values()}
        self.forecast_of = {s.companion_key: s.key for s in self.series.values() if s.is_forecast}
        self.first = dict(db.execute(select(SignalObservation.series_id, func.min(SignalObservation.observed_on))
                                     .group_by(SignalObservation.series_id)).all())

    def info(self, series: SignalSeries) -> SeriesInfo:
        source = self.sources[series.source_id]
        status = series_status(series, source, self.now)
        return SeriesInfo(
            key=series.key, label=series.label, description=series.description, unit=series.unit,
            geography=series.geography, geography_name=series.geography_name, frequency=series.frequency.value,
            aggregation=series.aggregation.value, role=series.role.value, group_key=series.group_key,
            forecast_key=self.forecast_of.get(series.key), source=source.code, source_name=source.name,
            source_homepage=source.homepage, attribution=source.attribution, citation=series.citation,
            first_observed_on=self.first.get(series.id), latest_observed_on=series.latest_observed_on,
            last_success_at=series.last_success_at, last_attempt_at=series.last_attempt_at,
            status=status[0], status_reason=status[1])

    def mapped(self, rows: list[SignalMapping]) -> tuple[list[MappedSeries], list[MappedSeries]]:
        demand, cost = [], []
        for row in sorted(rows, key=lambda r: (r.sort_order, self.series[r.series_id].key)):
            item = MappedSeries(series=self.info(self.series[row.series_id]), reason=row.reason)
            (demand if row.role.value == "demand_context" else cost).append(item)
        return demand, cost


def overview(db: Session, now: datetime | None = None) -> MarketOverview:
    now = now or utcnow()
    loaded = _Loaded(db, now)
    categories = [c for (c,) in db.execute(select(Product.category).distinct().order_by(Product.category))]
    mappings = list(db.scalars(select(SignalMapping).where(SignalMapping.category.is_not(None))))
    for c in sorted({m.category for m in mappings} - set(categories)):
        categories.append(c)  # mapped categories show even before the catalog is seeded
    blocks = []
    for category in categories:
        demand, cost = loaded.mapped([m for m in mappings if m.category == category])
        blocks.append(CategoryMarket(category=category, demand_context=demand, input_cost=cost))
    stale_news = load_catalog().file.news.stale_after_days
    sources = []
    for source in sorted(loaded.sources.values(), key=lambda s: s.id):
        if source.code == "gdelt":
            status = news_status(source, now, stale_news, _news_stored(db))
        else:
            status = source_status(source, now, min(
                (s.stale_after_days for s in loaded.series.values() if s.source_id == source.id), default=3))
        sources.append(_source_out(source, status))
    bounds = data_bounds(db)
    return MarketOverview(sales_first_date=bounds[0] if bounds else None,
                          sales_last_date=bounds[1] if bounds else None, categories=blocks, sources=sources)


def product_market(db: Session, sku: str, now: datetime | None = None) -> ProductMarket:
    product = db.scalars(select(Product).where(Product.sku == sku)).one_or_none()
    if product is None:
        raise NotFoundError(f"Unknown sku: {sku}")
    loaded = _Loaded(db, now or utcnow())
    demand, cost = loaded.mapped(list(db.scalars(select(SignalMapping).where(SignalMapping.sku == sku))))
    return ProductMarket(sku=product.sku, name=product.name, category=product.category,
                         demand_context=demand, input_cost=cost)


def series_data(db: Session, keys: list[str], granularity: Granularity, date_from: date | None,
                date_to: date | None) -> list[SeriesData]:
    found = {s.key: s for s in db.scalars(select(SignalSeries).where(SignalSeries.key.in_(keys)))}
    missing = [k for k in keys if k not in found]
    if missing:
        raise NotFoundError(f"Unknown signal series: {', '.join(missing)}")
    out = []
    for key in dict.fromkeys(keys):
        series = found[key]
        g = Granularity.MONTH if series.frequency.value == "monthly" else granularity
        bucket = period_start_expr(SignalObservation.observed_on, g).label("bucket")
        agg = func.avg if series.aggregation.value == "mean" else func.sum
        stmt = (select(bucket, agg(SignalObservation.value), func.count())
                .where(SignalObservation.series_id == series.id))
        if date_from:
            stmt = stmt.where(SignalObservation.observed_on >= date_from)
        if date_to:
            stmt = stmt.where(SignalObservation.observed_on <= date_to)
        rows = db.execute(stmt.group_by(bucket).order_by(bucket)).all()
        points = [SignalPoint(period_start=b if isinstance(b, date) else date.fromisoformat(str(b)),
                              value=round(float(v), 4), days=int(n)) for b, v, n in rows]
        out.append(SeriesData(key=key, granularity=g.value, aggregation=series.aggregation.value,
                              is_forecast=series.is_forecast, points=points))
    return out


def headlines(db: Session, category: str, limit: int, now: datetime | None = None) -> HeadlinesResponse:
    topics = [t.category for t in load_catalog().file.news.topics]
    if category not in topics:
        raise NotFoundError(f"No news topic for category: {category}")
    source = db.scalars(select(SignalSource).where(SignalSource.code == "gdelt")).one_or_none()
    if source is None:
        raise NotFoundError("No news source yet: run make signals-backfill.")
    base = select(NewsItem).join(NewsItemCategory).where(NewsItemCategory.category == category)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = db.scalars(base.order_by(NewsItem.published_at.desc(), NewsItem.id.desc()).limit(limit)).all()
    status = news_status(source, now or utcnow(), load_catalog().file.news.stale_after_days, _news_stored(db))
    return HeadlinesResponse(
        category=category, total=total, source=_source_out(source, status),
        items=[Headline(title=i.title, url=i.url, publisher=i.publisher, published_at=i.published_at,
                        language=i.language) for i in items])
