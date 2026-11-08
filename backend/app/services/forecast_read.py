"""Reads for the forecast and backtest endpoints. No model code: everything here comes from
the stored runs (app.forecasting writes them)."""

import statistics
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from app.models import (
    BacktestMetric,
    Forecast,
    ForecastRun,
    ForecastRunKind,
    MetricWindow,
    Product,
    Region,
    RegionLevel,
    ShockScope,
    WeeklySales,
)
from app.schemas.forecasting import (
    Allocation,
    AllocatedGroup,
    AllocatedWeek,
    Assumptions,
    ChampionRow,
    ForecastWeek,
    LeaderboardRow,
    MetricRow,
    RunInfo,
    SkuForecast,
)
from app.services.errors import NotFoundError

SHARE_WEEKS = 13
BASELINE = "seasonal_naive"
TARGET_SKILL = 0.15
DEFAULT_ASSUMPTIONS = {"promotions": "none planned after the data end", "supply_shocks": "never forecast"}


def latest(session: Session, kind: ForecastRunKind) -> ForecastRun:
    run = session.scalars(sa.select(ForecastRun).where(ForecastRun.kind == kind)
                          .order_by(ForecastRun.id.desc()).limit(1)).first()
    if run is None:
        raise NotFoundError("No forecast run yet: run make backtest, then make forecast"
                            if kind == ForecastRunKind.PRODUCTION else "No backtest run yet: run make backtest")
    return run


def run_info(run: ForecastRun) -> RunInfo:
    return RunInfo(id=run.id, kind=run.kind.value, data_end_date=run.data_end_date,
                   training_cutoff=run.training_cutoff, trained_at=run.trained_at, random_seed=run.random_seed,
                   library_versions=run.library_versions)


def assumptions(run: ForecastRun) -> Assumptions:
    return Assumptions(**{**DEFAULT_ASSUMPTIONS, **run.params.get("assumptions", {})})


def sku_forecasts(session: Session, run: ForecastRun, skus: list[str] | None = None) -> list[SkuForecast]:
    stmt = (sa.select(Forecast, Product.sku, Product.name).join(Product, Product.id == Forecast.product_id)
            .where(Forecast.run_id == run.id).order_by(Product.sku, Forecast.week))
    if skus:
        stmt = stmt.where(Product.sku.in_(skus))
    short = set(run.params.get("short_history_skus", []))
    out: dict[str, SkuForecast] = {}
    for f, sku, name in session.execute(stmt):
        item = out.get(sku)
        if item is None:
            item = out[sku] = SkuForecast(sku=sku, name=name, model=f.model, short_history=sku in short, weeks=[])
        item.weeks.append(ForecastWeek(week=f.week, horizon=f.horizon, p50=f.p50, lo80=f.lo80, hi80=f.hi80,
                                       lo95=f.lo95, hi95=f.hi95))
    return list(out.values())


def allocation(session: Session, run: ForecastRun, forecast: SkuForecast, view: str) -> Allocation:
    """The SKU's weekly p50 split by its trailing 13-week shares of units (as of the run's
    training cutoff), by state (a city counts toward its state) or by channel. Each week is
    rounded so the groups add up to the SKU's p50 exactly (largest remainder)."""
    share_to = run.training_cutoff
    share_from = share_to - timedelta(weeks=SHARE_WEEKS - 1)
    product_id = session.scalar(sa.select(Product.id).where(Product.sku == forecast.sku))
    window = (WeeklySales.product_id == product_id, WeeklySales.period_start.between(share_from, share_to))
    if view == "state":
        state = aliased(Region)
        state_id = sa.case((Region.level == RegionLevel.STATE, Region.id), else_=Region.parent_region_id)
        rows = session.execute(
            sa.select(state.code, state.name, sa.func.sum(WeeklySales.units))
            .join(Region, Region.id == WeeklySales.region_id).join(state, state.id == state_id)
            .where(*window).group_by(state.code, state.name).order_by(state.code)
        ).all()
    else:
        rows = [(channel.value, channel.value.capitalize(), units) for channel, units in session.execute(
            sa.select(WeeklySales.channel, sa.func.sum(WeeklySales.units)).where(*window)
            .group_by(WeeklySales.channel).order_by(WeeklySales.channel))]
    total = sum(int(u) for _, _, u in rows)
    shares = [(code, name, int(units) / total) for code, name, units in rows if total and units]
    split = [_largest_remainder(w.p50, [s for _, _, s in shares]) for w in forecast.weeks]
    groups = [
        AllocatedGroup(code=code, name=name, share=round(share, 6), weeks=[
            AllocatedWeek(week=w.week, horizon=w.horizon, p50=parts[i]) for w, parts in zip(forecast.weeks, split,
                                                                                            strict=True)])
        for i, (code, name, share) in enumerate(shares)
    ]
    return Allocation(view=view, method=f"p50 x the SKU's share of units over {SHARE_WEEKS} weeks", share_from=share_from,
                      share_to=share_to + timedelta(days=6), groups=groups)


