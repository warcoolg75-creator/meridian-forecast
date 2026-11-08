from abc import ABC, abstractmethod

import numpy as np

from app.forecasting.data import SalesHistory

HORIZON = 26  # weeks ahead, the planning horizon
SEASON = 52  # weeks in a year: the seasonal lag


class Forecaster(ABC):
    """Fit on a history (the weeks up to an origin, and the calendar), predict a horizon.

    `forecast` returns each SKU's p50 (median) for weeks 1..horizon after the history's
    last week, as floats. A SKU the model cannot forecast is absent, never fitted badly;
    a single week it cannot forecast is NaN. Intervals are added later from backtest
    errors (app.forecasting.intervals), the same way for every model.
    """

    name: str
    # Weeks of data a SKU needs at the origin (its launch week counts).
    min_weeks: int

    def eligible(self, history: SalesHistory) -> list[int]:
        return [s.index for s in history.skus if history.weeks_since_launch(s.index) >= self.min_weeks]

    @abstractmethod
    def forecast(self, history: SalesHistory, horizon: int = HORIZON, seed: int = 42) -> dict[str, np.ndarray]:
        ...


def to_units(log_values: np.ndarray) -> np.ndarray:
    """Back from log(1 + units): a median, not a mean (see the report's bias section)."""
    return np.clip(np.expm1(log_values), 0, None)
