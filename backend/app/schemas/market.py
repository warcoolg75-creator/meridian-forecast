"""Market signals (phase 6a): context beside our sales, never a forecasting input."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

CONTEXT_NOTE = "Context only. Our sales data is synthetic, so these signals are not used in the forecast."
SHAPES_NOTE = "Similar shapes here reflect shared seasons, not cause and effect."

SignalStatus = Literal["fresh", "stale", "partial", "never_fetched", "not_configured"]


class SourceStatus(BaseModel):
    code: str
    name: str
    homepage: str
    licence: str
    attribution: str
    terms_url: str
    requires_key: bool
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    status: SignalStatus
    status_reason: str | None


class SeriesInfo(BaseModel):
    key: str
    label: str
    description: str
    unit: str
    geography: str
    geography_name: str
    frequency: Literal["daily", "weekly", "monthly"]
    aggregation: Literal["mean", "sum"]
    role: Literal["demand_context", "input_cost"]
    group_key: str
    forecast_key: str | None = Field(description="The series holding this one's latest forecast, if any")
    source: str
    source_name: str
    source_homepage: str
    attribution: str
    citation: str | None
    first_observed_on: date | None
    latest_observed_on: date | None
    last_success_at: datetime | None
    last_attempt_at: datetime | None
    status: SignalStatus
    status_reason: str | None


class MappedSeries(BaseModel):
    series: SeriesInfo
    reason: str


class CategoryMarket(BaseModel):
    category: str
    demand_context: list[MappedSeries]
    input_cost: list[MappedSeries]


class MarketOverview(BaseModel):
    note: str = CONTEXT_NOTE
    sales_first_date: date | None
    sales_last_date: date | None
    categories: list[CategoryMarket]
    sources: list[SourceStatus]


class SignalPoint(BaseModel):
    period_start: date
    value: float
    days: int = Field(description="Observations in the period (a partial week has fewer than 7)")


class SeriesData(BaseModel):
    key: str
    granularity: Literal["day", "week", "month"]
    aggregation: Literal["mean", "sum"]
    is_forecast: bool
    points: list[SignalPoint]


class SeriesDataResponse(BaseModel):
    items: list[SeriesData]


class Headline(BaseModel):
    title: str
    url: str
    publisher: str
    published_at: datetime = Field(description="When GDELT first saw the article, not the publisher's timestamp")
    language: str


class HeadlinesResponse(BaseModel):
    category: str
    items: list[Headline]
    total: int
    source: SourceStatus


class ProductMarket(BaseModel):
    note: str = CONTEXT_NOTE
    shapes_note: str = SHAPES_NOTE
    sku: str
    name: str
    category: str
    demand_context: list[MappedSeries]
    input_cost: list[MappedSeries]
