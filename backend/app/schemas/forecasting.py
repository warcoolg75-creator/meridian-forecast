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
