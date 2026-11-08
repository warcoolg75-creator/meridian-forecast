"""The ground truth, for scoring only. The ONLY forecasting module that reads it.

Possible because the data is synthetic: app.seed.ground_truth computes the expected
units behind every sale (expected_cell_demand), so:
  * the oracle forecast is that expectation; its error against actuals is pure Poisson
    sampling noise, the floor no model can beat;
  * shock weeks are known exactly, so every score can be computed with and without them;
  * after the data ends, the same function with the window extended (the ground truth
    lists holidays up to 182 days past the end) gives expected demand for the production
    forecast's weeks. Asked for weeks past that, it refuses rather than approximating.

No model or feature may import this module or the ground truth:
tests/test_forecast_leakage.py checks the imports.
"""

import copy
from datetime import date, timedelta
from functools import lru_cache

import numpy as np

from app.seed.ground_truth import CALENDAR_HORIZON_DAYS, expected_cell_demand, load_ground_truth


@lru_cache(maxsize=1)
def _ground_truth() -> dict:
    return load_ground_truth()


def window_end() -> date:
    return date.fromisoformat(_ground_truth()["window"]["end"])


def _weekly(gt: dict, skus: list[str], weeks: list[date]) -> dict[str, np.ndarray]:
    start = date.fromisoformat(gt["window"]["start"])
    out = {}
    for sku in skus:
        _, mu = expected_cell_demand(gt, sku)
        daily = mu.sum(axis=1)
        values = np.zeros(len(weeks))
        for i, monday in enumerate(weeks):
            first = (monday - start).days
            if first < 0 or first + 7 > len(daily):
                raise ValueError(f"No expected demand for the week of {monday}")
            values[i] = daily[first:first + 7].sum()
        out[sku] = values
    return out


def expected_weekly(skus: list[str], weeks: list[date]) -> dict[str, np.ndarray]:
    """Expected units per SKU per (Monday) week inside the data window, as generated:
    with the recorded promotions and supply shocks."""
    return _weekly(_ground_truth(), skus, weeks)


def expected_weekly_planned(skus: list[str], weeks: list[date]) -> dict[str, np.ndarray]:
    """Expected units for weeks that may run past the data end, with no promotions and no
    supply shocks: the assumptions of the production forecast (no promotion is recorded
    after the data end, and shocks are never forecast)."""
    gt = copy.deepcopy(_ground_truth())
    end = date.fromisoformat(gt["window"]["end"])
    limit = end + timedelta(days=CALENDAR_HORIZON_DAYS)
    last_day = max(weeks) + timedelta(days=6)
    if last_day > limit:
        raise ValueError(f"The ground truth lists holidays only to {limit}; cannot give expected demand "
                         f"to {last_day} without approximating")
    gt["window"]["days"] += max(0, (last_day - end).days)
    for product in gt["products"].values():
        product["promotions"] = []
        product["shocks"] = []
    return _weekly(gt, skus, weeks)


def shock_weeks() -> set[tuple[str, date]]:
    """(SKU, Monday) for every week holding at least one day of that SKU's supply shock."""
    weeks = set()
    for sku, product in _ground_truth()["products"].items():
        for shock in product["shocks"]:
            day, last = date.fromisoformat(shock["start"]), date.fromisoformat(shock["end"])
            while day <= last:
                weeks.add((sku, day - timedelta(days=day.weekday())))
                day += timedelta(days=1)
    return weeks
