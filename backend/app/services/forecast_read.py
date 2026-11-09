"""Reads for the forecast and backtest endpoints. No model code: everything here comes from
the stored runs (app.forecasting writes them)."""

import statistics
from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session, aliased

from app.models import (
    BacktestForecast,
    BacktestMetric,
    CalendarEvent,
    EventType,
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
    ActualWeek,
    Allocation,
    AllocatedGroup,
    AllocatedWeek,
    Assumptions,
    ChampionRow,
    ForecastOverviewResponse,
    ForecastWeek,
    HorizonEvent,
    LeaderboardRow,
    MetricRow,
    OracleTestResponse,
    OracleTestScore,
    OverviewRow,
    PastForecastWeek,
    RunInfo,
    SkuAccuracy,
    SkuForecast,
    SkuForecastContext,
)
from app.services.analytics import classify
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


# ---- Phase 5b: the forecast page ----

LAST_YEAR = timedelta(days=364)  # 52 weeks: weekdays line up, as in the analytics comparison
ACTUAL_WEEKS = 52
ABC_WEEKS = 52
PAST_MAX_HORIZON = 4
CSV_COLUMNS = ("sku", "week", "horizon", "model", "p50", "lo80", "hi80", "lo95", "hi95")


def backtest_of(session: Session, production: ForecastRun) -> ForecastRun:
    """The backtest run a production run's champions and intervals came from."""
    run_id = production.params.get("backtest_run_id")
    run = session.get(ForecastRun, run_id) if run_id else None
    return run or latest(session, ForecastRunKind.BACKTEST)


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _weekly_units(session: Session, first: date, last: date) -> dict[tuple[str, date], int]:
    rows = session.execute(
        sa.select(Product.sku, WeeklySales.period_start, sa.func.sum(WeeklySales.units))
        .join(Product, Product.id == WeeklySales.product_id)
        .where(WeeklySales.period_start.between(first, last))
        .group_by(Product.sku, WeeklySales.period_start))
    return {(sku, week): int(units) for sku, week, units in rows}


def overview(session: Session, run: ForecastRun) -> ForecastOverviewResponse:
    """Per SKU: the next 4 and 13 weeks' p50 against the same weeks 52 weeks earlier, the
    held-out skill, ABC (revenue, 52 weeks to the cutoff) and forecastability (XYZ on the
    champion's backtest error CV, stored with the backtest run)."""
    items = sku_forecasts(session, run)
    backtest = backtest_of(session, run)
    launched = dict(session.execute(sa.select(Product.sku, Product.launched_on)).all())
    history_from = session.scalar(sa.select(WeeklySales.period_start).order_by(WeeklySales.period_start).limit(1))
    starts = [w.week for i in items for w in i.weeks]
    last_year = _weekly_units(session, min(starts) - LAST_YEAR, max(starts) - LAST_YEAR) if starts else {}
    abc_from = run.training_cutoff - timedelta(weeks=ABC_WEEKS - 1)
    abc_to = run.training_cutoff + timedelta(days=6)
    revenue = dict(session.execute(
        sa.select(Product.sku, sa.func.coalesce(sa.func.sum(WeeklySales.revenue_minor), 0))
        .outerjoin(WeeklySales, sa.and_(WeeklySales.product_id == Product.id,
                                        WeeklySales.period_start.between(abc_from, run.training_cutoff)))
        .group_by(Product.sku)).all())
    abc = classify.abc_classes({sku: int(v) for sku, v in revenue.items()})
    xyz = {r["sku"]: r for r in backtest.params.get("xyz", [])}
    champions = {c.sku: c for c in leaderboard(session, backtest, MetricWindow.HELD_OUT, ShockScope.INCLUDED)[1]}

    rows = []
    for item in items:
        launch = _monday(launched[item.sku])

        def sums(h: int) -> tuple[int, int | None, float | None]:
            weeks = [w for w in item.weeks if w.horizon <= h]
            ahead = sum(w.p50 for w in weeks)
            before = [w.week - LAST_YEAR for w in weeks]
            if any(d < launch or history_from is None or d < history_from for d in before):
                return ahead, None, None
            past = sum(last_year.get((item.sku, d), 0) for d in before)
            return ahead, past, (ahead / past - 1) if past else None

        n4, ly4, c4 = sums(4)
        n13, ly13, c13 = sums(13)
        on = launched[item.sku]
        reason = (f"Launched {on.day} {on:%b %Y}: no sales in the same weeks last year"
                  if ly4 is None or ly13 is None else None)
        champion = champions.get(item.sku)
        x = xyz.get(item.sku, {})
        rows.append(OverviewRow(
            sku=item.sku, name=item.name, model=item.model, short_history=item.short_history, next_4=n4,
            next_13=n13, last_year_4=ly4, last_year_13=ly13, change_4=c4, change_13=c13,
            no_comparison_reason=reason, skill=champion.skill if champion else None, abc=abc.get(item.sku),
            forecastability=x.get("error_xyz"), error_cv=x.get("error_cv")))
    return ForecastOverviewResponse(run=run_info(run), backtest_run_id=backtest.id, assumptions=assumptions(run),
                                    models=sorted({i.model for i in items}), abc_from=abc_from, abc_to=abc_to,
                                    xyz_x_below=classify.XYZ_X_BELOW, xyz_y_up_to=classify.XYZ_Y_UP_TO, items=rows)


