from app.forecasting.models.base import HORIZON, SEASON, Forecaster
from app.forecasting.models.ets import ETS
from app.forecasting.models.lightgbm_model import LightGBMGlobal
from app.forecasting.models.prophet_model import ProphetModel
from app.forecasting.models.seasonal_naive import SeasonalNaive

VERSION = "v2"
BASELINE = SeasonalNaive.name
MODEL_NAMES = (SeasonalNaive.name, ETS.name, ProphetModel.name, LightGBMGlobal.name)
# The champion of every SKU since v2: the mean of the two calendar-aware models (the
# Air Fryer, which Prophet cannot fit, gets LightGBM alone). Picked over per-SKU champions
# on a split inside the selection window (CLAUDE.md, "Forecasting").
ENSEMBLE = "prophet_lightgbm"
ENSEMBLE_PARTS = (ProphetModel.name, LightGBMGlobal.name)
CALENDAR_AWARE = (ProphetModel.name, LightGBMGlobal.name, ENSEMBLE)

# v2 settings, each decided on the selection window only:
#   Prophet: festivals within a week of each other every year are one regressor; a week that
#     collapsed below half its trailing 13-week median and below half the same weeks last year
#     (when there is a last year) is left out of the fit.
#   LightGBM: the recent level is the 13-week median, which one shock week cannot drag down.
#     The festival-offset features were tried and not adopted: they worsened pooled WAPE.
PROPHET_V2 = {"merge_festivals": True, "drop_dips": "trailing_and_year_ago_if_known"}
LIGHTGBM_V2 = {"level": "median", "offsets": False}


def all_models() -> list[Forecaster]:
    """Fresh v2 instances, in a fixed order."""
    return [SeasonalNaive(), ETS(), ProphetModel(**PROPHET_V2), LightGBMGlobal(**LIGHTGBM_V2)]


def model_by_name(name: str) -> Forecaster:
    return {m.name: m for m in all_models()}[name]


__all__ = ["BASELINE", "CALENDAR_AWARE", "ENSEMBLE", "ENSEMBLE_PARTS", "HORIZON", "MODEL_NAMES", "SEASON",
           "VERSION", "Forecaster", "all_models", "model_by_name"]
