import logging

import numpy as np
import pandas as pd

from app.forecasting.calendar import FEATURE_NAMES, WINDOWS, merged_festivals
from app.forecasting.data import SalesHistory
from app.forecasting.models.base import HORIZON, SEASON, Forecaster, to_units

from prophet import Prophet

logging.getLogger("cmdstanpy").disabled = True
# ERROR, not WARNING: Prophet warns that yearly seasonality has "less than 730 days" at the
# origins with exactly 104 weeks (728 days), the deliberate minimum. Set after the import:
# importing Prophet resets its logger's level.
logging.getLogger("prophet").setLevel(logging.ERROR)

# Festival windows given to Prophet as regressors. Prophet's own `holidays` only act on
# a matching ds, and weekly ds (Mondays) almost never match a festival date, so the
# weekly window counts from calendar.py go in as extra regressors instead. A smaller set
# than LightGBM's: about 150 weekly points cannot support 64 regressors.
REGRESSOR_WINDOWS = {
    **{key: ("pre2", "pre1", "day", "post1") for key in ("diwali", "dhanteras", "holi")},
    **{key: ("pre1", "day") for key in ("raksha_bandhan", "eid_al_fitr", "dussehra", "christmas", "durga_puja",
                                         "republic_day", "independence_day", "other_public")},
}
REGRESSORS = tuple(f"{key}_{window}" for key, windows in REGRESSOR_WINDOWS.items() for window in windows)


def regressor_groups(festivals: tuple, merge: bool) -> list[tuple[str, ...]]:
    """Prophet's festival regressors, one per group: festivals within a week of each other in
    every year of the calendar (Dhanteras and Diwali; Dussehra and Durga Puja on the pinned
    data) are one regressor, their window days summed."""
    keys = list(REGRESSOR_WINDOWS)
    return merged_festivals(festivals, keys) if merge else [(k,) for k in keys]


def regressor_matrix(history: SalesHistory, weeks: list, merge: bool) -> tuple[np.ndarray, list[str]]:
    full = history.calendar.festival_matrix(weeks)
    columns, names = [], []
    for group in regressor_groups(history.calendar.festivals, merge):
        windows = [w for w, _, _ in WINDOWS if any(w in REGRESSOR_WINDOWS[k] for k in group)]
        for window in windows:
            columns.append(sum(full[:, FEATURE_NAMES.index(f"{k}_{window}")] for k in group))
            names.append(f"{'+'.join(group)}_{window}")
    return np.column_stack(columns), names
PROMO = "promo_days"
# A collapsed week (a supply shock) says nothing about demand, so it can be left out of the
# fit: under DIP_SHARE of the median of the 13 weeks before it ("trailing"), and with
# "trailing_and_year_ago" also under DIP_SHARE of the same weeks last year (weeks t-53..t-51),
# so a seasonal fall (coolers after summer, gifts after Diwali) is not mistaken for one.
DIP_SHARE = 0.5
DIP_WEEKS = 13
DIP_RULES = (None, "trailing", "trailing_and_year_ago", "trailing_and_year_ago_if_known")


def collapsed_weeks(units: np.ndarray, rule: str | None) -> np.ndarray:
    """Weeks the dip rule leaves out of the fit. Uses each week's own past only."""
    s = pd.Series(units)
    if rule is None:
        return np.zeros(len(units), dtype=bool)
    out = units < DIP_SHARE * s.shift(1).rolling(DIP_WEEKS, min_periods=DIP_WEEKS).median().to_numpy()
    if rule in ("trailing_and_year_ago", "trailing_and_year_ago_if_known"):
        year_ago = pd.concat([s.shift(SEASON - 1), s.shift(SEASON), s.shift(SEASON + 1)], axis=1)
        reference = year_ago.median(axis=1, skipna=False).to_numpy()
        below = units < DIP_SHARE * reference
        if rule == "trailing_and_year_ago_if_known":  # no year-ago weeks yet: the trailing check alone
            below |= np.isnan(reference)
        out &= below
    return out


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

    def __init__(self, drop_dips: str | None = None, merge_festivals: bool = False) -> None:
        if drop_dips not in DIP_RULES:
            raise ValueError(f"drop_dips must be one of {DIP_RULES}")
        self.drop_dips = drop_dips
        self.merge_festivals = merge_festivals

    def forecast(self, history: SalesHistory, horizon: int = HORIZON, seed: int = 42) -> dict[str, np.ndarray]:
        weeks = list(history.weeks)
        future = history.future_weeks(horizon)
        festivals, names = regressor_matrix(history, weeks + future, self.merge_festivals)
        out = {}
        for s in self.eligible(history):
            sku = history.skus[s].sku
            first = history.launch_index(s)
            promo = history.calendar.promo_days(sku, weeks + future)
            frame = pd.DataFrame(festivals, columns=names)
            frame[PROMO] = promo
            frame.insert(0, "ds", pd.to_datetime(weeks + future))
            train = frame.iloc[first:len(weeks)].copy()
            units = history.units[s, first:]
            train["y"] = np.log1p(units)
            train = train[~collapsed_weeks(units, self.drop_dips)]
            used = [c for c in (*names, PROMO) if train[c].std() > 0]

            model = Prophet(growth="linear", yearly_seasonality=10, weekly_seasonality=False,
                            daily_seasonality=False, uncertainty_samples=0, changepoint_prior_scale=0.05)
            for column in used:
                model.add_regressor(column, prior_scale=0.5, standardize=False)
            model.fit(train[["ds", "y", *used]], algorithm="LBFGS")
            predicted = model.predict(frame.iloc[len(weeks):][["ds", *used]])
            out[sku] = to_units(predicted["yhat"].to_numpy())
        return out
