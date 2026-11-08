import numpy as np

from app.forecasting.data import SalesHistory
from app.forecasting.models.base import HORIZON, SEASON, Forecaster


class SeasonalNaive(Forecaster):
    """The same week last year: week t + h gets the actual of week t + h - 52.

    The baseline every model is judged against. With h <= 26 that week is always in the
    past. A week whose year-earlier week is before the SKU's launch has no forecast.
    """

    name = "seasonal_naive"
    min_weeks = SEASON + 1

    def forecast(self, history: SalesHistory, horizon: int = HORIZON, seed: int = 42) -> dict[str, np.ndarray]:
        last = history.last
        out = {}
        for s in self.eligible(history):
            values = np.full(horizon, np.nan)
            for h in range(1, horizon + 1):
                source = last + h - SEASON
                if 0 <= source <= last:
                    values[h - 1] = history.units[s, source]
            if not np.all(np.isnan(values)):
                out[history.skus[s].sku] = values
        return out
