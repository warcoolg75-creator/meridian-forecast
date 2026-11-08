import logging

import numpy as np
import pandas as pd

from app.forecasting.calendar import FEATURE_NAMES
from app.forecasting.data import SalesHistory
from app.forecasting.models.base import HORIZON, SEASON, Forecaster, to_units

logging.getLogger("cmdstanpy").disabled = True
# ERROR, not WARNING: Prophet warns that yearly seasonality has "less than 730 days" at the
# origins with exactly 104 weeks (728 days), the deliberate minimum.
logging.getLogger("prophet").setLevel(logging.ERROR)

from prophet import Prophet  # noqa: E402  (after silencing cmdstanpy's per-fit log lines)

# Festival windows given to Prophet as regressors. Prophet's own `holidays` only act on
# a matching ds, and weekly ds (Mondays) almost never match a festival date, so the
# weekly window counts from calendar.py go in as extra regressors instead. A smaller set
# than LightGBM's: about 150 weekly points cannot support 64 regressors.
REGRESSORS = tuple(
    [f"{key}_{window}" for key in ("diwali", "dhanteras", "holi") for window in ("pre2", "pre1", "day", "post1")]
    + [f"{key}_{window}" for key in ("raksha_bandhan", "eid_al_fitr", "dussehra", "christmas", "durga_puja",
                                     "republic_day", "independence_day", "other_public")
       for window in ("pre1", "day")]
)
PROMO = "promo_days"


class ProphetModel(Forecaster):
    """Prophet on log(1 + units): linear trend, yearly seasonality (10 Fourier terms),
    festival windows and planned promotion days as regressors.

    Point forecasts only (uncertainty_samples=0): intervals come from backtest errors,
    like every model's, and Prophet's sampling would make runs non-deterministic. The
    MAP fit (L-BFGS from a fixed start) gives the same numbers every time.
    Needs two full years: with less, it cannot tell the yearly cycle from the trend.
    """

    name = "prophet"
    min_weeks = 2 * SEASON

    def forecast(self, history: SalesHistory, horizon: int = HORIZON, seed: int = 42) -> dict[str, np.ndarray]:
        weeks = list(history.weeks)
        future = history.future_weeks(horizon)
        festivals = history.calendar.festival_matrix(weeks + future)[:, [FEATURE_NAMES.index(n) for n in REGRESSORS]]
        out = {}
        for s in self.eligible(history):
            sku = history.skus[s].sku
            first = history.launch_index(s)
            promo = history.calendar.promo_days(sku, weeks + future)
            frame = pd.DataFrame(festivals, columns=list(REGRESSORS))
            frame[PROMO] = promo
            frame.insert(0, "ds", pd.to_datetime(weeks + future))
            train = frame.iloc[first:len(weeks)].copy()
            train["y"] = np.log1p(history.units[s, first:])
            used = [c for c in (*REGRESSORS, PROMO) if train[c].std() > 0]

            model = Prophet(growth="linear", yearly_seasonality=10, weekly_seasonality=False,
                            daily_seasonality=False, uncertainty_samples=0, changepoint_prior_scale=0.05)
            for column in used:
                model.add_regressor(column, prior_scale=0.5, standardize=False)
            model.fit(train[["ds", "y", *used]], algorithm="LBFGS")
            predicted = model.predict(frame.iloc[len(weeks):][["ds", *used]])
            out[sku] = to_units(predicted["yhat"].to_numpy())
        return out
