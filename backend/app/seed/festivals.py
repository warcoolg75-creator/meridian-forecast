"""Indian public holidays and festivals, and how each one moves demand per category.

Dates come from the pinned `holidays` package wherever it has them:
  * category "public"   -> gazetted national holidays           -> event_type public_holiday
  * category "optional" -> restricted holidays; we use Raksha Bandhan, Onam, Pongal,
                           Ganesh Chaturthi and Durga Puja (the package lists Durga
                           Ashtami as "Dussehra (Mahashtami)")   -> event_type festival
Dhanteras is the only festival we need that the package does not have, so its
dates are hardcoded below.

This module never computes a lunar date itself.
"""

from dataclasses import dataclass
from datetime import date

import holidays

from app.seed.catalog import COOLING, FOODS, INDUSTRIAL, KITCHEN

HOLIDAYS_SOURCE = f"holidays=={holidays.__version__}"
HARDCODED_SOURCE = "hardcoded (UNVERIFIED)"

# NOT VERIFIED AGAINST A SOURCE. Written from memory because the holidays package has
# no Dhanteras; spot-check against a published panchang before trusting them. The
# seed summary prints them next to the package's Diwali dates for that purpose.
HARDCODED_UNVERIFIED: dict[str, tuple[str, list[date]]] = {
    "dhanteras": ("Dhanteras", [date(2023, 11, 10), date(2024, 10, 29), date(2025, 10, 18), date(2026, 11, 6)]),
}
HARDCODED_YEARS = {d.year for _, dates in HARDCODED_UNVERIFIED.values() for d in dates}

# Package holiday name -> our effect key. Any other "public" holiday maps to "other_public".
PUBLIC_KEYS = {
    "Republic Day": "republic_day",
    "Independence Day": "independence_day",
    "Mahatma Gandhi's Jayanti": "gandhi_jayanti",
    "Holi": "holi",
    "Diwali (Deepavali)": "diwali",
    "Dussehra": "dussehra",
    "Id-ul-Fitr": "eid_al_fitr",
    "Id-ul-Zuha (Bakrid)": "eid_al_adha",
    "Christmas": "christmas",
}
# Package "optional" name -> (effect key, state the effect is limited to, or None = national).
OPTIONAL_KEYS: dict[str, tuple[str, str | None]] = {
    "Raksha Bandhan": ("raksha_bandhan", None),
    "Onam": ("onam", "IN-KL"),
    "Pongal": ("pongal", "IN-TN"),
    "Ganesh Chaturthi": ("ganesh_chaturthi", "IN-MH"),
    "Ganesh Chaturthi / Vinayak Chaturthi": ("ganesh_chaturthi", "IN-MH"),
    "Dussehra (Mahashtami)": ("durga_puja", "IN-WB"),
}
DISPLAY_NAMES = {"durga_puja": "Durga Puja (Mahashtami)"}
# The package marks future lunar-calendar dates "Id-ul-Fitr (estimated)"; match on the bare name.
ESTIMATED_SUFFIX = " (estimated)"

# key -> category -> [(first_offset_days, last_offset_days, multiplier)], offsets relative
# to the holiday date, inclusive. Overlapping effects multiply. Regional keys only apply
# to cities inside the holiday's state.
HOLIDAY_EFFECTS: dict[str, dict[str, list[tuple[int, int, float]]]] = {
    "diwali": {FOODS: [(-10, -1, 1.8), (0, 0, 0.8)], KITCHEN: [(-10, -1, 1.3), (0, 0, 0.5)],
               COOLING: [(0, 0, 0.4)], INDUSTRIAL: [(-1, 2, 0.15)]},
    "dhanteras": {KITCHEN: [(0, 0, 2.2)], FOODS: [(0, 0, 1.3)]},
    "holi": {FOODS: [(-5, -1, 1.5), (0, 0, 0.4)], KITCHEN: [(0, 0, 0.5)], COOLING: [(0, 0, 0.5)],
             INDUSTRIAL: [(0, 1, 0.3)]},
    "raksha_bandhan": {FOODS: [(-4, 0, 1.6)]},
    "eid_al_fitr": {FOODS: [(-3, 0, 1.3)], INDUSTRIAL: [(0, 0, 0.6)]},
    "eid_al_adha": {INDUSTRIAL: [(0, 0, 0.6)]},
    "dussehra": {KITCHEN: [(-2, 0, 1.4)], INDUSTRIAL: [(0, 0, 0.3)]},
    "republic_day": {KITCHEN: [(0, 0, 1.1)], COOLING: [(0, 0, 1.1)], INDUSTRIAL: [(0, 0, 0.3)]},
    "independence_day": {KITCHEN: [(0, 0, 1.1)], COOLING: [(0, 0, 1.1)], INDUSTRIAL: [(0, 0, 0.3)]},
    "gandhi_jayanti": {INDUSTRIAL: [(0, 0, 0.3)]},
    "christmas": {FOODS: [(-3, 0, 1.15)], INDUSTRIAL: [(0, 0, 0.5)]},
    "other_public": {INDUSTRIAL: [(0, 0, 0.6)]},
    "durga_puja": {FOODS: [(-3, 1, 2.0)], KITCHEN: [(-3, 0, 1.3)], INDUSTRIAL: [(0, 2, 0.3)]},
    "onam": {FOODS: [(-3, 0, 1.8)], KITCHEN: [(-5, 0, 1.6)]},
    "pongal": {FOODS: [(-2, 0, 1.5)], KITCHEN: [(-3, 0, 1.3)], INDUSTRIAL: [(0, 1, 0.4)]},
    "ganesh_chaturthi": {FOODS: [(-2, 0, 1.5)]},
}


@dataclass(frozen=True)
class Holiday:
    date: date
    key: str
    name: str
    event_type: str  # public_holiday | festival
    region_code: str | None  # state code for regional festivals
    source: str

    def as_dict(self) -> dict:
        return {"date": self.date.isoformat(), "key": self.key, "name": self.name, "event_type": self.event_type,
                "region_code": self.region_code, "source": self.source}


def holiday_calendar(date_from: date, date_to: date) -> list[Holiday]:
    years = range(date_from.year, date_to.year + 1)
    found: list[Holiday] = []

    public = holidays.India(years=years, categories=("public",), language="en_IN")
    for day in public:
        for name in public.get_list(day):
            key = PUBLIC_KEYS.get(name.removesuffix(ESTIMATED_SUFFIX), "other_public")
            found.append(Holiday(day, key, name, "public_holiday", None, f"{HOLIDAYS_SOURCE} public"))

    optional = holidays.India(years=years, categories=("optional",), language="en_IN")
    for day in optional:
        for name in optional.get_list(day):
            bare = name.removesuffix(ESTIMATED_SUFFIX)
            if bare in OPTIONAL_KEYS:
                key, region = OPTIONAL_KEYS[bare]
                found.append(Holiday(day, key, DISPLAY_NAMES.get(key, name), "festival", region,
                                     f"{HOLIDAYS_SOURCE} optional"))

    for key, (name, dates) in HARDCODED_UNVERIFIED.items():
        for day in dates:
            found.append(Holiday(day, key, name, "festival", None, HARDCODED_SOURCE))

    return sorted((h for h in found if date_from <= h.date <= date_to), key=lambda h: (h.date, h.key, h.name))


def uncovered_hardcoded_years(date_from: date, date_to: date) -> list[int]:
    """Years in range for which the hardcoded festivals have no date (so are missing)."""
    return [y for y in range(date_from.year, date_to.year + 1) if y not in HARDCODED_YEARS]
