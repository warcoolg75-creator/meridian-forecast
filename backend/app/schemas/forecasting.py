from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import MetricWindow, ShockScope


class RunInfo(BaseModel):
    id: int
    kind: Literal["production", "backtest"]
    data_end_date: date = Field(description="Last day with sales data")
    training_cutoff: date = Field(description="Monday of the last complete week the models were trained on")
    trained_at: datetime
    random_seed: int
    library_versions: dict[str, str]


class Assumptions(BaseModel):
    promotions: str
    supply_shocks: str


class ForecastWeek(BaseModel):
    week: date = Field(description="Monday")
    horizon: int
    p50: int = Field(description="Median units")
    lo80: int
    hi80: int
    lo95: int
    hi95: int


class SkuForecast(BaseModel):
    """Modelled: units per SKU per week, from the SKU's champion model."""

    sku: str
    name: str
    model: str = Field(description="The champion that produced it (picked on backtest WAPE)")
    short_history: bool = Field(description="Under 52 weeks of history: no seasonal-naive baseline; LightGBM only")
    weeks: list[ForecastWeek]


class ForecastsResponse(BaseModel):
    run: RunInfo
    assumptions: Assumptions
    items: list[SkuForecast]


class AllocatedWeek(BaseModel):
    week: date
    horizon: int
    p50: int


class AllocatedGroup(BaseModel):
    code: str
    name: str
    share: float = Field(description="Share of the SKU's units in the trailing 13 weeks")
    weeks: list[AllocatedWeek]


class Allocation(BaseModel):
    """Allocated, not modelled: the SKU's p50 split by its trailing 13-week shares. Medians
    only: a share of an interval is not an interval."""

    view: Literal["state", "channel"]
    allocated: Literal[True] = True
    method: str
    share_from: date
    share_to: date
    groups: list[AllocatedGroup]


class SkuForecastResponse(BaseModel):
    run: RunInfo
    assumptions: Assumptions
    forecast: SkuForecast
    allocation: Allocation | None = Field(description="Present for view=state or view=channel")


class MetricRow(BaseModel):
    model: str = Field(description="A model, 'champion' (each SKU's champion) or 'oracle' (expected demand)")
    sku: str | None = Field(description="Null: the headline SKUs pooled")
    window: MetricWindow
    shocks: ShockScope
    horizon: int | None = Field(description="Null: horizons 1-26 pooled")
    n_weeks: int
    wape: float | None
    bias: float | None
    mase: float | None
    coverage_80: float | None = Field(description="Held-out window only")
    coverage_95: float | None


class MetricsResponse(BaseModel):
    run: RunInfo
    items: list[MetricRow]


class LeaderboardRow(BaseModel):
    model: str
    wape: float | None
    skill: float | None = Field(description="1 - WAPE / seasonal naive's WAPE (pooled, volume-weighted)")
    median_sku_skill: float | None = Field(description="Median of per-SKU skill: every SKU counts once")
    bias: float | None
    mase: float | None
    coverage_80: float | None
    coverage_95: float | None
    n_weeks: int


class ChampionRow(BaseModel):
    sku: str
    model: str
    short_history: bool
    wape: float | None
    baseline_wape: float | None
    skill: float | None
    coverage_80: float | None


class LeaderboardResponse(BaseModel):
    run: RunInfo
    window: MetricWindow
    shocks: ShockScope
    target_skill: float = Field(description="The landing page's target: 15% lower error than seasonal naive")
    headline_skus: list[str]
    models: list[LeaderboardRow]
    champions: list[ChampionRow]


# ---- Phase 5b: the forecast page ----

class OverviewRow(BaseModel):
    sku: str
    name: str
    model: str
    short_history: bool
    next_4: int = Field(description="Sum of p50, horizons 1-4")
    next_13: int = Field(description="Sum of p50, horizons 1-13")
    last_year_4: int | None = Field(description="Actual units of the same 4 weeks 52 weeks (364 days) earlier; "
                                                "null when any of them is before the SKU's launch or the history")
    last_year_13: int | None
    change_4: float | None = Field(description="next_4 / last_year_4 - 1")
    change_13: float | None
    no_comparison_reason: str | None
    skill: float | None = Field(description="Held-out, horizons 1-26, all weeks: 1 - champion WAPE / seasonal "
                                            "naive WAPE. Null without a seasonal-naive forecast")
    abc: str | None = Field(description="By revenue over the 52 weeks to the training cutoff")
    forecastability: str | None = Field(description="XYZ on the champion's backtest error CV (X < 0.5, Y 0.5-1, Z > 1)")
    error_cv: float | None


class ForecastOverviewResponse(BaseModel):
    run: RunInfo
    backtest_run_id: int
    assumptions: Assumptions
    models: list[str] = Field(description="Distinct models behind the stored forecasts")
    abc_from: date
    abc_to: date
    xyz_x_below: float = Field(description="Forecastability X: error CV below this")
    xyz_y_up_to: float = Field(description="Forecastability Y: error CV up to this; Z above")
    items: list[OverviewRow]


class ActualWeek(BaseModel):
    week: date
    units: int | None = Field(description="Null before the SKU's launch")


class HorizonEvent(BaseModel):
    date: date
    end_date: date
    week: date = Field(description="Monday of the forecast week it falls in")
    name: str
    event_type: Literal["public_holiday", "festival"]
    region_code: str | None = Field(description="Null: national")


class SkuAccuracy(BaseModel):
    """The champion's held-out scores, horizons 1-26 pooled, all weeks, as stored."""

    model: str
    n_weeks: int
    wape: float | None
    baseline_wape: float | None
    skill: float | None
    bias: float | None
    coverage_80: float | None
    coverage_95: float | None


class PastForecastWeek(BaseModel):
    week: date
    origin: date = Field(description="First week of the forecast it comes from")
    weeks_before: int = Field(description="Horizon: the forecast was made this many weeks before (1-4)")
    actual: int
    p50: float
    lo80: float
    hi80: float


class SkuForecastContext(BaseModel):
    run: RunInfo
    backtest_run_id: int
    sku: str
    name: str
    short_history: bool
    launched_on: date
    actuals: list[ActualWeek] = Field(description="The 52 complete weeks to the training cutoff")
    events: list[HorizonEvent] = Field(description="Holidays and festivals inside the 26 forecast weeks")
    accuracy: SkuAccuracy | None
    held_out_from: date
    past_forecasts: list[PastForecastWeek] = Field(
        description="Each held-out week against the latest forecast made 1-4 weeks before it, with its 80% "
                    "interval (empty until make backtest-forecasts has run)")


class OracleTestScore(BaseModel):
    skus: list[str]
    champion_wape: float | None
    naive_wape: float | None
    skill: float | None


class OracleTestResponse(BaseModel):
    """The forward oracle test stored with the production run: its forecast against expected
    demand with no promotions and no shocks. Not comparable with backtest WAPE."""

    run: RunInfo
    weeks_from: date
    weeks_to: date
    pooled: OracleTestScore
    festive: OracleTestScore
