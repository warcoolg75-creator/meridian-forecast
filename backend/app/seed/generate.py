"""`make seed`: wipe the database and regenerate every table, deterministically.

Pipeline (all randomness from numpy Generators seeded by (seed, stream, product)):
  1. ground truth  - draw promotions/shocks, write ground_truth.json
  2. sales         - units[p,d,c] ~ Poisson(expected_cell_demand), turned into orders:
                     one order per customer, ship-to city and day (all its products as
                     lines); ecommerce demand is split into up to 3 single-line orders
  3. production    - per line, an order-up-to plan driven by trailing 28-day sales,
                     capped by line capacity; supply shocks show up as downtime
  4. inventory     - per product and plant: on_hand = on_hand + yesterday's output - sales
                     (floored at zero; stock-outs do not feed back into sales)
  5. calendar      - holidays/festivals (incl. the next 26 weeks), promotions, plant
                     shutdowns, trade shows
  6. load          - wipe, bulk insert (executemany), rebuild daily_sales via the rollup

Production and inventory are plausible illustrations only; the scored ground truth is demand.
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import func, insert, select, text
from sqlalchemy.orm import Session

from app.models import (
    Base,
    CalendarEvent,
    Customer,
    DailySales,
    Inventory,
    LineCapability,
    Plant,
    Product,
    ProductionLine,
    ProductionRun,
    Region,
    SalesOrder,
    SalesOrderLine,
)
from app.seed.catalog import (
    CAPABILITIES,
    CHANNEL_PRICE_FACTOR,
    CUSTOMERS,
    LINES,
    PLANTS,
    PRODUCTS,
    REGIONS,
    SCRAP_RATE,
    TRADE_SHOWS,
)
from app.seed.festivals import HARDCODED_SOURCE, uncovered_hardcoded_years
from app.seed.ground_truth import (
    CALENDAR_HORIZON_DAYS,
    GROUND_TRUTH_PATH,
    STREAM_ORDERS,
    STREAM_PRODUCTION,
    STREAM_SAMPLE,
    build_ground_truth,
    expected_cell_demand,
    launch_date,
    promo_by_day,
    rng_for,
    shock_by_day,
    window_for,
    write_ground_truth,
)
from app.services.rollup import rebuild_daily_sales

INSERT_CHUNK = 50_000
ECOMMERCE_MAX_ORDERS = 3
TRAILING_DAYS = 28
COVER_DAYS = 7
SAFETY_DAYS = 5
PRE_LAUNCH_BUILD_DAYS = 21
LOAD_ORDER = [Region, Plant, Product, ProductionLine, LineCapability, Customer,
              SalesOrder, SalesOrderLine, Inventory, ProductionRun, CalendarEvent]


@dataclass
class Reference:
    region_id: dict[str, int]
    plant_id: dict[str, int]
    product_id: dict[str, int]
    line_id: dict[str, int]
    customer_id: dict[str, int]
    rows: dict[type, list[dict]] = field(default_factory=dict)


@dataclass
class SeedReport:
    seed: int
    start: date
    end: date
    seconds: float
    ground_truth_path: Path
    table_counts: dict[str, int]
    product_days: int
    daily_sales_rows: int
    product_table: pd.DataFrame
    holidays: list[dict]
    warnings: list[str]


def utc_yesterday() -> date:
    return datetime.now(UTC).date() - timedelta(days=1)


# --------------------------------------------------------------------------- reference data


def build_reference(end: date) -> Reference:
    region_id = {code: i for i, (code, *_rest) in enumerate(REGIONS, start=1)}
    plant_id = {p["code"]: i for i, p in enumerate(PLANTS, start=1)}
    product_id = {p.sku: i for i, p in enumerate(PRODUCTS, start=1)}
    line_id = {line["code"]: i for i, line in enumerate(LINES, start=1)}
    customer_id = {c[0]: i for i, c in enumerate(CUSTOMERS, start=1)}

    ref = Reference(region_id, plant_id, product_id, line_id, customer_id)
    ref.rows[Region] = [
        dict(id=region_id[code], code=code, name=name, country="IN", level=level,
             parent_region_id=region_id[parent] if parent else None)
        for code, name, level, parent in REGIONS
    ]
    ref.rows[Plant] = [dict(id=plant_id[p["code"]], **p) for p in PLANTS]
    ref.rows[Product] = [
        dict(id=product_id[p.sku], sku=p.sku, name=p.name, category=p.category, subcategory=p.subcategory,
             unit_cost_minor=p.unit_cost_minor, unit_price_minor=p.unit_price_minor,
             unit_of_measure=p.unit_of_measure, shelf_life_days=p.shelf_life_days, is_active=True,
             launched_on=launch_date(p, end))
        for p in PRODUCTS
    ]
    ref.rows[ProductionLine] = [
        dict(id=line_id[line["code"]], code=line["code"], name=line["name"], plant_id=plant_id[line["plant"]],
             units_per_hour=line["units_per_hour"], changeover_minutes=line["changeover_minutes"],
             operating_hours_per_day=line["operating_hours_per_day"], is_active=True)
        for line in LINES
    ]
    ref.rows[LineCapability] = [
        dict(id=i, production_line_id=line_id[line], product_id=product_id[sku], units_per_hour_override=override)
        for i, (line, sku, override) in enumerate(CAPABILITIES, start=1)
    ]
    ref.rows[Customer] = [
        dict(id=customer_id[code], code=code, name=name, channel=channel, region_id=region_id[city])
        for code, name, channel, city, _buys in CUSTOMERS
    ]
    return ref


# --------------------------------------------------------------------------- sales


def sample_order_lines(gt: dict, ref: Reference, seed: int) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Poisson-sample every product/day/cell and return one row per order line piece."""
    channel_of = {code: channel for code, _n, channel, _c, _b in CUSTOMERS}
    frames, daily_units = [], {}
    for index, spec in enumerate(PRODUCTS):
        cells, mu = expected_cell_demand(gt, spec.sku)
        units = rng_for(seed, STREAM_SAMPLE, index).poisson(mu)
        daily_units[spec.sku] = units.sum(axis=1)
        day, cell = np.nonzero(units)
        customers = [c.split("@")[0] for c in cells]
        frames.append(pd.DataFrame({
            "day": day,
            "customer_id": np.array([ref.customer_id[c] for c in customers])[cell],
            "region_id": np.array([ref.region_id[c.split("@")[1]] for c in cells])[cell],
            "channel": np.array([channel_of[c] for c in customers])[cell],
            "product_id": ref.product_id[spec.sku],
            "quantity": units[day, cell],
        }))
    lines = pd.concat(frames, ignore_index=True).sort_values(
        ["day", "customer_id", "region_id", "product_id"], kind="stable", ignore_index=True)

    # Ecommerce: split each cell's units into up to 3 consumer orders (each >= 1 unit).
    quantity = lines["quantity"].to_numpy()
    is_ecom = (lines["channel"] == "ecommerce").to_numpy()
    pieces = np.where(is_ecom, np.minimum(quantity, ECOMMERCE_MAX_ORDERS), 1)
    first_piece = np.cumsum(pieces) - pieces
    piece_qty = np.zeros(pieces.sum(), dtype=np.int64)
    piece_qty[first_piece[pieces == 1]] = quantity[pieces == 1]
    order_rng = rng_for(seed, STREAM_ORDERS)
    for k in range(2, ECOMMERCE_MAX_ORDERS + 1):
        rows = np.nonzero(pieces == k)[0]
        if len(rows):
            split = order_rng.multinomial(quantity[rows] - k, [1 / k] * k) + 1
            for j in range(k):
                piece_qty[first_piece[rows] + j] = split[:, j]

    expanded = lines.loc[lines.index.repeat(pieces)].reset_index(drop=True)
    expanded["quantity"] = piece_qty
    sub = np.arange(len(expanded)) - np.repeat(first_piece, pieces)
    ecom = (expanded["channel"] == "ecommerce").to_numpy()
    expanded["order_product"] = np.where(ecom, expanded["product_id"], 0)
    expanded["order_sub"] = np.where(ecom, sub, 0)
    return expanded, daily_units


