"""Rolling-origin backtest: every model, scored against actuals, the oracle and each other.

Origins: 13, every 4 weeks across the last 52 complete weeks (first forecast weeks
w/c 2025-10-06 ... 2026-09-07 on the pinned data). At each origin every model is trained
on `history.until(origin - 1)` and forecasts 26 weeks; weeks with actuals are scored.

Windows:
  selection  target weeks before the held-out window. Champions are picked here.
  held_out   the last 13 complete weeks; never used to pick a model or set an interval.
  festive_2025  selection targets in Sep-Nov 2025 (a labelled subset: the held-out window
             holds no festive peak).
Every score is computed with all weeks and without supply-shock weeks.

v2: the champion of every SKU is the mean of Prophet and LightGBM (ENSEMBLE); short-history
SKUs get intervals from a simulation (long-history SKUs forecast as if they were young);
each v2 decision is re-checked on the selection window in every run (`notes`).
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.forecasting import intervals, oracle
from app.forecasting.calendar import merged_festivals, moving_festivals
from app.forecasting.data import SalesHistory
from app.forecasting.metrics import bias, coverage, mase, skill, wape
from app.forecasting.models import (
    BASELINE,
    CALENDAR_AWARE,
    ENSEMBLE,
    ENSEMBLE_PARTS,
    HORIZON,
    MODEL_NAMES,
    SEASON,
    Forecaster,
    all_models,
)
from app.forecasting.models.lightgbm_model import LightGBMGlobal
from app.forecasting.models.prophet_model import DIP_RULES, REGRESSOR_WINDOWS, collapsed_weeks
from app.services.analytics import classify

ORIGIN_EVERY = 4
ORIGIN_COUNT = 13
HELD_OUT_WEEKS = 13
# Interval method check inside the selection window: calibrate before, test from this week.
INTERVAL_CHECK_FROM = date(2026, 4, 6)
FESTIVE_2025 = (date(2025, 9, 1), date(2025, 11, 30))
REPORTED_HORIZONS = (1, 4, 13, 26)
CHAMPION, ORACLE = "champion", "oracle"
XYZ_ERROR_HORIZONS = 13
FESTIVE_CATEGORIES = ("Packaged Foods", "Kitchen Appliances")
MARGIN = 0.10  # candidate (a): a per-SKU champion only when it beats the default by this much
YOUNG_AGE = 30  # weeks of data a simulated young SKU keeps (the Air Fryer had 15-35)


@dataclass
class BacktestResult:
    pairs: pd.DataFrame
    champions: dict[str, str]
    headline_skus: list[str]
    short_history_skus: list[str]
    metrics: list[dict]
    quantiles_all: dict
    xyz: list[dict]
    origins: list[date]
    held_out_start: date
    notes: dict = field(default_factory=dict)


def origin_indices(history: SalesHistory) -> list[int]:
    first = history.last - (ORIGIN_EVERY * (ORIGIN_COUNT - 1) + ORIGIN_EVERY - 1)
    return [first + ORIGIN_EVERY * k for k in range(ORIGIN_COUNT)]


def forecast_origin(history: SalesHistory, origin: int, models: list[Forecaster], seed: int) -> dict:
    """Every model's forecasts made at `origin` (the first forecast week), each trained on
    the weeks before it only."""
    past = history.until(origin - 1)
    return {model.name: model.forecast(past, HORIZON, seed) for model in models}


def seasonal_naive_scale(history: SalesHistory, s: int, cutoff: int) -> float:
    """MASE's denominator: in-sample MAE of last-year's-actual on weeks up to the cutoff."""
    units = history.units[s, : cutoff + 1]
    diffs = np.abs(units[SEASON:] - units[:-SEASON])
    diffs = diffs[~np.isnan(diffs)]
    return float(diffs.mean()) if diffs.size else np.nan


def run_backtest(history: SalesHistory, seed: int = 42, models: list[Forecaster] | None = None,
                 progress: Callable[[str], None] = lambda _: None) -> BacktestResult:
    models = models or all_models()
    origins = origin_indices(history)
    held_out_start = history.weeks[history.last - HELD_OUT_WEEKS + 1]
    rows = []
    for origin in origins:
        started = time.perf_counter()
        forecasts = forecast_origin(history, origin, models, seed)
        for model, by_sku in forecasts.items():
            for sku, values in by_sku.items():
                s = next(x.index for x in history.skus if x.sku == sku)
                scale = seasonal_naive_scale(history, s, origin - 1)
                for h in range(1, HORIZON + 1):
                    t = origin + h - 1
                    if t > history.last:
                        break
                    actual, p50 = history.units[s, t], values[h - 1]
                    if np.isnan(actual) or np.isnan(p50):
                        continue
                    rows.append((model, sku, history.weeks[origin], h, history.weeks[t], float(actual),
                                 float(p50), scale))
        progress(f"origin {history.weeks[origin]}: {time.perf_counter() - started:.1f}s")

    pairs = pd.DataFrame(rows, columns=["model", "sku", "origin", "horizon", "target", "actual", "p50", "scale"])
    if all(name in {m.name for m in models} for name in ENSEMBLE_PARTS):
        pairs = _with_ensemble(pairs)
    weeks_of_data = {(s.sku, history.weeks[o]): history.until(o - 1).weeks_since_launch(s.index)
                     for s in history.skus for o in origins}
    pairs["weeks_of_data"] = [weeks_of_data[(sku, origin)] for sku, origin in zip(pairs["sku"], pairs["origin"],
                                                                                    strict=True)]
    shocks = oracle.shock_weeks()
    pairs["window"] = np.where(pairs["target"] < held_out_start, "selection", "held_out")
    pairs["shock"] = [(sku, target) in shocks for sku, target in zip(pairs["sku"], pairs["target"], strict=True)]
    pairs["festive"] = (pairs["window"] == "selection") & pairs["target"].between(*FESTIVE_2025)

    baseline_skus = set(pairs.loc[pairs["model"] == BASELINE, "sku"])
    headline_skus = sorted(baseline_skus)
    short_history = sorted(set(pairs["sku"]) - baseline_skus)

    champions = _pick_champions(pairs, history)
    pairs = _with_champion_and_oracle(pairs, champions)
    real = pairs["model"].isin([*MODEL_NAMES, ENSEMBLE])
    lightgbm = next((m for m in models if isinstance(m, LightGBMGlobal)), None)
    young = _young_errors(history, origins, lightgbm, seed, held_out_start, progress) if lightgbm else None
    selection_quantiles = intervals.fit_quantiles(pairs[(pairs["window"] == "selection") & real])
    quantiles_all = intervals.fit_quantiles(pairs[real])
    if young is not None and not young.empty:
        selection_quantiles.update(intervals.fit_quantiles(young[young["target"] < held_out_start]))
        quantiles_all.update(intervals.fit_quantiles(young))
    pairs = _with_intervals(pairs, selection_quantiles)

    held = pairs[(pairs["window"] == "held_out") & (pairs["model"] == CHAMPION)]
    notes = {
        "festive_first_target": str(pairs.loc[pairs["festive"], "target"].min()),
        "champion_p50_outside_80": float(((held["p50"] < held["lo80"]) | (held["p50"] > held["hi80"])).mean()),
        "pairs": len(pairs),
        "interval_check": interval_check(pairs),
        "after_shock": after_shock(pairs, shocks),
        "champion_check": champion_check(pairs, history),
        "young_check": young_check(young, pairs, held_out_start) if young is not None else None,
        "dip_audit": dip_audit(history, held_out_start),
        "festival_merges": [list(g) for g in merged_festivals(history.calendar.festivals, list(REGRESSOR_WINDOWS))
                            if len(g) > 1],
        "moving_festivals": moving_festivals(history.calendar.festivals),
    }
    return BacktestResult(
        pairs=pairs, champions=champions, headline_skus=headline_skus, short_history_skus=short_history,
        metrics=compute_metrics(pairs, history, headline_skus), quantiles_all=quantiles_all,
        xyz=_xyz(pairs, history, champions), origins=[history.weeks[o] for o in origins],
        held_out_start=held_out_start, notes=notes,
    )


def after_shock(pairs: pd.DataFrame, shocks: set) -> dict:
    """WAPE at horizons 1-4 when the last training week was a supply-shock week for that SKU,
    against every other origin: how far a model carries a shock into the next weeks."""
    early = pairs[(pairs["horizon"] <= 4) & pairs["model"].isin([*MODEL_NAMES, ENSEMBLE, ORACLE])]
    hit = np.array([(sku, origin - timedelta(weeks=1)) in shocks
                    for sku, origin in zip(early["sku"], early["origin"], strict=True)])
    out = {}
    for model, rows in early.groupby("model", sort=True):
        flag = hit[early.index.get_indexer(rows.index)]
        out[str(model)] = {
            "after_shock": wape(rows.loc[flag, "actual"].to_numpy(), rows.loc[flag, "p50"].to_numpy()),
            "otherwise": wape(rows.loc[~flag, "actual"].to_numpy(), rows.loc[~flag, "p50"].to_numpy()),
            "after_shock_weeks": int(flag.sum()),
        }
    return out


def interval_check(pairs: pd.DataFrame) -> dict:
    """Champions' coverage with per-SKU and with pooled (per model) error quantiles,
    calibrated on selection targets before INTERVAL_CHECK_FROM and measured on the rest of
    the selection window: how the pooled method was chosen without the held-out window."""
    selection = pairs[(pairs["window"] == "selection") & (pairs["model"] != ORACLE)]
    calibrate = selection[(selection["target"] < INTERVAL_CHECK_FROM)
                          & selection["model"].isin([*MODEL_NAMES, ENSEMBLE])]
    check = selection[(selection["target"] >= INTERVAL_CHECK_FROM) & (selection["model"] == CHAMPION)]
    errors = calibrate.assign(error=intervals.log_errors(calibrate["actual"].to_numpy(), calibrate["p50"].to_numpy()),
                              group=calibrate["horizon"].map(intervals.group_of))
    check = check.assign(group=check["horizon"].map(intervals.group_of))
    out: dict = {"calibrated_before": str(INTERVAL_CHECK_FROM)}
    if errors.empty or check.empty:  # a history that does not reach the check week
        return {**out, "per_sku": {"coverage_80": None, "coverage_95": None, "n": 0},
                "pooled": {"coverage_80": None, "coverage_95": None, "n": 0}}
    for method, keys in (("per_sku", ["source", "sku", "group"]), ("pooled", ["source", "group"])):
        table = {k: np.quantile(r["error"], intervals.QUANTILES) for k, r in errors.groupby(keys)}
        pooled = {k: np.quantile(r["error"], intervals.QUANTILES) for k, r in errors.groupby(["source", "group"])}
        q = np.array([table.get(tuple(row), pooled[(row[0], row[-1])]) for row in check[keys].itertuples(index=False)])
        f = (check["p50"].to_numpy()[:, None] + 1) * np.exp(q) - 1
        y = check["actual"].to_numpy()
        out[method] = {"coverage_80": float(np.mean((y >= f[:, 1]) & (y <= f[:, 2]))),
                       "coverage_95": float(np.mean((y >= f[:, 0]) & (y <= f[:, 3]))), "n": len(y)}
    return out


def _pick_champions(pairs: pd.DataFrame, history: SalesHistory) -> dict[str, str]:
    """v2: the ensemble for every SKU it covers. Where it was not run (the fast test
    fixtures), v1's rule: the lowest selection-window WAPE, calendar-aware models only for
    the festive categories when one is available."""
    # The ensemble needs no selection data: a SKU forecast only in the held-out window still
    # gets it (and so a production forecast).
    champions = {str(sku): ENSEMBLE for sku in sorted(pairs.loc[pairs["model"] == ENSEMBLE, "sku"].unique())}
    selection = pairs[(pairs["window"] == "selection") & ~pairs["sku"].isin(list(champions))]
    festive = {s.sku for s in history.skus if s.category in FESTIVE_CATEGORIES}
    for sku, rows in selection.groupby("sku", sort=True):
        scores = {model: wape(r["actual"].to_numpy(), r["p50"].to_numpy()) for model, r in rows.groupby("model")}
        scored = {m: w for m, w in scores.items() if w is not None}
        if sku in festive and any(m in CALENDAR_AWARE for m in scored):
            scored = {m: w for m, w in scored.items() if m in CALENDAR_AWARE}
        champions[str(sku)] = min(sorted(scored), key=lambda m: scored[m])
    return champions


def _with_ensemble(pairs: pd.DataFrame) -> pd.DataFrame:
    """The mean of Prophet's and LightGBM's p50 for every forecast-week; LightGBM's alone
    where Prophet has none (a short-history SKU)."""
    parts = pairs[pairs["model"].isin(ENSEMBLE_PARTS)]
    keys = [c for c in pairs.columns if c not in ("model", "p50")]  # every per-forecast-week column
    mean = parts.groupby(keys, sort=True, dropna=False)["p50"].mean().reset_index()
    return pd.concat([pairs, mean.assign(model=ENSEMBLE)[pairs.columns]], ignore_index=True)


def champion_check(pairs: pd.DataFrame, history: SalesHistory) -> dict:
    """The v2 champion decision, re-run on every backtest: candidates chosen on selection
    targets before INTERVAL_CHECK_FROM and judged on the rest of the selection window.
      v1     each SKU's lowest WAPE
      margin a per-SKU champion only where it beats a default (lowest pooled WAPE) by MARGIN;
             calendar-aware models only for festive SKUs
      mean   the mean of Prophet and LightGBM for every SKU"""
    selection = pairs[(pairs["window"] == "selection") & pairs["model"].isin([*MODEL_NAMES, ENSEMBLE])]
    early = selection[selection["target"] < INTERVAL_CHECK_FROM]
    late = selection[selection["target"] >= INTERVAL_CHECK_FROM]
    if early.empty or late.empty or not (selection["model"] == ENSEMBLE).any():
        return {}
    headline = sorted(set(selection.loc[selection["model"] == BASELINE, "sku"]))
    festive = {s.sku for s in history.skus if s.category in FESTIVE_CATEGORIES}

    def w(rows: pd.DataFrame, model: str, sku: str | None = None) -> float | None:
        r = rows[(rows["model"] == model) & (rows["sku"] == sku if sku else rows["sku"].isin(headline))]
        return wape(r["actual"].to_numpy(), r["p50"].to_numpy()) if len(r) else None

    def scores(sku: str, candidates) -> dict:
        return {m: v for m in candidates if (v := w(early, m, sku)) is not None}

    skus = sorted(selection["sku"].unique())
    v1, margin = {}, {}
    default = min(("ets", "prophet", "lightgbm"), key=lambda m: w(early, m) or np.inf)
    festive_default = default if default in CALENDAR_AWARE else min(("prophet", "lightgbm"),
                                                                    key=lambda m: w(early, m) or np.inf)
    for sku in skus:
        every = scores(sku, MODEL_NAMES)
        v1[sku] = min(every, key=every.get) if every else "lightgbm"
        candidates = ("prophet", "lightgbm") if sku in festive else MODEL_NAMES
        base = festive_default if sku in festive else default
        sc = scores(sku, candidates)
        best = min(sc, key=sc.get) if sc else "lightgbm"
        margin[sku] = best if (base not in sc or sc[best] <= (1 - MARGIN) * sc[base]) else base

    def judge(assignment: dict) -> dict:
        chosen = pd.concat([late[(late["sku"] == s) & (late["model"] == m)] for s, m in assignment.items()])
        per_sku = [skill(w(chosen.assign(model="x"), "x", s), w(late, BASELINE, s)) for s in headline]
        festive_rows = chosen[chosen["sku"].isin(festive & set(headline))]
        return {"pooled_wape": w(chosen.assign(model="x"), "x"),
                "median_sku_skill": float(np.median([v for v in per_sku if v is not None])),
                "festive_wape": wape(festive_rows["actual"].to_numpy(), festive_rows["p50"].to_numpy())}

    return {"v1": judge(v1), "margin": {**judge(margin), "default": default, "margin": MARGIN},
            "mean": judge({s: ENSEMBLE for s in skus}), "baseline_pooled_wape": w(late, BASELINE),
            "judged_from": str(INTERVAL_CHECK_FROM)}


def _young_errors(history: SalesHistory, origins: list[int], model: LightGBMGlobal, seed: int,
                  held_out_start: date, progress: Callable[[str], None]) -> pd.DataFrame:
    """LightGBM's errors for long-history SKUs made young: at each origin, half of them lose
    every week before (origin - YOUNG_AGE), as if launched then, and the model is trained with
    the other half intact. Their errors are what a short-history SKU's intervals come from."""
    long = [s for s in history.skus if history.weeks_since_launch(s.index) >= 2 * SEASON]
    rows = []
    for origin in origins:
        for group in (long[0::2], long[1::2]):
            units = history.units.copy()
            for sku in group:
                units[sku.index, : origin - YOUNG_AGE] = np.nan
            units.setflags(write=False)
            young = SalesHistory(history.weeks, units, history.skus, history.calendar, history.data_end)
            forecasts = model.forecast(young.until(origin - 1), HORIZON, seed)
            for sku in group:
                for h in range(1, HORIZON + 1):
                    t = origin + h - 1
                    if t > history.last or sku.sku not in forecasts:
                        break
                    if np.isnan(history.units[sku.index, t]):
                        continue
                    rows.append((intervals.YOUNG, sku.sku, history.weeks[origin], h, history.weeks[t],
                                 float(history.units[sku.index, t]), float(forecasts[sku.sku][h - 1])))
        progress(f"young-SKU simulation, origin {history.weeks[origin]}")
    return pd.DataFrame(rows, columns=["model", "sku", "origin", "horizon", "target", "actual", "p50"])


