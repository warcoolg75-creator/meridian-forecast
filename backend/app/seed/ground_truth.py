"""Ground truth for the synthetic demand: its parameters, and the expected demand they imply.

build_ground_truth() draws the random parameters (promotion windows, supply shocks),
rounds them, and returns one JSON-serialisable dict. expected_cell_demand() turns
that dict - and only that dict - into expected units per day per sales cell. The
generator samples from exactly these expectations, so ground_truth.json is the
truth by construction, and a later phase can import expected_cell_demand() to score
forecasts against it.

Model, for product p, day d and sales cell c (= customer x ship-to city):

    mu[p,d,c] = base_level[p]
              * trend[p](d)            exponential (1+g)^(t/365.25), t = days since window start;
                                       launch_ramp: logistic(days since launch; midpoint, scale)
                                       * (1+g)^(days since launch/365.25); 0 before launch
              * weekly[profile](dow)   7 multipliers, mean 1.0, Monday first
              * yearly[p](d)           1 + sum_k A_k * exp(-0.5 * (dist(d, center_k) / width_k)^2),
                                       dist = days to the nearest occurrence of center MM-DD
              * promo[p](d)            lift inside a promotion window, else 1
              * holiday_national[cat](d)  product of national holiday effects for the category
              * shock[p](d)            multiplier inside a supply-shock window, else 1
              * customer_weight[p,c]   region share * channel share * share within the channel
              * holiday_regional[cat](d, state(c))  regional festival effects in that state only

    units[p,d,c] ~ Poisson(mu[p,d,c]),  and mu = 0 before the product's launch date.
"""

import json
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from app.seed.catalog import (
    CHANNEL_PRICE_FACTOR,
    CONSUMER,
    CUSTOMERS,
    ECOMMERCE_SHARES,
    LAUNCH_MONTHS_AGO,
    PRODUCTS,
    REGIONS,
    WEEKLY_PROFILES,
    ProductSpec,
)
from app.seed.festivals import HOLIDAY_EFFECTS, HOLIDAYS_SOURCE, holiday_calendar

SCHEMA_VERSION = 1
GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "ground_truth.json"
HOLIDAY_LOOKBACK_DAYS = 30  # lead effects (e.g. Diwali -10 days) can reach back into the window
CALENDAR_HORIZON_DAYS = 182  # holidays are known ahead; keep the next 26 weeks for forecasting

# RNG stream ids: every (purpose, product) pair gets an independent stream, so adding a
# product or changing how orders are split does not move any other draw.
STREAM_PARAMS, STREAM_SAMPLE, STREAM_ORDERS, STREAM_PRODUCTION = 1, 2, 3, 4


def rng_for(seed: int, stream: int, index: int = 0) -> np.random.Generator:
    return np.random.default_rng([seed, stream, index])


def window_for(end: date, years: int) -> tuple[date, date]:
    """`years` full years of daily history ending on `end` (inclusive)."""
    try:
        anchor = end.replace(year=end.year - years)
    except ValueError:  # end is 29 Feb
        anchor = date(end.year - years, 2, 28)
    return anchor + timedelta(days=1), end


def months_before(d: date, months: int) -> date:
    month_index = d.year * 12 + (d.month - 1) - months
    year, month = divmod(month_index, 12)
    return date(year, month + 1, min(d.day, 28))


def launch_date(spec: ProductSpec, end: date) -> date:
    return spec.launched_on or months_before(end, LAUNCH_MONTHS_AGO)


# --------------------------------------------------------------------------- drawing


def _blocks(active_from: date, end: date) -> list[tuple[date, int]]:
    """Split [active_from, end] into ~365-day product-years; a short tail joins the last block."""
    total = (end - active_from).days + 1
    starts = list(range(0, total, 365))
    if len(starts) > 1 and total - starts[-1] < 90:
        starts.pop()
    return [(active_from + timedelta(days=s), (starts[i + 1] if i + 1 < len(starts) else total) - s)
            for i, s in enumerate(starts)]


def _draw_windows(rng, active_from, end, per_year, length, min_gap, extra) -> list[dict]:
    windows: list[tuple[date, date]] = []
    result = []
    for block_start, block_len in _blocks(active_from, end):
        count = math.ceil(int(rng.integers(per_year[0], per_year[1] + 1)) * min(block_len, 365) / 365)
        for _ in range(count):
            for _attempt in range(100):
                days = int(rng.integers(length[0], length[1] + 1))
                if days > block_len:
                    break
                start = block_start + timedelta(days=int(rng.integers(0, block_len - days + 1)))
                stop = start + timedelta(days=days - 1)
                if all(stop + timedelta(days=min_gap) < s or e + timedelta(days=min_gap) < start
                       for s, e in windows):
                    windows.append((start, stop))
                    result.append({"start": start.isoformat(), "end": stop.isoformat(), **extra(rng)})
                    break
    return sorted(result, key=lambda w: w["start"])