def build_orders(gt: dict, lines: pd.DataFrame, dates: list[date]) -> tuple[list[dict], list[dict]]:
    key = ["day", "customer_id", "region_id", "order_product", "order_sub"]
    orders = lines[key + ["channel"]].drop_duplicates(key).sort_values(key, ignore_index=True)
    orders["order_id"] = np.arange(1, len(orders) + 1)
    lines = lines.merge(orders[key + ["order_id"]], on=key, how="left", validate="many_to_one")
    lines = lines.sort_values(["order_id", "product_id"], kind="stable", ignore_index=True)

    # Net unit price by product and channel; promotion discount by product and day.
    # Product ids follow PRODUCTS order (build_reference), so product_id - 1 indexes rows.
    list_price = {i: gt["products"][spec.sku]["list_price_minor"] for i, spec in enumerate(PRODUCTS, start=1)}
    unit_price = np.array([round(list_price[p] * CHANNEL_PRICE_FACTOR[c])
                           for p, c in zip(lines["product_id"], lines["channel"])], dtype=np.int64)
    discount_pct = np.vstack([promo_by_day(gt, spec.sku)[1] for spec in PRODUCTS])
    pct = discount_pct[lines["product_id"].to_numpy() - 1, lines["day"].to_numpy()]
    quantity = lines["quantity"].to_numpy()
    discount = np.rint(quantity * unit_price * pct).astype(np.int64)

    order_rows = [
        dict(id=i, order_date=dates[d], customer_id=c, region_id=r, channel=ch, currency="INR")
        for i, d, c, r, ch in zip(orders["order_id"].tolist(), orders["day"].tolist(),
                                  orders["customer_id"].tolist(), orders["region_id"].tolist(),
                                  orders["channel"].tolist())
    ]
    line_rows = [
        dict(id=i, sales_order_id=o, product_id=p, quantity=q, unit_price_minor=u, discount_minor=disc,
             is_promotional=promo)
        for i, o, p, q, u, disc, promo in zip(
            range(1, len(lines) + 1), lines["order_id"].tolist(), lines["product_id"].tolist(),
            quantity.tolist(), unit_price.tolist(), discount.tolist(), (pct > 0).tolist())
    ]
    return order_rows, line_rows


