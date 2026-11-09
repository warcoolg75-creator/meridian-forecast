"""The v2 pieces: festival merges and offsets, Prophet's dip rule, LightGBM's level, the
Prophet + LightGBM ensemble as champion and the young-SKU interval table. Synthetic data
only: no database, no ground truth."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.forecasting import intervals
from app.forecasting.backtest import _pick_champions, _with_ensemble, champion_check
from app.forecasting.calendar import festival_offsets, merged_festivals, moving_festivals
from app.forecasting.models import ENSEMBLE, all_models
from app.forecasting.models.lightgbm_model import FEATURES, LEVEL_WEEKS, LightGBMGlobal, build_rows
from app.forecasting.models.prophet_model import ProphetModel, collapsed_weeks, regressor_groups
from app.forecasting.production import ensemble, forecast_rows
from tests.forecast_fixture import history

# Two festivals two days apart every year (like Dhanteras and Diwali), one that is close to
# them in only one year, and a fixed-date holiday.
FESTIVALS = (
    (date(2023, 11, 10), "dhanteras"), (date(2023, 11, 12), "diwali"),
    (date(2024, 10, 29), "dhanteras"), (date(2024, 10, 31), "diwali"),
    (date(2025, 10, 18), "dhanteras"), (date(2025, 10, 20), "diwali"),
    (date(2023, 11, 15), "dussehra"), (date(2024, 10, 12), "dussehra"), (date(2025, 10, 2), "dussehra"),
    (date(2023, 12, 25), "christmas"), (date(2024, 12, 25), "christmas"), (date(2025, 12, 25), "christmas"),
)


def test_festivals_within_a_week_in_every_year_are_merged_and_no_others():
    groups = merged_festivals(FESTIVALS, ["christmas", "dhanteras", "diwali", "dussehra"])
    assert ("dhanteras", "diwali") in groups
    assert ("dussehra",) in groups  # 3 days from Diwali in 2023 only: not merged
    assert ("christmas",) in groups


def test_a_festival_missing_from_one_year_is_not_merged():
    partial = tuple(f for f in FESTIVALS if f != (date(2025, 10, 18), "dhanteras"))
    assert ("dhanteras", "diwali") not in merged_festivals(partial, ["dhanteras", "diwali"])


def test_prophet_regressor_groups_follow_the_merge_switch():
    merged = regressor_groups(FESTIVALS, merge=True)
    assert any({"dhanteras", "diwali"} <= set(g) for g in merged)
    assert all(len(g) == 1 for g in regressor_groups(FESTIVALS, merge=False))


def test_moving_festivals_are_those_that_move_more_than_a_week():
    assert moving_festivals(FESTIVALS) == ["dhanteras", "diwali", "dussehra"]


def test_festival_offsets_count_days_from_the_weeks_thursday():
    weeks = [date(2025, 10, 13), date(2025, 10, 20), date(2025, 12, 1)]  # Mondays
    out = festival_offsets(FESTIVALS, "diwali", weeks, reach=42)
    assert out[0] == -4  # Thursday 16 Oct, four days before Diwali (20 Oct)
    assert out[1] == 3
    assert np.isnan(out[2])  # Thursday 4 Dec is 45 days after Diwali: beyond reach


def test_the_trailing_dip_rule_drops_a_seasonal_fall_and_the_year_ago_rule_keeps_it():
    # Two identical years: 30 high weeks, then a fall to a fifth, every year. And one shock
    # week in year two that last year did not have.
    year = np.r_[np.full(30, 1000.0), np.full(22, 200.0)]
    units = np.r_[year, year, year]
    units[52 + 10] = 100.0  # the shock
    trailing = collapsed_weeks(units, "trailing")
    both = collapsed_weeks(units, "trailing_and_year_ago")
    known = collapsed_weeks(units, "trailing_and_year_ago_if_known")
    assert trailing[52 + 30] and trailing[104 + 30]  # the seasonal fall, deleted
    assert not both[52 + 30] and not both[104 + 30]  # kept: last year fell too
    assert both[52 + 10] and known[52 + 10]  # the shock is still dropped
    assert known[30] and not both[30]  # year one: no last year, so trailing alone
    assert not collapsed_weeks(units, None).any()


def test_dip_rule_uses_only_past_weeks():
    rng = np.random.default_rng(1)
    units = rng.poisson(500, 160).astype(float)
    for rule in ("trailing", "trailing_and_year_ago", "trailing_and_year_ago_if_known"):
        full = collapsed_weeks(units, rule)
        for cut in (60, 110):
            np.testing.assert_array_equal(collapsed_weeks(units[:cut], rule), full[:cut])


@pytest.mark.parametrize("level_stat", ["mean", "median"])
def test_lightgbm_level_is_the_13_week_statistic_for_every_sku(level_stat):
    """A parameter once shadowed by the loop's own `level` made "mean" the median for every
    SKU after the first. Check every SKU's level feature."""
    h = history()
    X, _, skus = build_rows(h, 26, train=False, level_stat=level_stat)
    for s in h.skus:
        rows = [i for i, sku in enumerate(skus) if sku == s.sku]
        series = pd.Series(h.units[s.index]).rolling(LEVEL_WEEKS, min_periods=LEVEL_WEEKS)
        expected = (series.mean() if level_stat == "mean" else series.median()).to_numpy()[-1]
        np.testing.assert_allclose(X[rows, FEATURES.index("log_level")], np.log1p(expected))


