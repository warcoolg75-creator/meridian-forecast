"""No forecast at an origin may use a value dated after it.

1. Every model, through the backtest's own entry point: scramble every week after the
   origin and the forecasts made at it must not change by a single bit.
2. Inside LightGBM's training rows: the features of an anchor week must not change when
   the weeks after that anchor are scrambled (only the target may).
3. No model or feature module may read the ground truth: only oracle.py imports it, and
   only scoring code imports oracle.py.
"""

import ast
from pathlib import Path

import numpy as np
import pytest

from app.forecasting.backtest import forecast_origin
from app.forecasting.models import all_models
from app.forecasting.models.lightgbm_model import FEATURES, _before, build_rows
from tests.forecast_fixture import history, scrambled_after

FORECASTING = Path(__file__).resolve().parent.parent / "app" / "forecasting"


@pytest.mark.parametrize("origin", [120, 145])
def test_scrambling_the_weeks_after_an_origin_changes_no_forecast(origin):
    h = history()
    clean = forecast_origin(h, origin, all_models(), seed=42)
    dirty = forecast_origin(scrambled_after(h, origin - 1), origin, all_models(), seed=42)
    assert clean.keys() == dirty.keys() == {"seasonal_naive", "ets", "prophet", "lightgbm"}
    for model, by_sku in clean.items():
        assert by_sku.keys() == dirty[model].keys(), model
        for sku, values in by_sku.items():
            np.testing.assert_array_equal(values, dirty[model][sku], err_msg=f"{model} {sku}")


def test_lightgbm_features_of_an_anchor_ignore_every_later_week():
    h = history()
    anchor_rows = 26  # anchor 100's rows, with targets up to week 126 inside the history
    X, y, _ = build_rows(h.until(130), 26, train=True)
    X2, y2, _ = build_rows(scrambled_after(h, 100).until(130), 26, train=True)
    # Rows are ordered SKU by SKU, anchor by anchor: find anchor 100 of the first SKU.
    first_anchor = 12  # LEVEL_WEEKS - 1 for a SKU with data from week 0
    start = sum(min(26, 130 - t) for t in range(first_anchor, 100))
    rows = slice(start, start + anchor_rows)
    np.testing.assert_array_equal(X[rows], X2[rows])
    assert not np.array_equal(y[rows], y2[rows])  # the targets do come from later weeks
    assert X.shape[1] == len(FEATURES)


def test_before_never_returns_a_week_after_the_anchor():
    values = np.arange(10.0)
    out = _before(values, np.array([-1, 0, 5, 6, 9]), anchor=5)
    np.testing.assert_array_equal(out, [np.nan, 0, 5, np.nan, np.nan])


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_only_the_oracle_reads_the_ground_truth_and_only_scoring_reads_the_oracle():
    scoring = {"oracle.py", "backtest.py", "scoring.py", "report.py"}
    for path in sorted(FORECASTING.rglob("*.py")):
        imports = _imports(path)
        if any(name.startswith("app.seed.ground_truth") for name in imports):
            assert path.name == "oracle.py", f"{path.name} reads the ground truth"
        if path.name not in scoring:
            assert not any(name.startswith("app.forecasting.oracle") for name in imports), f"{path.name} reads the oracle"
    # Models and features read neither the seed, the oracle, nor the scoring modules that use it.
    for path in [*(FORECASTING / "models").glob("*.py"), FORECASTING / "calendar.py", FORECASTING / "data.py",
                 FORECASTING / "intervals.py", FORECASTING / "production.py"]:
        forbidden = ("app.seed", "app.forecasting.oracle", "app.forecasting.scoring", "app.forecasting.backtest")
        assert not any(name.startswith(forbidden) for name in _imports(path)), path.name