# --------------------------------------------------------------------------- production & inventory


def plant_shutdowns(gt: dict, start: date, end: date) -> list[dict]:
    """PUN year-end maintenance, CHN May maintenance, MNS the four days after Diwali."""
    windows = []
    for year in range(start.year, end.year + 1):
        windows.append(("PUN", date(year, 12, 26), date(year, 12, 31), "Year-end maintenance shutdown"))
        windows.append(("CHN", date(year, 5, 1), date(year, 5, 5), "Summer maintenance shutdown"))
    for holiday in gt["holidays"]:
        if holiday["key"] == "diwali":
            diwali = date.fromisoformat(holiday["date"])
            windows.append(("MNS", diwali + timedelta(days=1), diwali + timedelta(days=4),
                            "Post-Diwali shutdown"))
    return [dict(plant=p, start=max(s, start), end=min(e, end), name=n)
            for p, s, e, n in sorted(windows, key=lambda w: (w[1], w[0])) if e >= start and s <= end]


def simulate_production(gt: dict, ref: Reference, daily_units: dict[str, np.ndarray], dates: list[date],
                        shutdowns: list[dict], seed: int) -> tuple[list[dict], list[dict]]:
    rng = rng_for(seed, STREAM_PRODUCTION)
    n = len(dates)
    start = dates[0]
    line_by_code = {line["code"]: line for line in LINES}
    category = {spec.sku: spec.category for spec in PRODUCTS}

    makers: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for line_code, sku, override in CAPABILITIES:
        makers[sku].append((line_code, override or line_by_code[line_code]["units_per_hour"]))
    products_on_line: dict[str, list[str]] = defaultdict(list)
    share, rate = {}, {}
    for sku, lines in makers.items():
        total = sum(u for _, u in lines)
        for line_code, uph in lines:
            share[(sku, line_code)] = uph / total
            rate[(sku, line_code)] = uph
            products_on_line[line_code].append(sku)

    # Each line ships its share of the day's sales; the last line takes the rounding remainder.
    shipped: dict[tuple[str, str], np.ndarray] = {}
    for sku, lines in makers.items():
        remaining = daily_units[sku].astype(np.int64)
        for j, (line_code, _uph) in enumerate(lines):
            if j == len(lines) - 1:
                shipped[(sku, line_code)] = remaining
            else:
                part = np.rint(daily_units[sku] * share[(sku, line_code)]).astype(np.int64)
                shipped[(sku, line_code)] = part
                remaining = remaining - part

    expected = {spec.sku: expected_cell_demand(gt, spec.sku)[1].sum(axis=1) for spec in PRODUCTS}
    cumulative = {sku: np.concatenate([[0], np.cumsum(u)]) for sku, u in daily_units.items()}
    shock = {spec.sku: shock_by_day(gt, spec.sku) for spec in PRODUCTS}
    launch_idx = {spec.sku: (launch_date(spec, dates[-1]) - start).days for spec in PRODUCTS}
    first_day = {sku: max(0, idx - PRE_LAUNCH_BUILD_DAYS) for sku, idx in launch_idx.items()}
    shutdown_days: dict[str, set[int]] = defaultdict(set)
    for window in shutdowns:
        for k in range((window["start"] - start).days, (window["end"] - start).days + 1):
            shutdown_days[window["plant"]].add(k)

    def demand_signal(sku: str, line_code: str, d: int) -> float:
        selling_from = max(launch_idx[sku], 0)
        if d - selling_from >= TRAILING_DAYS:
            mean = (cumulative[sku][d] - cumulative[sku][d - TRAILING_DAYS]) / TRAILING_DAYS
        else:  # cold start: no sales history yet, plan from the first two weeks of expected demand
            anchor = max(d, launch_idx[sku])
            mean = float(expected[sku][anchor:anchor + 14].mean()) if anchor < n else 0.0
        return share[(sku, line_code)] * mean

    on_hand: dict[tuple[str, str], int] = {}
    in_transit: dict[tuple[str, str], int] = defaultdict(int)
    for sku, lines in makers.items():
        for line_code, _ in lines:
            mature = launch_idx[sku] <= 0
            signal = demand_signal(sku, line_code, 0) if mature else 0.0
            on_hand[(sku, line_code)] = math.ceil((SAFETY_DAYS + COVER_DAYS) * signal) if mature else 0

    runs, inventory = [], []
    for d in range(n):
        for line in LINES:
            code, plant = line["code"], line["plant"]
            active = sorted(sku for sku in products_on_line[code] if d >= first_day[sku])
            signals = {sku: demand_signal(sku, code, d) for sku in active}
            produced: dict[str, int] = {}
            if active and d not in shutdown_days[plant]:
                queue = []
                for sku in active:
                    target = math.ceil(SAFETY_DAYS * signals[sku]) + COVER_DAYS * signals[sku]
                    need = max(0, math.ceil(target - on_hand[(sku, code)] - in_transit[(sku, code)]))
                    queue.append((-need / max(signals[sku], 1.0), sku, need))
                minutes, first = line["operating_hours_per_day"] * 60, True
                for _priority, sku, need in sorted(queue):
                    if need <= 0:
                        continue
                    if not first:
                        minutes -= line["changeover_minutes"]
                    if minutes <= 0:
                        break
                    uph = rate[(sku, code)]
                    run_minutes = min(minutes, math.ceil(need / uph * 60))
                    planned = run_minutes * uph // 60
                    if planned <= 0:
                        continue
                    minutes, first = minutes - run_minutes, False
                    if shock[sku][d] < 1:  # supply disruption: most of the run is lost
                        downtime = round(run_minutes * (1 - shock[sku][d]))
                    else:
                        downtime = min(run_minutes, int(rng.poisson(12)))
                    actual = int(planned * (run_minutes - downtime) / run_minutes * rng.uniform(0.95, 1.0))
                    scrap = int(rng.binomial(actual, SCRAP_RATE[category[sku]]))
                    produced[sku] = actual - scrap
                    runs.append(dict(date=dates[d], production_line_id=ref.line_id[code],
                                     product_id=ref.product_id[sku], planned_units=planned, actual_units=actual,
                                     downtime_minutes=downtime, scrap_units=scrap))
            for sku in active:
                key = (sku, code)
                on_hand[key] = max(0, on_hand[key] + in_transit[key] - int(shipped[key][d]))
                in_transit[key] = produced.get(sku, 0)
                inventory.append(dict(date=dates[d], product_id=ref.product_id[sku], plant_id=ref.plant_id[plant],
                                      on_hand_units=on_hand[key], in_transit_units=in_transit[key],
                                      safety_stock_units=math.ceil(SAFETY_DAYS * signals[sku])))

    for i, row in enumerate(runs, start=1):
        row["id"] = i
    inventory.sort(key=lambda r: (r["date"], r["product_id"], r["plant_id"]))
    for i, row in enumerate(inventory, start=1):
        row["id"] = i
    return runs, inventory


