"""The production forecast: each SKU's champion, trained on every complete week.

Champions and interval widths come from the latest backtest (make backtest first). The
forecast starts the week after the last complete week (w/c 2026-10-05 on the pinned data,
whose last day is Thursday 2026-10-08: that week's four recorded days are not used, as at
every backtest origin). No promotion is recorded after the data end, so none is assumed.

v2: the champion is the mean of Prophet and LightGBM (LightGBM alone where Prophet cannot
fit, i.e. the Air Fryer), and a SKU with under a year of data gets the young interval table.
"""

import hashlib
import json

import numpy as np

from app.forecasting import intervals
from app.forecasting.data import SalesHistory
from app.forecasting.models import ENSEMBLE, ENSEMBLE_PARTS, HORIZON, model_by_name


def ensemble(by_model: dict[str, dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    """The mean of the parts' p50 per SKU, over the parts that forecast it."""
    skus = sorted({sku for name in ENSEMBLE_PARTS for sku in by_model[name]})
    return {sku: np.mean([by_model[name][sku] for name in ENSEMBLE_PARTS if sku in by_model[name]], axis=0)
            for sku in skus}


def model_used(by_model: dict[str, dict[str, np.ndarray]], champion: str, sku: str) -> str:
    """The model that actually produced a SKU's forecast. The ensemble is the mean of the
    parts that forecast the SKU: both, it is the ensemble; one (Prophet cannot fit a
    short-history SKU), it is that part alone, and is stored under that part's name. Needs
    the parts' own forecasts to tell; without them it refuses rather than guess."""
    if champion != ENSEMBLE:
        return champion
    if not all(name in by_model for name in ENSEMBLE_PARTS):
        raise ValueError("The ensemble's parts are needed to record which model produced each forecast")
    used = [name for name in ENSEMBLE_PARTS if sku in by_model[name]]
    return ENSEMBLE if len(used) == len(ENSEMBLE_PARTS) else used[0]


def model_forecasts(history: SalesHistory, names: set[str], seed: int) -> dict[str, dict[str, np.ndarray]]:
    """Each named model's p50 per SKU; the ensemble from its parts."""
    single = ({*names} - {ENSEMBLE}) | (set(ENSEMBLE_PARTS) if ENSEMBLE in names else set())
    by_model = {name: model_by_name(name).forecast(history, HORIZON, seed) for name in sorted(single)}
    if ENSEMBLE in names:
        by_model[ENSEMBLE] = ensemble(by_model)
    return by_model


def forecast_rows(history: SalesHistory, champions: dict[str, str], quantiles: dict, seed: int,
                  by_model: dict[str, dict[str, np.ndarray]] | None = None) -> list[dict]:
    """Integer units per SKU and week: the champion's p50 and its 80% / 95% intervals.
    `by_model` reuses forecasts already made (the CLI makes every model's anyway).

    Each row's `model` is the model actually used (model_used): LightGBM for a SKU the
    ensemble could only forecast with LightGBM. Its interval table is still looked up under
    the champion's name, as the backtest calibrated it. (Runs before this, up to forecast
    run 8, stored the champion's name, prophet_lightgbm, for the Air Fryer too.)"""
    weeks = history.future_weeks(HORIZON)
    horizons = np.arange(1, HORIZON + 1)
    by_model = by_model or model_forecasts(history, set(champions.values()), seed)
    index = {s.sku: s.index for s in history.skus}
    rows = []
    for sku, model in sorted(champions.items()):
        p50 = by_model[model].get(sku)
        if p50 is None:
            continue
        used = model_used(by_model, model, sku)
        table = intervals.table_key(quantiles, model, history.weeks_since_launch(index[sku]))
        lo95, lo80, hi80, hi95 = intervals.bounds(quantiles, table, horizons, p50).T
        for i, week in enumerate(weeks):
            rows.append({
                "sku": sku, "week": week, "horizon": i + 1, "model": used,
                "p50": int(np.rint(p50[i])), "lo80": int(np.rint(lo80[i])), "hi80": int(np.rint(hi80[i])),
                "lo95": int(np.rint(lo95[i])), "hi95": int(np.rint(hi95[i])),
            })
    return rows


def digest(rows: list[dict]) -> str:
    """SHA-256 of the forecast rows: equal digests mean byte-identical forecasts."""
    payload = json.dumps([{**r, "week": str(r["week"])} for r in rows], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
