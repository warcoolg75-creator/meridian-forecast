from app.forecasting.models.base import HORIZON, SEASON, Forecaster
from app.forecasting.models.ets import ETS
from app.forecasting.models.lightgbm_model import LightGBMGlobal
from app.forecasting.models.prophet_model import ProphetModel
from app.forecasting.models.seasonal_naive import SeasonalNaive

BASELINE = SeasonalNaive.name
MODEL_NAMES = (SeasonalNaive.name, ETS.name, ProphetModel.name, LightGBMGlobal.name)


def all_models() -> list[Forecaster]:
    """Fresh instances, in a fixed order."""
    return [SeasonalNaive(), ETS(), ProphetModel(), LightGBMGlobal()]


def model_by_name(name: str) -> Forecaster:
    return {m.name: m for m in all_models()}[name]


__all__ = ["BASELINE", "HORIZON", "MODEL_NAMES", "SEASON", "Forecaster", "all_models", "model_by_name"]