# --------------------------------------------------------------------------- calendar


def _effect_note(gt: dict, key: str) -> str:
    parts = []
    for category, windows in gt["holiday_effects"].get(key, {}).items():
        spans = ", ".join(f"x{m:g} on day {a:+d}" if a == b else f"x{m:g} on days {a:+d}..{b:+d}"
                          for a, b, m in windows)
        parts.append(f"{category} {spans}")
    return "; ".join(parts) or "no modelled demand effect"


def build_calendar(gt: dict, ref: Reference, start: date, end: date, shutdowns: list[dict]) -> list[dict]:
    horizon = end + timedelta(days=CALENDAR_HORIZON_DAYS)
    events = []
    for h in gt["holidays"]:
        day = date.fromisoformat(h["date"])
        if start <= day <= horizon:
            events.append(dict(date=day, end_date=day, name=h["name"], event_type=h["event_type"],
                               region_id=ref.region_id[h["region_code"]] if h["region_code"] else None,
                               product_id=None, plant_id=None,
                               impact_note=f"{_effect_note(gt, h['key'])} | source: {h['source']}"))
    for sku, p in gt["products"].items():
        for promo in p["promotions"]:
            events.append(dict(date=date.fromisoformat(promo["start"]), end_date=date.fromisoformat(promo["end"]),
                               name=f"{p['name']} promotion", event_type="promotion", region_id=None,
                               product_id=ref.product_id[sku], plant_id=None,
                               impact_note=f"Demand x{promo['lift']:g}; {promo['discount_pct']:.0%} off promotional lines"))
    for window in shutdowns:
        events.append(dict(date=window["start"], end_date=window["end"], name=f"{window['plant']} {window['name']}",
                           event_type="plant_shutdown", region_id=None, product_id=None,
                           plant_id=ref.plant_id[window["plant"]], impact_note="No production on this plant's lines"))
    for name, city, month_day, days in TRADE_SHOWS:
        month, day = (int(x) for x in month_day.split("-"))
        for year in range(start.year, horizon.year + 1):
            first = date(year, month, day)
            if start <= first <= horizon:
                events.append(dict(date=first, end_date=first + timedelta(days=days - 1), name=name,
                                   event_type="trade_show", region_id=ref.region_id[city], product_id=None,
                                   plant_id=None, impact_note="Illustrative dates; no modelled demand effect"))
    events.sort(key=lambda e: (e["date"], e["event_type"], e["name"]))
    for i, event in enumerate(events, start=1):
        event["id"] = i
    return events


