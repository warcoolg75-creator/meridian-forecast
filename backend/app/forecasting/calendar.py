"""Known-in-advance inputs: festival and holiday windows, and planned promotions.

Holidays and festivals are known years ahead (the calendar holds the next 26 weeks).
Recorded promotions are treated as planned, i.e. known in advance: an assumption,
stated in CLAUDE.md. Supply shocks are not known in advance and are never an input.

A festival moves demand on the days around it, so each week gets, per festival, the
number of its days that fall in four windows: 14-8 days before, 7-1 days before, the
day itself and 1-7 days after. The windows are generic; nothing here knows how strongly
any festival moves any product.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

# Event name (as stored in calendar_events) -> feature key. Any other public holiday
# counts as "other_public".
FESTIVAL_KEYS = {
    "Diwali (Deepavali)": "diwali",
    "Dhanteras": "dhanteras",
    "Holi": "holi",
    "Raksha Bandhan": "raksha_bandhan",
    "Id-ul-Fitr": "eid_al_fitr",
    "Id-ul-Zuha (Bakrid)": "eid_al_adha",
    "Dussehra": "dussehra",
    "Christmas": "christmas",
    "Republic Day": "republic_day",
    "Independence Day": "independence_day",
    "Mahatma Gandhi's Jayanti": "gandhi_jayanti",
    "Durga Puja (Mahashtami)": "durga_puja",
    "Onam": "onam",
    "Pongal": "pongal",
    "Ganesh Chaturthi": "ganesh_chaturthi",
    "Ganesh Chaturthi / Vinayak Chaturthi": "ganesh_chaturthi",
}
OTHER_PUBLIC = "other_public"
KEYS = sorted({*FESTIVAL_KEYS.values(), OTHER_PUBLIC})

# (name, first offset, last offset) in days relative to the festival date, inclusive.
WINDOWS = (("pre2", -14, -8), ("pre1", -7, -1), ("day", 0, 0), ("post1", 1, 7))

FEATURE_NAMES = tuple(f"{key}_{window}" for key in KEYS for window, _, _ in WINDOWS)


def festival_key(name: str, public_holiday: bool) -> str | None:
    bare = name.removesuffix(" (estimated)")
    if bare in FESTIVAL_KEYS:
        return FESTIVAL_KEYS[bare]
    return OTHER_PUBLIC if public_holiday else None


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@dataclass(frozen=True)
class Calendar:
    """Festivals as (date, key), and each SKU's planned promotion windows."""

    festivals: tuple[tuple[date, str], ...]
    promotions: dict[str, tuple[tuple[date, date], ...]] = field(default_factory=dict)

    def festival_matrix(self, weeks: list[date]) -> np.ndarray:
        """(len(weeks), len(FEATURE_NAMES)): days of each window inside each week."""
        row = {w: i for i, w in enumerate(weeks)}
        column = {name: i for i, name in enumerate(FEATURE_NAMES)}
        out = np.zeros((len(weeks), len(FEATURE_NAMES)))
        for day, key in self.festivals:
            for window, first, last in WINDOWS:
                for offset in range(first, last + 1):
                    i = row.get(monday(day + timedelta(days=offset)))
                    if i is not None:
                        out[i, column[f"{key}_{window}"]] += 1
        return out

    def promo_days(self, sku: str, weeks: list[date]) -> np.ndarray:
        """Days of each week inside one of the SKU's planned promotions."""
        row = {w: i for i, w in enumerate(weeks)}
        out = np.zeros(len(weeks))
        for first, last in self.promotions.get(sku, ()):
            for k in range((last - first).days + 1):
                i = row.get(monday(first + timedelta(days=k)))
                if i is not None:
                    out[i] += 1
        return out

    def festival_dates(self, key: str) -> list[date]:
        return sorted(d for d, k in self.festivals if k == key)


MERGE_WITHIN_DAYS = 7
MOVES_MORE_THAN_DAYS = 7
YEAR_DAYS = 364  # 52 weeks: the shift the comparison and the year-ago features use


def _dates_by_key(festivals: tuple[tuple[date, str], ...]) -> dict[str, list[date]]:
    out: dict[str, list[date]] = {}
    for day, key in festivals:
        if key != OTHER_PUBLIC:  # a catch-all of unrelated holidays, never one festival
            out.setdefault(key, []).append(day)
    return {k: sorted(v) for k, v in out.items()}


def merged_festivals(festivals: tuple[tuple[date, str], ...], keys: list[str] | tuple[str, ...]) -> list[tuple[str, ...]]:
    """Groups of `keys` whose dates fall within MERGE_WITHIN_DAYS of each other in every year
    either occurs in the calendar (singletons for the rest). Such festivals are
    indistinguishable in weekly data, so a regression gives them huge opposite effects that
    cancel in the past but not when their dates fall differently against the weeks."""
    dates = _dates_by_key(festivals)

    def together(a: str, b: str) -> bool:
        years = {d.year for d in dates.get(a, [])} | {d.year for d in dates.get(b, [])}
        for year in years:
            da = [d for d in dates.get(a, []) if d.year == year]
            db = [d for d in dates.get(b, []) if d.year == year]
            if not da or not db or min(abs((x - y).days) for x in da for y in db) > MERGE_WITHIN_DAYS:
                return False
        return bool(years)

    parent = {k: k for k in keys}

    def root(k: str) -> str:
        while parent[k] != k:
            k = parent[k]
        return k

    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if a in dates and b in dates and together(a, b):
                parent[root(b)] = root(a)
    groups: dict[str, list[str]] = {}
    for k in keys:
        groups.setdefault(root(k), []).append(k)
    return sorted((tuple(sorted(g)) for g in groups.values()), key=lambda g: g[0])


def moving_festivals(festivals: tuple[tuple[date, str], ...]) -> list[str]:
    """Festivals whose date moves by more than MOVES_MORE_THAN_DAYS between consecutive years,
    once the 52-week shift is allowed for (fixed-date holidays move 1-2 days)."""
    out = []
    for key, days in _dates_by_key(festivals).items():
        moves = [abs((b - a).days - YEAR_DAYS) for a, b in zip(days, days[1:])]
        if any(m > MOVES_MORE_THAN_DAYS for m in moves):
            out.append(key)
    return sorted(out)


def festival_offsets(festivals: tuple[tuple[date, str], ...], key: str, weeks: list[date],
                     reach: int = 42) -> np.ndarray:
    """Days from each week's middle (Thursday) to the nearest occurrence of `key`: negative
    before it. NaN when the nearest is more than `reach` days away."""
    days = np.array([d.toordinal() for d in _dates_by_key(festivals).get(key, [])])
    mid = np.array([(w + timedelta(days=3)).toordinal() for w in weeks])
    if days.size == 0:
        return np.full(len(weeks), np.nan)
    offsets = mid[:, None] - days[None, :]
    nearest = offsets[np.arange(len(weeks)), np.argmin(np.abs(offsets), axis=1)].astype(float)
    nearest[np.abs(nearest) > reach] = np.nan
    return nearest
