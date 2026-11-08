"""The forward oracle test: the production forecast against expected demand.

The only out-of-sample festive check there is: the production forecast (w/c 2026-10-05
to 2027-03-29) spans Diwali 2026, which no backtest saw. It is scored against the ground
truth's expected demand for those weeks, computed with no promotions and no shocks, the
forecast's own assumptions; seasonal naive's forward forecast is scored the same way.
These are errors against an expectation, not noisy actuals: not comparable with backtest
WAPE, and reported in a section of their own.
"""

from datetime import date, timedelta

import numpy as np

from app.forecasting import oracle
from app.forecasting.data import SalesHistory
from app.forecasting.metrics import skill, wape
from app.forecasting.models import HORIZON
from app.forecasting.models.seasonal_naive import SeasonalNaive

# The categories whose demand the festive season moves: their champions must peak in the
# Diwali weeks.
FESTIVE_CATEGORIES = ("Packaged Foods", "Kitchen Appliances")
DIWALI_LEAD_DAYS = 10  # the festive buying before Diwali, as the weeks that hold it


def forward_scores(history: SalesHistory, rows: list[dict], headline_skus: list[str],
                   every_model: dict[str, dict[str, np.ndarray]] | None = None) -> dict:
    """`every_model`: each model's forward p50 (not only the champions'), for the
    diagnostic of which models can place Diwali."""
    weeks = history.future_weeks(HORIZON)
    skus = sorted({r["sku"] for r in rows})
    champion = {sku: np.array([r["p50"] for r in rows if r["sku"] == sku], dtype=float) for sku in skus}
    model = {sku: next(r["model"] for r in rows if r["sku"] == sku) for sku in skus}
    naive = SeasonalNaive().forecast(history, HORIZON)
    expected = oracle.expected_weekly_planned(skus, weeks)
    festive = sorted(s.sku for s in history.skus if s.category in FESTIVE_CATEGORIES and s.sku in skus)

    per_sku = []
    for sku in skus:
        c = wape(expected[sku], champion[sku])
        n = wape(expected[sku], naive[sku]) if sku in naive else None
        per_sku.append({"sku": sku, "model": model[sku], "champion_wape": c, "naive_wape": n, "skill": skill(c, n),
                        "festive": sku in festive})

    def pooled(group: list[str]) -> dict:
        group = [s for s in group if s in naive]
        e = np.concatenate([expected[s] for s in group])
        c = wape(e, np.concatenate([champion[s] for s in group]))
        n = wape(e, np.concatenate([naive[s] for s in group]))
        return {"skus": group, "champion_wape": c, "naive_wape": n, "skill": skill(c, n)}

    diwali = _diwali(history)
    peak_weeks = _weeks_holding(diwali - timedelta(days=DIWALI_LEAD_DAYS), diwali)
    peaks = []
    autumn = [i for i, w in enumerate(weeks) if w.month in (9, 10, 11, 12)]
    for sku in festive:
        def peak(values: np.ndarray) -> str:
            return str(weeks[autumn[int(np.argmax(values[autumn]))]])
        peaks.append({"sku": sku, "model": model[sku], "champion_peak": peak(champion[sku]),
                      "expected_peak": peak(expected[sku]), "naive_peak": peak(naive[sku]) if sku in naive else None,
                      "pass": peak(champion[sku]) in {str(w) for w in peak_weeks}})
    by_model = {
        name: {sku: (str(weeks[autumn[int(np.argmax(values[sku][autumn]))]]) if sku in values else None)
               for sku in festive}
        for name, values in sorted((every_model or {}).items())
    }
    return {
        "weeks": [str(weeks[0]), str(weeks[-1])],
        "peaks_by_model": by_model,
        "pooled": pooled(headline_skus),
        "festive_pooled": pooled([s for s in festive if s in headline_skus]),
        "per_sku": per_sku,
        "diwali": {"date": str(diwali), "peak_weeks": [str(w) for w in peak_weeks], "skus": peaks},
    }


def _diwali(history: SalesHistory) -> date:
    after = [d for d in history.calendar.festival_dates("diwali") if d > history.weeks[-1]]
    if not after:
        raise ValueError("The calendar has no Diwali after the data end")
    return after[0]


def _weeks_holding(first: date, last: date) -> list[date]:
    start = first - timedelta(days=first.weekday())
    return [start + timedelta(weeks=k) for k in range((last - start).days // 7 + 1)]