def young_check(young: pd.DataFrame, pairs: pd.DataFrame, held_out_start: date) -> dict:
    """On simulated young SKUs, selection window only: coverage of intervals from the young
    errors against intervals from LightGBM's long-history errors (calibrated before
    INTERVAL_CHECK_FROM, measured from it to the held-out start)."""
    young = young[young["target"] < held_out_start]
    late = young[young["target"] >= INTERVAL_CHECK_FROM]
    long = pairs[(pairs["model"] == "lightgbm") & (pairs["window"] == "selection")
                 & (pairs["target"] < INTERVAL_CHECK_FROM)]
    out = {}
    for name, source in (("young", young[young["target"] < INTERVAL_CHECK_FROM]),
                         ("long_history", long.assign(model=intervals.YOUNG))):
        if source.empty or late.empty:
            return {}
        table = intervals.fit_quantiles(source.assign(model=intervals.YOUNG))
        b = intervals.bounds(table, intervals.YOUNG, late["horizon"].to_numpy(), late["p50"].to_numpy())
        y = late["actual"].to_numpy()
        out[name] = {"coverage_80": float(np.mean((y >= b[:, 1]) & (y <= b[:, 2]))),
                     "coverage_95": float(np.mean((y >= b[:, 0]) & (y <= b[:, 3]))), "n": len(y)}
    full = intervals.fit_quantiles(young.assign(model="y"))["y"]
    base = intervals.fit_quantiles(pairs[(pairs["model"] == "lightgbm") & (pairs["window"] == "selection")])
    out["width_ratio_80"] = {g: round((full[g][2] - full[g][1]) / (base["lightgbm"][g][2] - base["lightgbm"][g][1]), 2)
                             for g in full if g in base.get("lightgbm", {})}
    return out