def test_lightgbm_rejects_an_unknown_level():
    with pytest.raises(ValueError):
        LightGBMGlobal(level="trimmed")


def test_the_v2_models_are_the_adopted_configuration():
    models = {m.name: m for m in all_models()}
    assert models["lightgbm"].level == "median" and models["lightgbm"].offsets is False
    assert isinstance(models["prophet"], ProphetModel)
    assert models["prophet"].merge_festivals is True
    assert models["prophet"].drop_dips == "trailing_and_year_ago_if_known"


def _pairs() -> pd.DataFrame:
    rows = []
    for sku, actual in (("A", 100.0), ("B", 50.0)):
        for target in (date(2026, 1, 5), date(2026, 5, 4)):
            for model, p50 in (("seasonal_naive", actual * 1.5), ("ets", actual * 1.2),
                               ("prophet", actual * 0.9), ("lightgbm", actual * 1.3)):
                rows.append((model, sku, target - timedelta(weeks=1), 1, target, actual, p50, 10.0))
    rows.append(("lightgbm", "NEW", date(2026, 1, 5), 1, date(2026, 1, 12), 40.0, 44.0, np.nan))
    pairs = pd.DataFrame(rows, columns=["model", "sku", "origin", "horizon", "target", "actual", "p50", "scale"])
    pairs["window"] = "selection"
    return pairs


def test_the_ensemble_is_the_mean_of_prophet_and_lightgbm_or_lightgbm_alone():
    pairs = _with_ensemble(_pairs())
    mean = pairs[pairs["model"] == ENSEMBLE].set_index(["sku", "target"])["p50"]
    assert mean[("A", date(2026, 1, 5))] == pytest.approx((90 + 130) / 2)
    assert mean[("NEW", date(2026, 1, 12))] == 44.0  # Prophet has no forecast for it


def test_the_champion_is_the_ensemble_when_it_ran_and_v1s_rule_otherwise():
    h = history()
    with_ensemble = _with_ensemble(_pairs().replace({"sku": {"A": "FX-FOOD", "B": "FX-FAN"}}))
    assert set(_pick_champions(with_ensemble, h).values()) == {ENSEMBLE}
    # Without the ensemble: lowest WAPE, calendar-aware models only for a festive SKU (FX-FOOD
    # is Packaged Foods; Prophet wins there anyway; FX-FAN is not festive).
    plain = _pairs().replace({"sku": {"A": "FX-FOOD", "B": "FX-FAN"}})
    plain = plain[plain["model"] != "prophet"]
    picked = _pick_champions(plain, h)
    assert picked["FX-FAN"] == "ets"  # 20% error, the lowest
    assert picked["FX-FOOD"] == "lightgbm"  # ETS is lower, but not calendar-aware


