import warnings

import numpy as np
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.forecasting.data import SalesHistory
from app.forecasting.models.base import HORIZON, SEASON, Forecaster, to_units


class ETS(Forecaster):
    """Holt-Winters on log(1 + units): additive damped trend, additive seasonality of
    period 52, which is multiplicative in units.

    Fitted on the log so that the festive spikes of a 20-units-a-week SKU do not break
    it: a multiplicative fit on raw units did not converge on the Gift Box. It has no
    calendar, so a festival that moves (Diwali) stays where it was last year.
    Needs two full seasons to initialise the seasonal states.
    """

    name = "ets"
    min_weeks = 2 * SEASON

    def __init__(self) -> None:
        self.convergence_warnings: list[str] = []

    def forecast(self, history: SalesHistory, horizon: int = HORIZON, seed: int = 42) -> dict[str, np.ndarray]:
        out = {}
        for s in self.eligible(history):
            series = history.units[s, history.launch_index(s):]
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always", ConvergenceWarning)
                fit = ExponentialSmoothing(
                    np.log1p(series), trend="add", damped_trend=True, seasonal="add",
                    seasonal_periods=SEASON, initialization_method="estimated",
                ).fit(optimized=True)
            if any(issubclass(w.category, ConvergenceWarning) for w in caught):
                self.convergence_warnings.append(f"{history.skus[s].sku} at {history.weeks[-1]}")
            out[history.skus[s].sku] = to_units(fit.forecast(horizon))
        return out