def dip_audit(history: SalesHistory, held_out_start: date) -> dict:
    """Which weeks each Prophet dip rule leaves out, against the ground truth's shock days
    (scoring only), on the history before the held-out window."""
    shock_days = oracle.shock_days_by_week()
    past = history.until(history.index(held_out_start) - 1)
    def summary(c: dict) -> dict:
        return {**c, "precision": c["true"] / c["dropped"] if c["dropped"] else None,
                "recall": c["true"] / c["shock_weeks"] if c["shock_weeks"] else None,
                "recall_3_day": c["caught_3_day"] / c["shock_weeks_3_day"] if c["shock_weeks_3_day"] else None}

    out = {"to": str(past.weeks[-1])}
    for rule in DIP_RULES[1:]:
        per_sku, total = {}, dict.fromkeys(("dropped", "true", "shock_weeks", "shock_weeks_3_day", "caught_3_day"), 0)
        for sku in past.skus:
            units = past.units[sku.index]
            flag = collapsed_weeks(units, rule) & ~np.isnan(units)
            days = np.array([shock_days.get((sku.sku, w), 0) for w in past.weeks])
            counts = {"dropped": int(flag.sum()), "true": int((flag & (days > 0)).sum()),
                      "shock_weeks": int((days > 0).sum()), "shock_weeks_3_day": int((days >= 3).sum()),
                      "caught_3_day": int((flag & (days >= 3)).sum())}
            per_sku[sku.sku] = summary(counts)
            total = {k: total[k] + counts[k] for k in total}
        out[rule] = {"all": summary(total), "per_sku": per_sku}
    return out