# --------------------------------------------------------------------------- database


def wipe_all(session: Session) -> None:
    tables = [t.name for t in Base.metadata.sorted_tables]
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE"))
    else:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())


def _sync_pg_sequences(session: Session) -> None:
    """Rows were inserted with explicit ids; move each id sequence past them."""
    if session.get_bind().dialect.name != "postgresql":
        return
    for table in Base.metadata.sorted_tables:
        session.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table.name}), 0) + 1, false)"))


def bulk_insert(session: Session, model: type, rows: list[dict]) -> None:
    """executemany in chunks via Core insert - no per-row ORM objects."""
    for i in range(0, len(rows), INSERT_CHUNK):
        session.execute(insert(model.__table__), rows[i:i + INSERT_CHUNK])


# --------------------------------------------------------------------------- entry point


def generate(session: Session, *, seed: int = 42, end_date: date | None = None, years: int = 3,
             ground_truth_path: Path = GROUND_TRUTH_PATH) -> SeedReport:
    started = time.perf_counter()
    start, end = window_for(end_date or utc_yesterday(), years)
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    gt = build_ground_truth(seed, start, end)
    write_ground_truth(gt, ground_truth_path)

    ref = build_reference(end)
    lines, daily_units = sample_order_lines(gt, ref, seed)
    ref.rows[SalesOrder], ref.rows[SalesOrderLine] = build_orders(gt, lines, dates)
    shutdowns = plant_shutdowns(gt, start, end)
    ref.rows[ProductionRun], ref.rows[Inventory] = simulate_production(gt, ref, daily_units, dates, shutdowns, seed)
    ref.rows[CalendarEvent] = build_calendar(gt, ref, start, end, shutdowns)

    wipe_all(session)
    for model in LOAD_ORDER:
        bulk_insert(session, model, ref.rows.get(model, []))
    _sync_pg_sequences(session)
    rebuild_daily_sales(session)
    session.commit()

    counts = {t.name: session.scalar(select(func.count()).select_from(t)) for t in Base.metadata.sorted_tables}
    product_days = sum((end - max(start, launch_date(spec, end))).days + 1 for spec in PRODUCTS)
    return SeedReport(
        seed=seed, start=start, end=end, seconds=time.perf_counter() - started,
        ground_truth_path=ground_truth_path, table_counts=counts, product_days=product_days,
        daily_sales_rows=counts[DailySales.__tablename__],
        product_table=_product_table(session, daily_units, dates), holidays=gt["holidays"],
        warnings=[f"No hardcoded festival dates for {year}; Dhanteras is missing that year"
                  for year in uncovered_hardcoded_years(start, end)],
    )