def customer_weights(spec: ProductSpec) -> dict[str, float]:
    """Share of the product's national demand going to each cell "<customer>@<city>"."""
    region_total = sum(spec.demand.region_weights.values())
    weights: dict[str, float] = {}
    for city, region_weight in sorted(spec.demand.region_weights.items()):
        if region_weight <= 0:
            continue
        eligible: dict[str, list[str]] = {}
        for code, _name, channel, home_city, buys in CUSTOMERS:
            if spec.category not in buys or spec.demand.channel_weights.get(channel, 0) <= 0:
                continue
            serves_city = home_city == city or (channel == "ecommerce" and spec.category in CONSUMER)
            if serves_city:
                eligible.setdefault(channel, []).append(code)
        if not eligible:
            raise ValueError(f"{spec.sku}: no customer can buy it in {city}")
        channel_total = sum(spec.demand.channel_weights[ch] for ch in eligible)
        for channel, codes in sorted(eligible.items()):
            channel_share = spec.demand.channel_weights[channel] / channel_total
            if channel == "ecommerce":
                share_total = sum(ECOMMERCE_SHARES[c] for c in codes)
                shares = {c: ECOMMERCE_SHARES[c] / share_total for c in codes}
            else:
                shares = {c: 1 / len(codes) for c in codes}
            for code in codes:
                weights[f"{code}@{city}"] = round(region_weight / region_total * channel_share * shares[code], 6)
    return dict(sorted(weights.items()))


def build_ground_truth(seed: int, start: date, end: date) -> dict:
    holidays = holiday_calendar(start - timedelta(days=HOLIDAY_LOOKBACK_DAYS),
                                end + timedelta(days=CALENDAR_HORIZON_DAYS))
    products = {}
    for index, spec in enumerate(PRODUCTS):
        rng = rng_for(seed, STREAM_PARAMS, index)
        launched_on = launch_date(spec, end)
        active_from = max(start, launched_on)
        promotions = _draw_windows(
            rng, active_from, end, per_year=(3, 5), length=(5, 14), min_gap=14,
            extra=lambda r: {"lift": round(float(r.uniform(1.4, 2.2)), 2),
                             "discount_pct": round(float(r.uniform(0.08, 0.20)), 2)},
        )
        shocks = _draw_windows(
            rng, active_from, end, per_year=(2, 4), length=(2, 6), min_gap=7,
            extra=lambda r: {"multiplier": round(float(r.uniform(0.02, 0.08)), 3)},
        )
        demand = spec.demand
        products[spec.sku] = {
            "name": spec.name,
            "category": spec.category,
            "launched_on": launched_on.isoformat(),
            "lifecycle": demand.lifecycle,
            "base_level": demand.base_level,
            "trend": demand.trend,
            "weekly_profile": demand.weekly_profile,
            "yearly": demand.yearly,
            "region_weights": {k: round(v, 6) for k, v in sorted(demand.region_weights.items())},
            "channel_weights": dict(sorted(demand.channel_weights.items())),
            "customer_weights": customer_weights(spec),
            "list_price_minor": spec.unit_price_minor,
            "promotions": promotions,
            "shocks": shocks,
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": (end - start).days + 1},
        "model": "units[p,d,c] ~ Poisson(base_level * trend * weekly * yearly * promo * holiday_national"
                 " * shock * customer_weight * holiday_regional); see app/seed/ground_truth.py",
        "holidays_source": HOLIDAYS_SOURCE,
        "weekly_profiles": WEEKLY_PROFILES,
        "channel_price_factor": CHANNEL_PRICE_FACTOR,
        "customer_channels": {code: channel for code, _n, channel, _c, _b in CUSTOMERS},
        "city_state": {code: parent for code, _n, level, parent in REGIONS if level == "city"},
        "holiday_effects": {key: {cat: [list(w) for w in windows] for cat, windows in sorted(effects.items())}
                            for key, effects in sorted(HOLIDAY_EFFECTS.items())},
        "holidays": [h.as_dict() for h in holidays],
        "products": products,
    }