def _with_champion_and_oracle(pairs: pd.DataFrame, champions: dict[str, str]) -> pd.DataFrame:
    champion = pd.concat([pairs[(pairs["sku"] == sku) & (pairs["model"] == model)] for sku, model in champions.items()])
    champion = champion.assign(source=champion["model"], model=CHAMPION)
    keys = pairs.drop_duplicates(["sku", "origin", "horizon"])
    skus = sorted(keys["sku"].unique())
    weeks = sorted(keys["target"].unique())
    expected = oracle.expected_weekly(skus, weeks)
    column = {w: i for i, w in enumerate(weeks)}
    oracle_rows = keys.assign(model=ORACLE, source=ORACLE,
                              p50=[expected[s][column[t]] for s, t in zip(keys["sku"], keys["target"], strict=True)])
    return pd.concat([pairs.assign(source=pairs["model"]), champion, oracle_rows], ignore_index=True)


def _with_intervals(pairs: pd.DataFrame, quantiles: dict) -> pd.DataFrame:
    """Interval bounds on held-out rows, from selection-window errors only; a short-history
    SKU's from the young table."""
    bounds = np.full((len(pairs), 4), np.nan)
    held = (pairs["window"] == "held_out") & (pairs["model"] != ORACLE)
    for (source, weeks), rows in pairs[held].groupby(["source", "weeks_of_data"]):
        key = intervals.table_key(quantiles, str(source), int(weeks))
        if key not in quantiles:
            continue
        bounds[rows.index] = intervals.bounds(quantiles, key, rows["horizon"].to_numpy(), rows["p50"].to_numpy())
    return pairs.assign(lo95=bounds[:, 0], lo80=bounds[:, 1], hi80=bounds[:, 2], hi95=bounds[:, 3])


