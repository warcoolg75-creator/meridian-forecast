"""LightGBM: one global model across all SKUs, direct multi-horizon.

One row per (SKU, anchor week t, horizon h); the target is week t + h. Every sales
feature is anchored at t and reads only weeks <= t (`_before`, which returns NaN for any
later week), so no lag is shorter than the horizon and nothing feeds back across it:
  - the last 4 weeks; rolling means over 4, 26 and 52 weeks and the 13-week maximum;
  - the same season last year: weeks t+h-53, t+h-52, t+h-51 and their 4-week mean
    (all <= t because h <= 26);
  - year-on-year growth: the last 13 weeks against the same 13 weeks a year before.
Calendar features describe the target week (known in advance): week of year, festival
windows, planned promotion days; and the same for the target week a year earlier, so the
model can learn "the festival was in this week last year, not this year".

Scale-free across SKUs: the target and the sales features are log(1 + units) minus the
log of the 13-week mean at t, so a 20-a-week SKU and a 5,000-a-week SKU share one model.
"""

from datetime import timedelta

import lightgbm as lgb
import numpy as np
import pandas as pd

from app.forecasting.calendar import FEATURE_NAMES, festival_offsets, moving_festivals
from app.forecasting.data import SalesHistory
from app.forecasting.models.base import HORIZON, SEASON, Forecaster, to_units

LEVEL_WEEKS = 13

FEATURES = (
    "horizon", "sku_code", "category_code", "log_level",
    "lag0", "lag1", "lag2", "lag3", "mean4", "mean26", "mean52", "max13",
    "ya_prev", "ya_same", "ya_next", "ya_mean4", "growth_yoy",
    "weeks_since_launch", "woy_sin", "woy_cos", "promo_days", "promo_days_ya",
    *(f"f_{n}" for n in FEATURE_NAMES), *(f"fya_{n}" for n in FEATURE_NAMES),
)
CATEGORICAL = ("sku_code", "category_code")


def feature_names(history: SalesHistory, offsets: bool) -> list[str]:
    """FEATURES, plus two per festival that moves by more than a week between years: the
    target week's days from it, and how much that differs from the year-ago week's days
    from last year's occurrence (a Diwali 19 days later than last year shows as -19)."""
    if not offsets:
        return list(FEATURES)
    moving = moving_festivals(history.calendar.festivals)
    return [*FEATURES, *(f"{kind}_{key}" for key in moving for kind in ("days_to", "moved"))]

PARAMS = {
    "objective": "l2", "learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 40,
    "feature_fraction": 0.8, "lambda_l2": 1.0, "deterministic": True, "force_row_wise": True,
    "num_threads": 1, "verbose": -1,
}
ROUNDS = 400


def _before(values: np.ndarray, index: np.ndarray, anchor: int) -> np.ndarray:
    """values[index], NaN where index < 0 or index > anchor: never a week after the anchor."""
    out = np.full(index.shape, np.nan)
    ok = (index >= 0) & (index <= anchor)
    out[ok] = values[index[ok]]
    return out


