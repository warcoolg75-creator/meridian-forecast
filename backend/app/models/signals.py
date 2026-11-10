"""External market signals (phase 6a): weather, attention, input costs and news.

Context only. The sales data is synthetic and its generator never saw any of these, so
nothing here is a forecasting input; the forecasting code never imports this module.

The tables stand apart from the seeded data on purpose: no foreign key points at
products or regions (mappings name a SKU or category, series name a region code), so
`make seed` can wipe and regenerate the pinned dataset without touching fetched signals,
which take up to an hour to backfill (GDELT).

Provenance: every observation and news row carries `fetched_at` and `fetch_id`, the
signal_fetches row of the run that last wrote it, which names the source, the mode and
where its raw responses were cached.
"""

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UTCDateTime, enum_type, utcnow
from app.models.enums import (
    FetchMode,
    FetchStatus,
    SignalAggregation,
    SignalFrequency,
    SignalRole,
)


class SignalSource(Base):
    """One provider (Open-Meteo, FRED, Wikimedia, GDELT), synced from the signals catalog."""

    __tablename__ = "signal_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32), unique=True)
    name: Mapped[str] = mapped_column(sa.String(80))
    homepage: Mapped[str] = mapped_column(sa.String(200))
    licence: Mapped[str] = mapped_column(sa.String(200))
    attribution: Mapped[str] = mapped_column(sa.String(400))
    terms_url: Mapped[str] = mapped_column(sa.String(300))
    requires_key: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_status: Mapped[FetchStatus | None] = mapped_column(enum_type(FetchStatus, "fetch_status"))
    last_error: Mapped[str | None] = mapped_column(sa.String(500))  # always redacted
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SignalSeries(Base):
    """One measured quantity: a variable at a place, at one frequency, in one unit.

    `geography` is a region code (a city, "IN") or "WORLD". `group_key` puts the same
    variable in different cities on one card. A forecast series (`is_forecast`) holds only
    the latest forecast and names the observed series it continues (`companion_key`).
    """

    __tablename__ = "signal_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(sa.ForeignKey("signal_sources.id"), index=True)
    key: Mapped[str] = mapped_column(sa.String(80), unique=True)
    label: Mapped[str] = mapped_column(sa.String(120))
    description: Mapped[str] = mapped_column(sa.String(400))
    unit: Mapped[str] = mapped_column(sa.String(60))
    geography: Mapped[str] = mapped_column(sa.String(16))
    geography_name: Mapped[str] = mapped_column(sa.String(80))
    frequency: Mapped[SignalFrequency] = mapped_column(enum_type(SignalFrequency, "signal_frequency"))
    aggregation: Mapped[SignalAggregation] = mapped_column(enum_type(SignalAggregation, "signal_aggregation"))
    role: Mapped[SignalRole] = mapped_column(enum_type(SignalRole, "signal_role"))
    group_key: Mapped[str] = mapped_column(sa.String(40))
    is_forecast: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    companion_key: Mapped[str | None] = mapped_column(sa.String(80))
    external_id: Mapped[str] = mapped_column(sa.String(120))
    params: Mapped[dict] = mapped_column(sa.JSON)
    citation: Mapped[str | None] = mapped_column(sa.String(400))
    stale_after_days: Mapped[int] = mapped_column(sa.SmallInteger)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(sa.String(500))  # always redacted
    latest_observed_on: Mapped[date | None] = mapped_column(sa.Date)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SignalFetch(Base):
    """One run of one source: the provenance every observation and news row points to."""

    __tablename__ = "signal_fetches"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(sa.ForeignKey("signal_sources.id"), index=True)
    mode: Mapped[FetchMode] = mapped_column(enum_type(FetchMode, "fetch_mode"))
    status: Mapped[FetchStatus] = mapped_column(enum_type(FetchStatus, "fetch_status"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    requests: Mapped[int] = mapped_column(sa.Integer, default=0)
    inserted: Mapped[int] = mapped_column(sa.Integer, default=0)
    updated: Mapped[int] = mapped_column(sa.Integer, default=0)
    deleted: Mapped[int] = mapped_column(sa.Integer, default=0)
    unchanged: Mapped[int] = mapped_column(sa.Integer, default=0)
    error: Mapped[str | None] = mapped_column(sa.String(500))  # always redacted
    cache_dir: Mapped[str | None] = mapped_column(sa.String(300))
    detail: Mapped[dict | None] = mapped_column(sa.JSON)


class SignalObservation(Base):
    __tablename__ = "signal_observations"
    __table_args__ = (sa.UniqueConstraint("series_id", "observed_on", name="uq_signal_observations_series_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(sa.ForeignKey("signal_series.id", ondelete="CASCADE"))
    observed_on: Mapped[date] = mapped_column(sa.Date)
    value: Mapped[float] = mapped_column(sa.Float)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    fetch_id: Mapped[int | None] = mapped_column(sa.ForeignKey("signal_fetches.id"), index=True)


class SignalMapping(Base):
    """Which series matter to which category (the market page) or SKU (its product page),
    and why. Data from the signals catalog, never hard-coded in a page."""

    __tablename__ = "signal_mappings"
    __table_args__ = (
        sa.CheckConstraint("(category IS NULL) <> (sku IS NULL)", name="category_or_sku"),
        sa.Index("ix_signal_mappings_category", "category"),
        sa.Index("ix_signal_mappings_sku", "sku"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id: Mapped[int] = mapped_column(sa.ForeignKey("signal_series.id", ondelete="CASCADE"))
    category: Mapped[str | None] = mapped_column(sa.String(60))
    sku: Mapped[str | None] = mapped_column(sa.String(32))
    role: Mapped[SignalRole] = mapped_column(enum_type(SignalRole, "signal_role"))
    reason: Mapped[str] = mapped_column(sa.String(400))
    sort_order: Mapped[int] = mapped_column(sa.SmallInteger, default=0)


class NewsItem(Base):
    """A headline and its metadata, never the article body. `published_at` is when GDELT
    first saw the article (its `seendate`); GDELT does not give the publisher's time."""

    __tablename__ = "news_items"
    __table_args__ = (sa.Index("ix_news_items_published_at", "published_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(sa.ForeignKey("signal_sources.id"))
    url: Mapped[str] = mapped_column(sa.Text)
    url_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)  # sha256 of url: urls outgrow an index
    title: Mapped[str] = mapped_column(sa.String(500))
    published_at: Mapped[datetime] = mapped_column(UTCDateTime)
    language: Mapped[str] = mapped_column(sa.String(40))
    publisher: Mapped[str] = mapped_column(sa.String(200))
    source_country: Mapped[str] = mapped_column(sa.String(60))
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    fetch_id: Mapped[int | None] = mapped_column(sa.ForeignKey("signal_fetches.id"), index=True)


class NewsItemCategory(Base):
    """The categories whose keyword query matched a headline (one row each)."""

    __tablename__ = "news_item_categories"
    __table_args__ = (sa.Index("ix_news_item_categories_category", "category"),)

    news_item_id: Mapped[int] = mapped_column(sa.ForeignKey("news_items.id", ondelete="CASCADE"),
                                              primary_key=True)
    category: Mapped[str] = mapped_column(sa.String(60), primary_key=True)


SIGNAL_TABLES = tuple(m.__tablename__ for m in (
    SignalSource, SignalSeries, SignalFetch, SignalObservation, SignalMapping, NewsItem, NewsItemCategory))
