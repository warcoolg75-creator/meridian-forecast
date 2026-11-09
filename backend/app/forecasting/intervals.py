"""80% and 95% intervals from each model's own backtest errors, the same for every model.

For a forecast f of actual y the error is r = log((y + 1) / (f + 1)), multiplicative and
defined on zero weeks. Its empirical quantiles per model and horizon group (1-4, 5-13,
14-26 weeks), pooled across SKUs, give the interval (f + 1) * exp(q) - 1, floored at 0.

Why pooled across SKUs: per-SKU quantiles were tried first and under-covered. A SKU's
champion is picked because its errors on the selection window were small, so those same
errors understate what comes next (the winner's curse). Calibrated on selection-window
targets before 2026-04-06 and checked on 2026-04-06..07-05, inside the selection window
and before the held-out window was looked at again, champions' 80% intervals covered
64.8% per SKU and 81.0% pooled (docs/backtest-report.md has the comparison).

Calibration is honest: the held-out window's intervals use quantiles from the selection
window only; the production run uses every backtest error. The p50 is never moved into
its interval: a biased model can sit outside its own 80% interval, and the report says
how often.
"""

import numpy as np
import pandas as pd

GROUPS = ((1, 4), (5, 13), (14, 26))
QUANTILES = (0.025, 0.10, 0.90, 0.975)
# SKUs with fewer weeks of data than this get the "young" table: errors of long-history SKUs
# forecast as if they were young (a simulation in the backtest), about twice as wide.
SHORT_HISTORY_WEEKS = 52
YOUNG = "young"


def group_of(horizon: int) -> str:
    for first, last in GROUPS:
        if first <= horizon <= last:
            return f"{first}-{last}"
    raise ValueError(f"horizon {horizon} outside 1-26")


def log_errors(actual: np.ndarray, forecast: np.ndarray) -> np.ndarray:
    return np.log1p(actual) - np.log1p(forecast)


def fit_quantiles(pairs: pd.DataFrame) -> dict[str, dict[str, list[float]]]:
    """{model: {group: [q2.5, q10, q90, q97.5]}} from rows with columns model, horizon,
    actual, p50."""
    frame = pairs.assign(error=log_errors(pairs["actual"].to_numpy(), pairs["p50"].to_numpy()),
                         group=pairs["horizon"].map(group_of))
    table: dict[str, dict[str, list[float]]] = {}
    for (model, group), rows in frame.groupby(["model", "group"], sort=True):
        quantiles = np.quantile(rows["error"].to_numpy(), QUANTILES)
        table.setdefault(str(model), {})[str(group)] = [round(float(q), 6) for q in quantiles]
    return table


def table_key(table: dict, model: str, weeks_of_data: int) -> str:
    """The young table for a short-history SKU (when the backtest made one), else the model's."""
    return YOUNG if weeks_of_data < SHORT_HISTORY_WEEKS and YOUNG in table else model


def bounds(table: dict, model: str, horizons: np.ndarray, p50: np.ndarray) -> np.ndarray:
    """(n, 4): lo95, lo80, hi80, hi95 for each forecast."""
    q = np.array([table[model][group_of(int(h))] for h in horizons])
    return np.clip((np.asarray(p50)[:, None] + 1) * np.exp(q) - 1, 0, None)
