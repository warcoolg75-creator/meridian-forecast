"""Forecast scores. Sums are over SKU-weeks; everything is in units.

WAPE, not MAPE: MAPE divides by each week's actual and breaks on zero weeks (the Gift Box
has them). WAPE pools the absolute errors and divides once, so it is volume-weighted: a
5,000-a-week SKU outweighs a 20-a-week one, which is why the report adds per-SKU skill.
"""

import numpy as np


def wape(actual: np.ndarray, forecast: np.ndarray) -> float | None:
    total = float(np.sum(actual))
    return float(np.sum(np.abs(actual - forecast))) / total if total > 0 else None


def bias(actual: np.ndarray, forecast: np.ndarray) -> float | None:
    """(forecast - actual) / actual, summed: negative means forecasts were too low."""
    total = float(np.sum(actual))
    return float(np.sum(forecast - actual)) / total if total > 0 else None


def mase(actual: np.ndarray, forecast: np.ndarray, scale: np.ndarray) -> float | None:
    """Mean absolute error over the in-sample seasonal-naive MAE (lag 52) of the history
    each forecast was trained on: below 1 beats last year's actuals on the training data."""
    ok = scale > 0
    if not np.any(ok):
        return None
    return float(np.mean(np.abs(actual[ok] - forecast[ok]) / scale[ok]))


def coverage(actual: np.ndarray, low: np.ndarray, high: np.ndarray) -> float | None:
    if actual.size == 0:
        return None
    return float(np.mean((actual >= low) & (actual <= high)))


def skill(model_wape: float | None, baseline_wape: float | None) -> float | None:
    """1 - WAPE / baseline WAPE: 0.15 is 15% lower error than the baseline."""
    if model_wape is None or not baseline_wape:
        return None
    return 1 - model_wape / baseline_wape
