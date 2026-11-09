"""Same seed, same data, same library versions: byte-identical forecasts."""

from app.forecasting.intervals import YOUNG, fit_quantiles
from app.forecasting.production import digest, forecast_rows
from app.forecasting.models import ENSEMBLE, all_models
from tests.forecast_fixture import history

import numpy as np
import pandas as pd

# The v2 champion (Prophet + LightGBM mean: FX-NEW, too young for Prophet, gets LightGBM
# alone and the young interval table) beside a v1-style single-model champion, so Prophet,
# LightGBM and ETS are all exercised.
CHAMPIONS = {"FX-FOOD": ENSEMBLE, "FX-FAN": "ets", "FX-NEW": ENSEMBLE}


def _quantiles() -> dict:
    rows = [{"model": m, "horizon": h, "actual": 100.0 + k * (3 if m == YOUNG else 1), "p50": 100.0}
            for m in ("seasonal_naive", "ets", "prophet", "lightgbm", ENSEMBLE, YOUNG)
            for h in range(1, 27) for k in range(-10, 11)]
    return fit_quantiles(pd.DataFrame(rows))


def test_the_production_forecast_is_byte_identical_across_runs():
    h, quantiles = history(), _quantiles()
    first = forecast_rows(h, CHAMPIONS, quantiles, seed=42)
    second = forecast_rows(h, CHAMPIONS, quantiles, seed=42)
    assert first == second
    assert digest(first) == digest(second)
    # Each row names the model actually used: FX-NEW's ensemble is LightGBM alone.
    assert {(r["sku"], r["model"]) for r in first} == {("FX-FOOD", ENSEMBLE), ("FX-FAN", "ets"),
                                                       ("FX-NEW", "lightgbm")}
    assert len(first) == 3 * 26


def test_every_model_repeats_itself_exactly():
    h = history()
    for first, second in zip(all_models(), all_models(), strict=True):
        a, b = first.forecast(h, seed=42), second.forecast(h, seed=42)
        assert a.keys() == b.keys(), first.name
        for sku in a:
            assert np.array_equal(a[sku], b[sku], equal_nan=True), f"{first.name} {sku}"
            assert a[sku].tobytes() == b[sku].tobytes(), f"{first.name} {sku}"
