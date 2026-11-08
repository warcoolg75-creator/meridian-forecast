"""A small synthetic weekly history for the forecasting tests: no database, no ground truth.

Two SKUs with 160 weeks (a yearly cycle, a Diwali bump and promotions) and one launched
20 weeks before the end, all Poisson around a known level from a seeded generator.
"""

from datetime import date, timedelta

import numpy as np

from app.forecasting.calendar import Calendar
from app.forecasting.data import SalesHistory, Sku

FIRST = date(2022, 1, 3)
WEEKS = 160
DIWALI = [date(2022, 10, 24), date(2023, 11, 12), date(2024, 10, 31), date(2025, 10, 20)]


def history(seed: int = 7) -> SalesHistory:
    rng = np.random.default_rng(seed)
    weeks = tuple(FIRST + timedelta(weeks=k) for k in range(WEEKS))
    t = np.arange(WEEKS)
    diwali_weeks = {d - timedelta(days=d.weekday()) - timedelta(weeks=1) for d in DIWALI}
    bump = np.array([2.5 if w in diwali_weeks else 1.0 for w in weeks])
    yearly = 1 + 0.4 * np.sin(2 * np.pi * t / 52)
    units = np.vstack([
        rng.poisson(300 * yearly * bump * (1 + 0.002 * t)),
        rng.poisson(80 * (1 + 0.6 * np.cos(2 * np.pi * t / 52))),
        np.where(t >= WEEKS - 20, rng.poisson(50 * bump), 0),
    ]).astype(float)
    units[2, : WEEKS - 20] = np.nan
    units.setflags(write=False)
    skus = (
        Sku(0, 1, "FX-FOOD", "Fixture sweets", "Packaged Foods", date(2015, 1, 1)),
        Sku(1, 2, "FX-FAN", "Fixture fan", "Cooling", date(2015, 1, 1)),
        Sku(2, 3, "FX-NEW", "Fixture newcomer", "Packaged Foods", weeks[WEEKS - 20]),
    )
    festivals = tuple((d, "diwali") for d in DIWALI) + ((date(2023, 3, 8), "holi"), (date(2024, 3, 25), "holi"))
    promotions = {"FX-FOOD": ((date(2023, 6, 5), date(2023, 6, 14)), (date(2025, 2, 10), date(2025, 2, 16)))}
    return SalesHistory(weeks=weeks, units=units, skus=skus, calendar=Calendar(festivals, promotions),
                        data_end=weeks[-1] + timedelta(days=6))


def scrambled_after(h: SalesHistory, last_week: int, seed: int = 99) -> SalesHistory:
    """The same history with every week after `last_week` replaced by random numbers."""
    units = h.units.copy()
    later = units[:, last_week + 1:]
    units[:, last_week + 1:] = np.where(np.isnan(later), np.nan,
                                        np.random.default_rng(seed).integers(0, 10_000, later.shape))
    units.setflags(write=False)
    return SalesHistory(weeks=h.weeks, units=units, skus=h.skus, calendar=h.calendar, data_end=h.data_end)