def test_the_champion_check_compares_three_strategies_on_the_later_weeks():
    h = history()
    pairs = _with_ensemble(_pairs().replace({"sku": {"A": "FX-FOOD", "B": "FX-FAN"}}))
    check = champion_check(pairs, h)
    assert set(check) >= {"v1", "margin", "mean", "baseline_pooled_wape"}
    assert check["mean"]["pooled_wape"] == pytest.approx(0.1)  # (0.9 + 1.3) / 2 = 1.1x actual


def test_short_history_skus_get_the_young_table_when_there_is_one():
    table = {"lightgbm": {}, intervals.YOUNG: {}}
    assert intervals.table_key(table, "lightgbm", 30) == intervals.YOUNG
    assert intervals.table_key(table, "lightgbm", 52) == "lightgbm"
    assert intervals.table_key({"lightgbm": {}}, "lightgbm", 30) == "lightgbm"


def test_production_ensemble_and_young_intervals():
    h = history()
    parts = {"prophet": {"FX-FOOD": np.full(26, 100.0)},
             "lightgbm": {"FX-FOOD": np.full(26, 140.0), "FX-NEW": np.full(26, 30.0)}}
    out = ensemble(parts)
    np.testing.assert_array_equal(out["FX-FOOD"], np.full(26, 120.0))
    np.testing.assert_array_equal(out["FX-NEW"], np.full(26, 30.0))
    narrow = [-0.1, -0.05, 0.05, 0.1]
    wide = [-0.8, -0.5, 0.5, 0.8]
    quantiles = {ENSEMBLE: {g: narrow for g in ("1-4", "5-13", "14-26")},
                 intervals.YOUNG: {g: wide for g in ("1-4", "5-13", "14-26")}}
    rows = forecast_rows(h, {"FX-FOOD": ENSEMBLE, "FX-NEW": ENSEMBLE}, quantiles, 42,
                         by_model={**parts, ENSEMBLE: out})
    first = {r["sku"]: r for r in rows if r["horizon"] == 1}
    assert first["FX-FOOD"]["p50"] == 120
    # FX-NEW has 20 weeks of data: the young table's wider interval.
    assert first["FX-NEW"]["hi80"] == int(np.rint(31 * np.exp(0.5) - 1))
    assert first["FX-FOOD"]["hi80"] == int(np.rint(121 * np.exp(0.05) - 1))


def test_a_short_history_sku_stores_the_model_actually_used():
    """FX-NEW (20 weeks, short history) has a LightGBM forecast only: its rows say lightgbm,
    not the ensemble, while its values and young-table interval are unchanged."""
    h = history()
    parts = {"prophet": {"FX-FOOD": np.full(26, 100.0)},
             "lightgbm": {"FX-FOOD": np.full(26, 140.0), "FX-NEW": np.full(26, 30.0)}}
    wide = [-0.8, -0.5, 0.5, 0.8]
    quantiles = {ENSEMBLE: {g: [-0.1, -0.05, 0.05, 0.1] for g in ("1-4", "5-13", "14-26")},
                 intervals.YOUNG: {g: wide for g in ("1-4", "5-13", "14-26")}}
    rows = forecast_rows(h, {"FX-FOOD": ENSEMBLE, "FX-NEW": ENSEMBLE}, quantiles, 42,
                         by_model={**parts, ENSEMBLE: ensemble(parts)})
    models = {r["sku"]: {x["model"] for x in rows if x["sku"] == r["sku"]} for r in rows}
    assert models == {"FX-FOOD": {ENSEMBLE}, "FX-NEW": {"lightgbm"}}
    new = next(r for r in rows if r["sku"] == "FX-NEW" and r["horizon"] == 1)
    assert new["p50"] == 30 and new["hi80"] == int(np.rint(31 * np.exp(0.5) - 1))  # values as before
    with pytest.raises(ValueError, match="parts are needed"):
        forecast_rows(h, {"FX-NEW": ENSEMBLE}, quantiles, 42, by_model={ENSEMBLE: ensemble(parts)})