def _largest_remainder(total: int, shares: list[float]) -> list[int]:
    raw = [total * s for s in shares]
    parts = [int(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - parts[i]), i))
    for i in order[: total - sum(parts)]:
        parts[i] += 1
    return parts


def metric_rows(session: Session, run: ForecastRun, model: str | None, sku: str | None,
                window: MetricWindow | None, shocks: ShockScope | None, horizon: int | None) -> list[MetricRow]:
    stmt = (sa.select(BacktestMetric, Product.sku).outerjoin(Product, Product.id == BacktestMetric.product_id)
            .where(BacktestMetric.run_id == run.id)
            .order_by(BacktestMetric.model, Product.sku.nulls_first(), BacktestMetric.window, BacktestMetric.shocks,
                      BacktestMetric.horizon.nulls_first()))
    if model:
        stmt = stmt.where(BacktestMetric.model == model)
    if sku:
        stmt = stmt.where(Product.sku == sku)
    if window:
        stmt = stmt.where(BacktestMetric.window == window)
    if shocks:
        stmt = stmt.where(BacktestMetric.shocks == shocks)
    if horizon:
        stmt = stmt.where(BacktestMetric.horizon == horizon)
    return [MetricRow(model=m.model, sku=s, window=m.window, shocks=m.shocks, horizon=m.horizon, n_weeks=m.n_weeks,
                      wape=m.wape, bias=m.bias, mase=m.mase, coverage_80=m.coverage_80, coverage_95=m.coverage_95)
            for m, s in session.execute(stmt)]


def leaderboard(session: Session, run: ForecastRun, window: MetricWindow,
                shocks: ShockScope) -> tuple[list[LeaderboardRow], list[ChampionRow]]:
    rows = [r for r in metric_rows(session, run, None, None, window, shocks, None) if r.horizon is None]
    pooled = {r.model: r for r in rows if r.sku is None}
    per_sku = {(r.model, r.sku): r for r in rows if r.sku is not None}
    headline = run.params.get("headline_skus", [])

    def skill(model_wape: float | None, base: float | None) -> float | None:
        return None if model_wape is None or not base else 1 - model_wape / base

    base = pooled.get(BASELINE)
    models = []
    for name, r in pooled.items():
        sku_skills = [s for s in (skill(per_sku[(name, k)].wape, per_sku[(BASELINE, k)].wape)
                                  for k in headline if (name, k) in per_sku and (BASELINE, k) in per_sku)
                      if s is not None]
        models.append(LeaderboardRow(
            model=name, wape=r.wape, skill=None if name == BASELINE else skill(r.wape, base.wape if base else None),
            median_sku_skill=None if name == BASELINE or not sku_skills else statistics.median(sku_skills),
            bias=r.bias, mase=r.mase, coverage_80=r.coverage_80, coverage_95=r.coverage_95, n_weeks=r.n_weeks))
    models.sort(key=lambda m: (m.wape is None, m.wape))
    short = set(run.params.get("short_history_skus", []))
    champions = []
    for sku, model in sorted(run.params.get("champions", {}).items()):
        c, b = per_sku.get(("champion", sku)), per_sku.get((BASELINE, sku))
        champions.append(ChampionRow(sku=sku, model=model, short_history=sku in short, wape=c.wape if c else None,
                                     baseline_wape=b.wape if b else None,
                                     skill=skill(c.wape if c else None, b.wape if b else None),
                                     coverage_80=c.coverage_80 if c else None))
    return models, champions