def compute_metrics(pairs: pd.DataFrame, history: SalesHistory, headline_skus: list[str]) -> list[dict]:
    """One row per model x SKU (None = headline SKUs pooled) x window x shocks x horizon
    (None = 1-26 pooled). Coverage only on the held-out window."""
    out = []
    windows = {
        "selection": pairs["window"] == "selection",
        "held_out": pairs["window"] == "held_out",
        "festive_2025": pairs["festive"],
    }
    for model in (*MODEL_NAMES, ENSEMBLE, CHAMPION, ORACLE):
        by_model = pairs[pairs["model"] == model]
        for window, in_window in windows.items():
            for shocks in ("included", "excluded"):
                rows = by_model[in_window[by_model.index]]
                if shocks == "excluded":
                    rows = rows[~rows["shock"]]
                for sku in [None, *sorted(rows["sku"].unique())]:
                    sku_rows = rows[rows["sku"].isin(headline_skus)] if sku is None else rows[rows["sku"] == sku]
                    for horizon in (None, *REPORTED_HORIZONS):
                        r = sku_rows if horizon is None else sku_rows[sku_rows["horizon"] == horizon]
                        if r.empty:
                            continue
                        out.append(_score(r, model, sku, window, shocks, horizon))
    return out


def _score(r: pd.DataFrame, model: str, sku: str | None, window: str, shocks: str, horizon: int | None) -> dict:
    y, f = r["actual"].to_numpy(), r["p50"].to_numpy()
    interval = window == "held_out" and model != ORACLE
    return {
        "model": model, "sku": sku, "window": window, "shocks": shocks, "horizon": horizon, "n_weeks": len(r),
        "wape": wape(y, f), "bias": bias(y, f), "mase": mase(y, f, r["scale"].to_numpy()),
        "coverage_80": coverage(y, r["lo80"].to_numpy(), r["hi80"].to_numpy()) if interval else None,
        "coverage_95": coverage(y, r["lo95"].to_numpy(), r["hi95"].to_numpy()) if interval else None,
    }