def limit_horizon(forecast: SkuForecast, horizon: int) -> SkuForecast:
    return forecast.model_copy(update={"weeks": [w for w in forecast.weeks if w.horizon <= horizon]})


def forecast_csv(forecast: SkuForecast) -> str:
    lines = [",".join(CSV_COLUMNS)]
    lines += [",".join(str(v) for v in (forecast.sku, w.week.isoformat(), w.horizon, forecast.model, w.p50, w.lo80,
                                        w.hi80, w.lo95, w.hi95)) for w in forecast.weeks]
    return "\n".join(lines) + "\n"


def context(session: Session, run: ForecastRun, forecast: SkuForecast) -> SkuForecastContext:
    """What the SKU forecast page draws around the forecast: 52 weeks of actuals, the
    holidays and festivals in the horizon, the stored held-out scores and the held-out
    weeks against the latest forecast made 1-4 weeks before each."""
    backtest = backtest_of(session, run)
    product = session.scalars(sa.select(Product).where(Product.sku == forecast.sku)).one()
    weeks = [run.training_cutoff - timedelta(weeks=k) for k in range(ACTUAL_WEEKS - 1, -1, -1)]
    units = _weekly_units(session, weeks[0], weeks[-1])
    launch = _monday(product.launched_on)
    actuals = [ActualWeek(week=w, units=None if w < launch else units.get((forecast.sku, w), 0)) for w in weeks]

    first, last = forecast.weeks[0].week, forecast.weeks[-1].week + timedelta(days=6)
    events = [
        HorizonEvent(date=e.date, end_date=e.end_date, week=_monday(e.date), name=e.name,
                     event_type=e.event_type.value, region_code=code)
        for e, code in session.execute(
            sa.select(CalendarEvent, Region.code).outerjoin(Region, Region.id == CalendarEvent.region_id)
            .where(CalendarEvent.event_type.in_([EventType.PUBLIC_HOLIDAY, EventType.FESTIVAL]),
                   CalendarEvent.date.between(first, last))
            .order_by(CalendarEvent.date, CalendarEvent.name)).all()
    ]

    rows = {r.model: r for r in metric_rows(session, backtest, None, forecast.sku, MetricWindow.HELD_OUT,
                                            ShockScope.INCLUDED, None) if r.horizon is None}
    champion, base = rows.get("champion"), rows.get(BASELINE)
    accuracy = None if champion is None else SkuAccuracy(
        model=backtest.params.get("champions", {}).get(forecast.sku, forecast.model), n_weeks=champion.n_weeks,
        wape=champion.wape, baseline_wape=base.wape if base else None,
        skill=None if base is None or champion.wape is None or not base.wape else 1 - champion.wape / base.wape,
        bias=champion.bias, coverage_80=champion.coverage_80, coverage_95=champion.coverage_95)

    past = [PastForecastWeek(week=f.week, origin=f.origin, weeks_before=f.horizon, actual=f.actual, p50=f.p50,
                             lo80=f.lo80, hi80=f.hi80)
            for f in session.scalars(sa.select(BacktestForecast).where(
                BacktestForecast.run_id == backtest.id, BacktestForecast.product_id == product.id,
                BacktestForecast.horizon <= PAST_MAX_HORIZON).order_by(BacktestForecast.week))]
    held_out_from = date.fromisoformat(backtest.params.get("held_out_start", run.training_cutoff.isoformat()))
    return SkuForecastContext(run=run_info(run), backtest_run_id=backtest.id, sku=forecast.sku, name=forecast.name,
                              short_history=forecast.short_history, launched_on=product.launched_on,
                              actuals=actuals, events=events, accuracy=accuracy, held_out_from=held_out_from,
                              past_forecasts=past)


def oracle_test(run: ForecastRun) -> OracleTestResponse:
    stored = run.params.get("forward_oracle")
    if not stored:
        raise NotFoundError("This forecast run has no forward oracle test: run make forecast")

    def score(part: dict) -> OracleTestScore:
        return OracleTestScore(skus=part["skus"], champion_wape=part["champion_wape"],
                               naive_wape=part["naive_wape"], skill=part["skill"])

    return OracleTestResponse(run=run_info(run), weeks_from=stored["weeks"][0], weeks_to=stored["weeks"][1],
                              pooled=score(stored["pooled"]), festive=score(stored["festive_pooled"]))
