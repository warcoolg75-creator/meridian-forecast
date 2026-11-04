"""Responses of /api/v1/analytics/*. Money in paise, quantities as integers, dates ISO."""

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import Channel, EventType, RegionLevel
from app.schemas.catalog import ProductRead
from app.services.bucketing import Granularity


class ComparisonMode(StrEnum):
    """same_period_last_year: the same days 52 weeks (364 days) earlier, so weekdays line
    up. previous_period: the window of equal length immediately before."""

    SAME_PERIOD_LAST_YEAR = "same_period_last_year"
    PREVIOUS_PERIOD = "previous_period"


class PeriodInfo(BaseModel):
    """A window as used: clipped to the stored history when the request reached past it."""

    date_from: date
    date_to: date
    days: int
    days_with_data: int


class ComparisonInfo(PeriodInfo):
    mode: ComparisonMode
    shift_days: int = Field(description="How far back the comparison window sits")
    complete: bool = Field(description="Every comparison day has history; otherwise changes are withheld")


class Coverage(BaseModel):
    first_date: date | None
    last_date: date | None


class Totals(BaseModel):
    revenue_minor: int
    units: int
    orders: int = Field(description="Distinct orders (sales_orders), not order lines")
    gross_margin_minor: int = Field(description="Revenue minus units x today's unit cost")
    average_selling_price_minor: int | None = Field(description="Revenue / units, rounded; null without units")
    margin_rate: float | None = Field(description="Gross margin / revenue; null without revenue")


class Changes(BaseModel):
    """Relative change against the comparison period (0.062 = +6.2%). Null when the
    comparison is incomplete or its value is zero."""

    revenue: float | None
    units: float | None
    orders: float | None
    gross_margin: float | None
    average_selling_price: float | None


class SummaryResponse(BaseModel):
    period: PeriodInfo
    comparison: ComparisonInfo
    current: Totals
    baseline: Totals = Field(description="Totals for the comparison period")
    change: Changes


class TimeseriesPoint(BaseModel):
    """One bucket of the current period and the same days in the comparison period."""

    period_start: date
    period_end: date
    days_covered: int
    is_partial: bool
    units: int
    revenue_minor: int
    baseline_units: int
    baseline_revenue_minor: int
    baseline_days_covered: int = Field(
        description="How many of this bucket's days have comparison history (see baseline_history): equal "
                    "to days_covered when the comparison is whole, fewer when partial, 0 when missing"
    )


class BaselineHistory(BaseModel):
    """Where the comparison's history begins: the first day of data or, when the rows are
    filtered to products, the earliest launch among them if that is later. A comparison day
    before it has no sales to compare with, not zero sales."""

    first_date: date
    starts_with: Literal["data", "launch"]


class MovingEvent(BaseModel):
    """A festival or holiday that falls on a different date in the two periods.

    aligned_date is where the comparison occurrence lands on this period's axis
    (comparison_date + shift_days); days_apart = current_date - aligned_date. Either date
    is null when the event falls in only one of the two periods.
    """

    name: str
    region_code: str | None
    current_date: date | None
    comparison_date: date | None
    aligned_date: date | None
    days_apart: int | None


class TimeseriesResponse(BaseModel):
    period: PeriodInfo
    comparison: ComparisonInfo
    granularity: Granularity
    points: list[TimeseriesPoint]
    baseline_history: BaselineHistory | None = Field(description="Null when there is no data at all")
    moving_events: list[MovingEvent] = Field(
        description="Only for same_period_last_year: festivals whose date moved by more than 3 days"
    )


AbcClass = Literal["A", "B", "C"]
XyzClass = Literal["X", "Y", "Z"]


class ProductRow(BaseModel):
    rank: int = Field(description="By revenue in the period, 1 = highest")
    sku: str
    name: str
    category: str
    revenue_minor: int
    units: int
    gross_margin_minor: int
    share: float = Field(description="Share of the rows' total revenue")
    baseline_revenue_minor: int
    growth: float | None = Field(description="Revenue change against the comparison period")
    abc: AbcClass | None
    xyz: XyzClass | None = Field(description="Null: under 13 full weeks of sales history")
    xyz_cv: float | None
    xyz_weeks: int = Field(description="Full weeks the coefficient of variation was computed over")
    sparkline: list[int] = Field(description="Units per full week, the last 13 weeks to date_to, oldest first")


class Classification(BaseModel):
    """How abc and xyz were computed (see app/services/analytics/classify.py)."""

    abc_a_share: float
    abc_b_share: float
    xyz_x_below: float
    xyz_y_up_to: float
    xyz_window: PeriodInfo
    xyz_min_weeks: int


class ProductSort(StrEnum):
    RANK = "rank"
    SKU = "sku"
    NAME = "name"
    CATEGORY = "category"
    REVENUE = "revenue"
    UNITS = "units"
    MARGIN = "margin"
    SHARE = "share"
    GROWTH = "growth"
    ABC = "abc"
    XYZ = "xyz"


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class ProductsResponse(BaseModel):
    period: PeriodInfo
    comparison: ComparisonInfo
    classification: Classification
    sort: ProductSort
    order: SortOrder
    rows: list[ProductRow]


class RegionRow(BaseModel):
    code: str
    name: str
    level: RegionLevel
    parent_code: str | None
    revenue_minor: int
    units: int
    share: float = Field(description="Share of the rows' total revenue (of the parent, when drilling down)")
    baseline_revenue_minor: int
    growth: float | None


class RegionsResponse(BaseModel):
    period: PeriodInfo
    comparison: ComparisonInfo
    level: RegionLevel
    parent_code: str | None
    rows: list[RegionRow]


class ChannelRow(BaseModel):
    channel: Channel
    revenue_minor: int
    units: int
    share: float
    baseline_revenue_minor: int
    baseline_share: float | None
    growth: float | None


class ChannelsResponse(BaseModel):
    period: PeriodInfo
    comparison: ComparisonInfo
    rows: list[ChannelRow]


class ProductEvent(BaseModel):
    """A calendar event that can move this product's demand or supply.

    scope: product (its promotions), national / regional (holidays and festivals),
    plant (shutdowns at a plant with a line that makes it).
    """

    date: date
    end_date: date
    name: str
    event_type: EventType
    scope: Literal["product", "national", "regional", "plant"]
    region_code: str | None
    plant_code: str | None
    impact_note: str | None


class ProductDetail(ProductRead):
    events: list[ProductEvent]
    events_from: date | None
    events_to: date | None