def build_rows(history: SalesHistory, horizon: int, train: bool, level_stat: str = "mean",
               offsets: bool = False) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Feature rows. train=True: every anchor whose target is inside the history, with
    targets; train=False: the last week as anchor, h = 1..horizon, for each SKU with
    LEVEL_WEEKS of data. Returns (X, y or empty, the SKU of each row)."""
    weeks = list(history.weeks)
    last = len(weeks) - 1
    future = history.future_weeks(horizon)
    calendar_weeks = sorted(set(weeks + future) | {w - timedelta(weeks=SEASON) for w in weeks + future})
    calendar_row = {w: i for i, w in enumerate(calendar_weeks)}
    festivals = history.calendar.festival_matrix(calendar_weeks)
    categories = sorted({s.category for s in history.skus})
    # Calendar-only (known in advance): days from each moving festival, for every week.
    moving = moving_festivals(history.calendar.festivals) if offsets else []
    days_to = np.column_stack([festival_offsets(history.calendar.festivals, k, calendar_weeks) for k in moving])         if moving else np.empty((len(calendar_weeks), 0))

    X_parts, y_parts, row_skus = [], [], []
    for sku in history.skus:
        s, first = sku.index, history.launch_index(sku.index)
        if last + 1 - first < LEVEL_WEEKS:
            continue
        units = history.units[s]
        log_units = np.log1p(units)
        series = pd.Series(units)
        mean = {w: series.rolling(w, min_periods=w).mean().to_numpy() for w in (4, LEVEL_WEEKS, 26, 52)}
        # The level every sales feature and the target are measured against: the 13-week mean,
        # or the median, which one shock week cannot drag down.
        typical = mean[LEVEL_WEEKS] if level_stat == "mean" else series.rolling(LEVEL_WEEKS, min_periods=LEVEL_WEEKS).median().to_numpy()
        log_mean13 = np.log1p(typical)
        max13 = series.rolling(13, min_periods=13).max().to_numpy()
        promo = history.calendar.promo_days(sku.sku, calendar_weeks)

        anchors = range(first + LEVEL_WEEKS - 1, last) if train else [last]
        for t in anchors:
            h = np.arange(1, horizon + 1)
            if train:
                h = h[t + h <= last]
            if h.size == 0:
                continue
            level = log_mean13[t]
            point = lambda k: _before(log_units, np.full(h.shape, t - k), t) - level  # noqa: E731
            ya = lambda k: _before(log_units, t + h - SEASON + k, t) - level  # noqa: E731
            ya_window = np.stack([_before(units, t + h - SEASON + k, t) for k in (-1, 0, 1, 2)])
            counted = (~np.isnan(ya_window)).sum(axis=0)
            ya_mean = np.divide(np.nansum(ya_window, axis=0), counted, out=np.full(h.shape, np.nan),
                                where=counted > 0)
            ya_mean4 = np.log1p(ya_mean) - level
            targets = [weeks[t] + timedelta(weeks=int(k)) for k in h]
            target_rows = [calendar_row[w] for w in targets]
            ya_rows = [calendar_row[w - timedelta(weeks=SEASON)] for w in targets]
            day_of_year = np.array([(w + timedelta(days=3)).timetuple().tm_yday for w in targets])
            growth = log_mean13[t] - log_mean13[t - SEASON] if t >= SEASON else np.nan
            columns = [
                h, np.full(h.shape, s), np.full(h.shape, categories.index(sku.category)), np.full(h.shape, level),
                point(0), point(1), point(2), point(3),
                np.log1p(np.full(h.shape, mean[4][t])) - level,
                np.log1p(np.full(h.shape, mean[26][t])) - level,
                np.log1p(np.full(h.shape, mean[52][t])) - level,
                np.log1p(np.full(h.shape, max13[t])) - level,
                ya(-1), ya(0), ya(1), ya_mean4, np.full(h.shape, growth),
                np.minimum(t + h - first, 156),
                np.sin(2 * np.pi * day_of_year / 365.25), np.cos(2 * np.pi * day_of_year / 365.25),
                promo[target_rows], promo[ya_rows],
            ]
            moved = days_to[target_rows] - days_to[ya_rows]
            extra = np.column_stack([v for k in range(len(moving)) for v in (days_to[target_rows, k], moved[:, k])])                 if moving else np.empty((h.size, 0))
            X_parts.append(np.column_stack([*columns, festivals[target_rows], festivals[ya_rows], extra]))
            if train:
                y_parts.append(log_units[t + h] - level)
            row_skus.extend([sku.sku] * h.size)
    X = np.vstack(X_parts) if X_parts else np.empty((0, len(FEATURES) + 2 * len(moving)))
    y = np.concatenate(y_parts) if y_parts else np.empty(0)
    return X, y, row_skus


class LightGBMGlobal(Forecaster):
    """See the module docstring. Needs 13 weeks of a SKU's own data for its level; its
    seasonality and festival response can come from the other SKUs in its category,
    which is how a short-history SKU (the Air Fryer) gets a forecast at all."""

    name = "lightgbm"
    min_weeks = LEVEL_WEEKS

    def __init__(self, level: str = "mean", offsets: bool = False) -> None:
        if level not in ("mean", "median"):
            raise ValueError(f"level must be mean or median, not {level!r}")
        self.level = level
        self.offsets = offsets

    def forecast(self, history: SalesHistory, horizon: int = HORIZON, seed: int = 42) -> dict[str, np.ndarray]:
        X, y, _ = build_rows(history, horizon, train=True, level_stat=self.level, offsets=self.offsets)
        keep = ~np.isnan(y)
        data = lgb.Dataset(X[keep], y[keep], feature_name=feature_names(history, self.offsets),
                           categorical_feature=list(CATEGORICAL), free_raw_data=False)
        booster = lgb.train({**PARAMS, "seed": seed}, data, num_boost_round=ROUNDS)
        X_next, _, skus = build_rows(history, horizon, train=False, level_stat=self.level, offsets=self.offsets)
        predicted = booster.predict(X_next)
        level = X_next[:, FEATURES.index("log_level")]
        values = to_units(predicted + level)
        out: dict[str, np.ndarray] = {}
        for sku, value in zip(skus, values, strict=True):
            out.setdefault(sku, []).append(value)  # type: ignore[arg-type]
        return {sku: np.array(v) for sku, v in out.items()}