def write_ground_truth(gt: dict, path: Path = GROUND_TRUTH_PATH) -> bytes:
    """Stable bytes: sorted keys, LF line endings, no timestamps."""
    payload = (json.dumps(gt, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")
    path.write_bytes(payload)
    return payload


def load_ground_truth(path: Path = GROUND_TRUTH_PATH) -> dict:
    return json.loads(path.read_text(encoding="ascii"))


# --------------------------------------------------------------------------- expectation


def _dates(gt: dict) -> np.ndarray:
    start = np.datetime64(gt["window"]["start"], "D")
    return start + np.arange(gt["window"]["days"])


def _window_mask(dates: np.ndarray, first: str, last: str) -> np.ndarray:
    return (dates >= np.datetime64(first, "D")) & (dates <= np.datetime64(last, "D"))


def _yearly(dates: np.ndarray, components: list[dict]) -> np.ndarray:
    result = np.ones(len(dates))
    years = dates.astype("datetime64[Y]").astype(int) + 1970
    for component in components:
        month, day = (int(x) for x in component["center"].split("-"))
        distance = np.full(len(dates), np.inf)
        for year in range(years.min() - 1, years.max() + 2):
            center = np.datetime64(date(year, month, day).isoformat(), "D")
            distance = np.minimum(distance, np.abs((dates - center).astype(int)))
        result += component["amplitude"] * np.exp(-0.5 * (distance / component["width_days"]) ** 2)
    return result


def _trend(dates: np.ndarray, window_start: np.datetime64, launched_on: np.datetime64, trend: dict) -> np.ndarray:
    if trend["type"] == "exponential":
        t = (dates - window_start).astype(int)
        return (1 + trend["annual_growth"]) ** (t / 365.25)
    if trend["type"] == "launch_ramp":
        s = (dates - launched_on).astype(int)
        ramp = 1 / (1 + np.exp(-(s - trend["midpoint_days"]) / trend["scale_days"]))
        return np.where(s < 0, 0.0, ramp * (1 + trend["annual_growth"]) ** (np.maximum(s, 0) / 365.25))
    raise ValueError(f"unknown trend type {trend['type']!r}")


def _holiday_multiplier(gt: dict, dates: np.ndarray, category: str, region_code: str | None) -> np.ndarray:
    """Multiplier from holidays scoped to `region_code` (None = national holidays)."""
    result = np.ones(len(dates))
    for holiday in gt["holidays"]:
        if holiday["region_code"] != region_code:
            continue
        for first, last, multiplier in gt["holiday_effects"].get(holiday["key"], {}).get(category, []):
            anchor = np.datetime64(holiday["date"], "D")
            offset = (dates - anchor).astype(int)
            result[(offset >= first) & (offset <= last)] *= multiplier
    return result


def promo_by_day(gt: dict, sku: str) -> tuple[np.ndarray, np.ndarray]:
    """(lift, discount_pct) per day; 1.0 / 0.0 outside promotion windows."""
    dates = _dates(gt)
    lift, discount = np.ones(len(dates)), np.zeros(len(dates))
    for promo in gt["products"][sku]["promotions"]:
        mask = _window_mask(dates, promo["start"], promo["end"])
        lift[mask] = promo["lift"]
        discount[mask] = promo["discount_pct"]
    return lift, discount


def shock_by_day(gt: dict, sku: str) -> np.ndarray:
    dates = _dates(gt)
    result = np.ones(len(dates))
    for shock in gt["products"][sku]["shocks"]:
        result[_window_mask(dates, shock["start"], shock["end"])] *= shock["multiplier"]
    return result


def national_component(gt: dict, sku: str) -> np.ndarray:
    """Everything in mu except the cell weight and regional festivals."""
    p = gt["products"][sku]
    dates = _dates(gt)
    window_start = np.datetime64(gt["window"]["start"], "D")
    launched_on = np.datetime64(p["launched_on"], "D")
    weekly = np.array(gt["weekly_profiles"][p["weekly_profile"]])
    weekday = (dates.astype(int) + 3) % 7  # 1970-01-01 was a Thursday; Monday = 0

    mu = (p["base_level"]
          * _trend(dates, window_start, launched_on, p["trend"])
          * weekly[weekday]
          * _yearly(dates, p["yearly"])
          * promo_by_day(gt, sku)[0]
          * _holiday_multiplier(gt, dates, p["category"], None)
          * shock_by_day(gt, sku))
    mu[dates < launched_on] = 0.0
    return mu


def expected_cell_demand(gt: dict, sku: str) -> tuple[list[str], np.ndarray]:
    """Cells ("<customer>@<city>") and expected units, shape (days, cells)."""
    p = gt["products"][sku]
    dates = _dates(gt)
    cells = sorted(p["customer_weights"])
    weights = np.array([p["customer_weights"][c] for c in cells])
    mu = national_component(gt, sku)[:, None] * weights[None, :]

    regional_states = sorted({h["region_code"] for h in gt["holidays"] if h["region_code"]})
    cell_states = [gt["city_state"][c.split("@")[1]] for c in cells]
    for state in regional_states:
        columns = [i for i, s in enumerate(cell_states) if s == state]
        if columns:
            mu[:, columns] *= _holiday_multiplier(gt, dates, p["category"], state)[:, None]
    return cells, mu
