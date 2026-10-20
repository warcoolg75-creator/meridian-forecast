"""ABC-XYZ classification: which products matter, and how steady their volume is.

ABC, by revenue share over the requested period. Products are ranked by revenue; walking
down the ranking, a product is
    A  while the share of the products ranked above it is under 80% (ABC_A_SHARE),
    B  while it is under 95% (ABC_B_SHARE),
    C  after that.
So the product whose revenue takes the running total past 80% is still A (and the top
product is always A), and likewise at 95% for B.

XYZ, by the coefficient of variation (sample standard deviation / mean) of weekly units:
    X  CV < 0.5 (XYZ_X_BELOW),  Y  0.5 <= CV <= 1.0 (XYZ_Y_UP_TO),  Z  CV > 1.0.
Measured over a fixed window, not the requested period: the 52 full Monday-Sunday weeks
ending on or before date_to (a 13-week window made every SKU X, because it cannot see a
seasonal cycle). Only weeks starting on or after the product's launch, and inside the
stored history, count; missing weeks are zero units. Under 13 such weeks the product is
not yet classifiable (xyz null).

XYZ measures volume variability, not predictability: a product with a regular, sharp
festival peak is Z although that pattern is forecastable. Phase 5 should reclassify on the
CV of forecast errors once forecasts exist.
"""

import statistics
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

ABC_A_SHARE = 0.80
ABC_B_SHARE = 0.95
XYZ_X_BELOW = 0.5
XYZ_Y_UP_TO = 1.0
XYZ_WEEKS = 52
XYZ_MIN_WEEKS = 13
SPARKLINE_WEEKS = 13


def abc_classes(revenue: Mapping[str, int]) -> dict[str, str | None]:
    """{key: "A" | "B" | "C"} by revenue share; all None when there is no revenue at all.
    Ties rank by key, so the result does not depend on input order."""
    total = sum(revenue.values())
    if total <= 0:
        return dict.fromkeys(revenue)
    classes: dict[str, str | None] = {}
    share_above = 0.0
    for key in sorted(revenue, key=lambda k: (-revenue[k], k)):
        classes[key] = "A" if share_above < ABC_A_SHARE else "B" if share_above < ABC_B_SHARE else "C"
        share_above += revenue[key] / total
    return classes


def coefficient_of_variation(weekly_units: Sequence[int]) -> float | None:
    """Sample standard deviation / mean; None under XYZ_MIN_WEEKS weeks or without sales."""
    if len(weekly_units) < XYZ_MIN_WEEKS:
        return None
    mean = statistics.fmean(weekly_units)
    if mean <= 0:
        return None
    return statistics.stdev(weekly_units) / mean


def xyz_class(cv: float | None) -> str | None:
    if cv is None:
        return None
    return "X" if cv < XYZ_X_BELOW else "Y" if cv <= XYZ_Y_UP_TO else "Z"


def xyz_weeks(date_to: date, data_first: date, data_last: date) -> list[date]:
    """Mondays of the full weeks XYZ is measured over: up to 52, ending on or before
    date_to and inside the stored history."""
    end = min(date_to, data_last)
    last_sunday = end - timedelta(days=(end.weekday() + 1) % 7)
    first_monday = last_sunday - timedelta(days=XYZ_WEEKS * 7 - 1)
    history_monday = data_first + timedelta(days=(7 - data_first.weekday()) % 7)
    start = max(first_monday, history_monday)
    weeks = []
    monday = start
    while monday + timedelta(days=6) <= last_sunday:
        weeks.append(monday)
        monday += timedelta(days=7)
    return weeks


def weeks_since_launch(weeks: Sequence[date], launched_on: date) -> list[date]:
    """The weeks starting on or after launch (a launch week the product was not on sale
    for in full would read as low demand)."""
    return [w for w in weeks if w >= launched_on]