def _xyz(pairs: pd.DataFrame, history: SalesHistory, champions: dict[str, str]) -> list[dict]:
    """XYZ twice: on weekly volume (phase 4's measure: CV of the last 52 weeks' units) and on
    the champion's forecast errors (std of actual - p50 over mean actual, horizons 1-13,
    every backtest week), with the same thresholds."""
    out = []
    weeks = classify.xyz_weeks(history.data_end, history.weeks[0], history.data_end)
    for sku in history.skus:
        indices = [history.index(w) for w in weeks if w in history.weeks and w >= sku.launched_on]
        volume = history.units[sku.index, indices]
        volume_cv = classify.coefficient_of_variation([float(v) for v in volume if not np.isnan(v)])
        r = pairs[(pairs["model"] == CHAMPION) & (pairs["sku"] == sku.sku) & (pairs["horizon"] <= XYZ_ERROR_HORIZONS)]
        error_cv = float(np.std(r["actual"] - r["p50"], ddof=1) / r["actual"].mean()) if len(r) > 1 else None
        out.append({"sku": sku.sku, "champion": champions.get(sku.sku), "volume_cv": volume_cv,
                    "volume_xyz": classify.xyz_class(volume_cv), "error_cv": error_cv,
                    "error_xyz": classify.xyz_class(error_cv), "error_weeks": len(r)})
    return out
