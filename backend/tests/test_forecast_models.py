"""The forecasting pieces on a synthetic history: models, calendar, metrics, intervals,
and the backtest driver (with the oracle stubbed: the fixture SKUs have no ground truth)."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.forecasting import backtest as backtest_module
from app.forecasting.backtest import CHAMPION, ORACLE, origin_indices, run_backtest
from app.forecasting.calendar import FEATURE_NAMES, Calendar, festival_key
from app.forecasting.intervals import bounds, fit_quantiles, group_of
from app.forecasting.metrics import bias, coverage, mase, skill, wape
from app.forecasting.models import all_models
from app.forecasting.models.ets import ETS
from app.forecasting.models.seasonal_naive import SeasonalNaive
from tests.forecast_fixture import history


def test_seasonal_naive_repeats_the_same_week_last_year():
    h = history()
    out = SeasonalNaive().forecast(h, horizon=26)
    last = h.last
    np.testing.assert_array_equal(out["FX-FOOD"], h.units[0, last + 1 - 52: last + 27 - 52])
    assert "FX-NEW" not in out  # 20 weeks old: no year-earlier week exists


def test_short_history_is_excluded_rather_than_fitted_badly():
    h = history()
    covered = {m.name: set(m.forecast(h)) for m in all_models()}
    assert covered["seasonal_naive"] == covered["ets"] == covered["prophet"] == {"FX-FOOD", "FX-FAN"}
    assert covered["lightgbm"] == {"FX-FOOD", "FX-FAN", "FX-NEW"}
    # ETS needs two full seasons: with 103 weeks it leaves the SKU out.
    assert ETS().forecast(h.until(102)) == {}


def test_forecasts_are_non_negative_and_twenty_six_weeks_long():
    for model in all_models():
        for sku, values in model.forecast(history()).items():
            assert values.shape == (26,), (model.name, sku)
            assert np.nanmin(values) >= 0, (model.name, sku)


def test_festival_windows_count_days_per_week():
    diwali = date(2026, 11, 8)  # a Sunday
    weeks = [date(2026, 10, 19) + timedelta(weeks=k) for k in range(5)]
    m = Calendar(((diwali, "diwali"),)).festival_matrix(weeks)
    column = {name: i for i, name in enumerate(FEATURE_NAMES)}
    # pre2 = 14..8 days before: 25-31 Oct (w/c 19 Oct holds 25 Oct, w/c 26 Oct the other six).
    assert m[:, column["diwali_pre2"]].tolist() == [1, 6, 0, 0, 0]
    assert m[:, column["diwali_pre1"]].tolist() == [0, 1, 6, 0, 0]
    assert m[:, column["diwali_day"]].tolist() == [0, 0, 1, 0, 0]
    assert m[:, column["diwali_post1"]].tolist() == [0, 0, 0, 7, 0]
    assert festival_key("Id-ul-Fitr (estimated)", True) == "eid_al_fitr"
    assert festival_key("Muharram", True) == "other_public"
    assert festival_key("Some fair", False) is None


def test_planned_promotions_count_days_per_week():
    cal = Calendar((), {"A": ((date(2026, 3, 5), date(2026, 3, 11)),)})
    weeks = [date(2026, 3, 2), date(2026, 3, 9), date(2026, 3, 16)]
    assert cal.promo_days("A", weeks).tolist() == [4, 3, 0]
    assert cal.promo_days("B", weeks).tolist() == [0, 0, 0]


def test_metrics():
    y, f = np.array([10.0, 0.0, 30.0]), np.array([12.0, 3.0, 24.0])
    assert wape(y, f) == pytest.approx(11 / 40)
    assert bias(y, f) == pytest.approx(-1 / 40)
    assert mase(y, f, np.array([2.0, 2.0, 0.0])) == pytest.approx(np.mean([1.0, 1.5]))
    assert coverage(y, f - 3, f + 3) == pytest.approx(2 / 3)
    assert skill(0.17, 0.34) == pytest.approx(0.5)
    assert wape(np.zeros(3), f) is None and skill(0.1, None) is None


def test_intervals_from_errors_cover_their_nominal_share():
    rng = np.random.default_rng(3)
    p50 = rng.uniform(50, 500, 4000)
    actual = rng.poisson(p50).astype(float)
    frame = pd.DataFrame({"model": "m", "horizon": rng.integers(1, 27, 4000), "actual": actual, "p50": p50})
    table = fit_quantiles(frame.iloc[:2000])
    test = frame.iloc[2000:]
    b = bounds(table, "m", test["horizon"].to_numpy(), test["p50"].to_numpy())
    assert coverage(test["actual"].to_numpy(), b[:, 1], b[:, 2]) == pytest.approx(0.80, abs=0.03)
    assert coverage(test["actual"].to_numpy(), b[:, 0], b[:, 3]) == pytest.approx(0.95, abs=0.02)
    assert group_of(1) == "1-4" and group_of(13) == "5-13" and group_of(26) == "14-26"


def test_the_backtest_scores_every_window_and_picks_a_champion_per_sku(monkeypatch):
    h = history()

    def expected(skus, weeks):  # stub: the fixture has no ground truth
        return {s: np.full(len(weeks), 100.0) for s in skus}

    monkeypatch.setattr(backtest_module.oracle, "expected_weekly", expected)
    monkeypatch.setattr(backtest_module.oracle, "shock_weeks", lambda: {("FX-FOOD", h.weeks[-5])})
    result = run_backtest(h, models=[SeasonalNaive(), ETS()])

    origins = origin_indices(h)
    assert len(origins) == 13 and origins[-1] == h.last - 3 and origins[0] == h.last - 51
    assert result.held_out_start == h.weeks[h.last - 12]
    assert set(result.champions) == {"FX-FOOD", "FX-FAN"} and set(result.champions.values()) <= {"seasonal_naive", "ets"}
    assert result.headline_skus == ["FX-FAN", "FX-FOOD"]
    rows = pd.DataFrame(result.metrics)
    assert set(rows["window"]) == {"selection", "held_out"}  # the fixture has no Sep-Nov 2025 weeks
    assert set(rows["model"]) == {"seasonal_naive", "ets", CHAMPION, ORACLE}
    assert rows.loc[rows["window"] == "selection", "coverage_80"].isna().all()
    held = rows[(rows["window"] == "held_out") & (rows["model"] == CHAMPION)]
    assert held["coverage_80"].between(0, 1).all()
    # Excluding the one shock week drops exactly the forecasts made for it.
    pooled = rows[(rows["model"] == "seasonal_naive") & rows["sku"].isna() & rows["horizon"].isna()
                  & (rows["window"] == "held_out")].set_index("shocks")["n_weeks"]
    assert pooled["included"] - pooled["excluded"] == len({o for o in origins if h.weeks[o] <= h.weeks[-5]
                                                           and h.weeks[-5] <= h.weeks[o] + timedelta(weeks=25)})