def _product_table(session: Session, daily_units: dict[str, np.ndarray], dates: list[date]) -> pd.DataFrame:
    stats = session.execute(
        select(Product.sku, Product.category, func.min(DailySales.date), func.max(DailySales.date),
               func.count(func.distinct(DailySales.date)), func.sum(DailySales.units),
               func.sum(DailySales.revenue_minor))
        .join(DailySales, DailySales.product_id == Product.id)
        .group_by(Product.sku, Product.category)
        .order_by(Product.sku)
    ).all()
    table = pd.DataFrame(stats, columns=["sku", "category", "first_sale", "last_sale", "days_with_sales",
                                         "units", "revenue_minor"])
    index = pd.DatetimeIndex(dates)
    table["peak_month"] = [pd.Series(daily_units[sku], index=index).groupby(index.month).sum().idxmax()
                           for sku in table["sku"]]
    table["peak_month"] = table["peak_month"].map(lambda m: date(2000, m, 1).strftime("%b"))
    return table


def format_report(report: SeedReport) -> str:
    out = [
        f"Meridian seed: seed={report.seed}, history {report.start} .. {report.end} "
        f"({(report.end - report.start).days + 1} days), finished in {report.seconds:.1f}s",
        f"Ground truth written to {report.ground_truth_path}",
        "",
        f"{'Table':<22}{'Rows':>10}",
    ]
    out += [f"{name:<22}{count:>10,}" for name, count in report.table_counts.items()]
    out += [
        "",
        f"Product-days of history (12 SKUs x days since launch or window start): {report.product_days:>9,}",
        f"daily_sales rows (one per date x product x city x channel):             {report.daily_sales_rows:>9,}",
        "  (daily_sales has more rows than product-days because each product-day is split by city and channel)",
        "",
        f"{'SKU':<14}{'Category':<23}{'First sale':<12}{'Last sale':<12}{'Days':>6}{'Units':>11}"
        f"{'Revenue INR':>16}  Peak month",
    ]
    for row in report.product_table.itertuples():
        out.append(f"{row.sku:<14}{row.category:<23}{row.first_sale!s:<12}{row.last_sale!s:<12}"
                   f"{row.days_with_sales:>6,}{row.units:>11,}{row.revenue_minor / 100:>16,.0f}  {row.peak_month}")

    diwali_by_year = {h["date"][:4]: h["date"] for h in report.holidays if h["key"] == "diwali"}
    out += ["", f"Holiday & festival dates used ({len(report.holidays)}; window -30 days .. +26 weeks):",
            f"{'Date':<12}{'Dow':<5}{'Key':<18}{'Name':<34}{'Type':<16}{'Region':<8}Source"]
    for h in report.holidays:
        day = date.fromisoformat(h["date"])
        note = ""
        if h["source"] == HARDCODED_SOURCE and h["date"][:4] in diwali_by_year:
            gap = (date.fromisoformat(diwali_by_year[h["date"][:4]]) - day).days
            note = f"  <- {gap} day(s) before package Diwali {diwali_by_year[h['date'][:4]]}"
        out.append(f"{h['date']:<12}{day:%a}  {h['key']:<18}{h['name'][:33]:<34}{h['event_type']:<16}"
                   f"{h['region_code'] or '-':<8}{h['source']}{note}")
    out += [f"WARNING: {w}" for w in report.warnings]
    return "\n".join(out)
