"""Recompute every analytics figure in pandas and compare it with the running API.

    make run                    # in another terminal: the API on http://127.0.0.1:8000
    make verify-analytics       # VERIFY_ARGS="--base-url ... --email ... --password ..."

Independent by construction: the tables are read straight into pandas (no app query
code, no rollup tables), the rules are re-implemented here from their written
definitions (CLAUDE.md, "Sales analytics"), and the API is called over HTTP like the
frontend does. Orders are recomputed from sales_orders / sales_order_lines; everything
else from daily_sales. The seasonal check compares each seasonal SKU's peak month with
the peak of expected demand from app/seed/ground_truth.py:expected_cell_demand.

Exit status 0 when every figure matches, 1 otherwise.
"""

import argparse
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

import httpx
import numpy as np
import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402  (database URL only)
from app.db import normalize_url  # noqa: E402
from app.seed.ground_truth import _dates, expected_cell_demand, load_ground_truth  # noqa: E402
from app.seed.users import DEMO_PASSWORD, DEMO_USERS  # noqa: E402

YEAR_SHIFT = 364
COMBOS = [
    dict(name="52 weeks, all, vs last year", date_from="2025-10-10", date_to="2026-10-08"),
    dict(name="13 weeks, Maharashtra (Mumbai + Pune), vs last year", date_from="2026-07-10",
         date_to="2026-10-08", regions=["IN-MH"]),
    dict(name="13 weeks, ecommerce, vs last year", date_from="2026-07-10", date_to="2026-10-08",
         channels=["ecommerce"]),
    dict(name="4 weeks, two SKUs, by day, vs previous period", date_from="2026-09-11", date_to="2026-10-08",
         skus=["FDS-SWT-500", "KIT-MXG-750"], granularity="day", comparison="previous_period"),
    dict(name="Year to date, Bengaluru, by month, vs last year", date_from="2026-01-01", date_to="2026-10-08",
         regions=["IN-KA-BLR"], granularity="month"),
]


# --------------------------------------------------------------------------- comparison bookkeeping


@dataclass
class Report:
    checked: Counter = field(default_factory=Counter)
    failures: list[str] = field(default_factory=list)

    def same(self, where: str, got, want) -> None:
        self.checked[where.split(":")[0]] += 1
        if isinstance(want, float) or isinstance(got, float):
            ok = got is not None and want is not None and math.isclose(got, want, rel_tol=1e-9, abs_tol=5e-5)
        else:
            ok = got == want
        if not ok:
            self.failures.append(f"{where}: API {got!r} != pandas {want!r}")


# --------------------------------------------------------------------------- data


class Data:
    def __init__(self, engine: sa.Engine):
        read = lambda sql, **kw: pd.read_sql(sa.text(sql), engine, **kw)  # noqa: E731
        self.ds = read("select date, product_id, region_id, channel, units, revenue_minor from daily_sales",
                       parse_dates=["date"])
        self.products = read("select id, sku, name, category, unit_cost_minor, is_active, launched_on from products",
                             parse_dates=["launched_on"]).set_index("id")
        self.regions = read("select id, code, name, level, parent_region_id from regions").set_index("id")
        self.orders = read("select id, order_date, region_id, channel from sales_orders", parse_dates=["order_date"])
        self.lines = read("select sales_order_id, product_id from sales_order_lines")
        self.events = read("select date, end_date, name, event_type, region_id, product_id, plant_id from "
                           "calendar_events", parse_dates=["date", "end_date"])
        self.capable_plants = read("select pl.plant_id, lc.product_id from line_capabilities lc join production_lines "
                                   "pl on pl.id = lc.production_line_id")
        self.ds["cost"] = self.ds.units * self.ds.product_id.map(self.products.unit_cost_minor)
        self.first, self.last = self.ds.date.min(), self.ds.date.max()

    def descendants(self, codes: list[str]) -> set[int]:
        by_code = {row.code: rid for rid, row in self.regions.iterrows()}
        out, stack = set(), [by_code[c] for c in codes]
        while stack:
            rid = stack.pop()
            if rid not in out:
                out.add(rid)
                stack += list(self.regions.index[self.regions.parent_region_id == rid])
        return out


@dataclass
class Scope:
    period: tuple[pd.Timestamp, pd.Timestamp]
    comparison: tuple[pd.Timestamp, pd.Timestamp]
    shift: int
    complete: bool
    product_ids: set[int] | None
    region_ids: set[int] | None
    channels: set[str] | None
    granularity: str


def scope_for(data: Data, combo: dict) -> Scope:
    frm, to = pd.Timestamp(combo["date_from"]), pd.Timestamp(combo["date_to"])
    frm, to = max(frm, data.first), min(to, data.last)
    days = (to - frm).days + 1
    shift = YEAR_SHIFT if combo.get("comparison", "same_period_last_year") == "same_period_last_year" else days
    cfrm, cto = frm - pd.Timedelta(days=shift), to - pd.Timedelta(days=shift)
    skus = combo.get("skus")
    return Scope(
        period=(frm, to), comparison=(cfrm, cto), shift=shift,
        complete=cfrm >= data.first and cto <= data.last,
        product_ids=set(data.products.index[data.products.sku.isin(skus)]) if skus else None,
        region_ids=data.descendants(combo["regions"]) if combo.get("regions") else None,
        channels=set(combo["channels"]) if combo.get("channels") else None,
        granularity=combo.get("granularity", "week"),
    )


def rows(data: Data, s: Scope, window: tuple[pd.Timestamp, pd.Timestamp]) -> pd.DataFrame:
    d = data.ds[(data.ds.date >= window[0]) & (data.ds.date <= window[1])]
    if s.product_ids is not None:
        d = d[d.product_id.isin(s.product_ids)]
    if s.region_ids is not None:
        d = d[d.region_id.isin(s.region_ids)]
    if s.channels is not None:
        d = d[d.channel.isin(s.channels)]
    return d


def change(cur, base, complete):
    if not complete or cur is None or base is None or base <= 0:
        return None
    return (cur - base) / base


def bucket(dates: pd.Series, granularity: str) -> pd.Series:
    if granularity == "day":
        return dates
    if granularity == "week":
        return dates - pd.to_timedelta(dates.dt.weekday, unit="D")
    return dates.dt.to_period("M").dt.to_timestamp()


def bucket_end(start: pd.Timestamp, granularity: str) -> pd.Timestamp:
    if granularity == "day":
        return start
    if granularity == "week":
        return start + pd.Timedelta(days=6)
    return start + pd.offsets.MonthEnd(0)


# --------------------------------------------------------------------------- checks


def check_summary(api, data, s, combo, report):
    body = api("analytics/summary", combo)
    cur, base = rows(data, s, s.period), rows(data, s, s.comparison)

    def orders_in(window):
        o = data.orders[(data.orders.order_date >= window[0]) & (data.orders.order_date <= window[1])]
        if s.region_ids is not None:
            o = o[o.region_id.isin(s.region_ids)]
        if s.channels is not None:
            o = o[o.channel.isin(s.channels)]
        if s.product_ids is not None:
            o = o[o.id.isin(data.lines.sales_order_id[data.lines.product_id.isin(s.product_ids)])]
        return o.id.nunique()

    for key, frame, window in (("current", cur, s.period), ("baseline", base, s.comparison)):
        units, revenue, cost = int(frame.units.sum()), int(frame.revenue_minor.sum()), int(frame.cost.sum())
        want = dict(revenue_minor=revenue, units=units, orders=orders_in(window), gross_margin_minor=revenue - cost,
                    average_selling_price_minor=round(revenue / units) if units else None,
                    margin_rate=(revenue - cost) / revenue if revenue else None)
        for field_name, value in want.items():
            report.same(f"summary:{key}.{field_name}", body[key][field_name], value)
    c, b = body["current"], body["baseline"]
    for name, (x, y) in dict(revenue=("revenue_minor",) * 2, units=("units",) * 2, orders=("orders",) * 2,
                             gross_margin=("gross_margin_minor",) * 2,
                             average_selling_price=("average_selling_price_minor",) * 2).items():
        report.same(f"summary:change.{name}", body["change"][name], change(c[x], b[y], s.complete))
    report.same("summary:comparison.date_from", body["comparison"]["date_from"], s.comparison[0].date().isoformat())
    report.same("summary:comparison.complete", body["comparison"]["complete"], s.complete)


def check_timeseries(api, data, s, combo, report):
    body = api("analytics/timeseries", combo)
    g = s.granularity
    cur = rows(data, s, s.period).assign(b=lambda f: bucket(f.date, g))
    base = rows(data, s, s.comparison).assign(b=lambda f: bucket(f.date + pd.Timedelta(days=s.shift), g))
    cur_sum = cur.groupby("b")[["units", "revenue_minor"]].sum()
    base_sum = base.groupby("b")[["units", "revenue_minor"]].sum()
    starts = sorted(set(bucket(pd.Series(pd.date_range(*s.period)), g)))
    report.same("timeseries:bucket count", len(body["points"]), len(starts))
    for point, start in zip(body["points"], starts, strict=False):
        end = bucket_end(start, g)
        lo, hi = max(start, s.period[0], data.first), min(end, s.period[1], data.last)
        covered = max(0, (hi - lo).days + 1)
        where = f"timeseries:{start.date()}"
        report.same(f"{where}.period_start", point["period_start"], start.date().isoformat())
        report.same(f"{where}.days_covered", point["days_covered"], covered)
        report.same(f"{where}.is_partial", point["is_partial"], covered < (end - start).days + 1)
        for key, frame, col in (("units", cur_sum, "units"), ("revenue_minor", cur_sum, "revenue_minor"),
                                ("baseline_units", base_sum, "units"),
                                ("baseline_revenue_minor", base_sum, "revenue_minor")):
            want = int(frame[col].get(start, 0))
            report.same(f"{where}.{key}", point[key], want)


def xyz_weeks(data: Data, date_to: pd.Timestamp) -> list[pd.Timestamp]:
    end = min(date_to, data.last)
    last_sunday = end - pd.Timedelta(days=(end.weekday() + 1) % 7)
    first = last_sunday - pd.Timedelta(days=52 * 7 - 1)
    history_monday = data.first + pd.Timedelta(days=(7 - data.first.weekday()) % 7)
    return list(pd.date_range(max(first, history_monday), last_sunday - pd.Timedelta(days=6), freq="7D"))


def check_products(api, data, s, combo, report):
    body = api("analytics/products", combo)
    cur, base = rows(data, s, s.period), rows(data, s, s.comparison)
    rev, units, cost = (cur.groupby("product_id")[c].sum() for c in ("revenue_minor", "units", "cost"))
    b_rev = base.groupby("product_id").revenue_minor.sum()
    catalogue = data.products if s.product_ids is None else data.products.loc[sorted(s.product_ids)]
    with_sales = set(cur.product_id) | set(base.product_id)
    listed = catalogue[catalogue.is_active.astype(bool) | catalogue.index.isin(with_sales)]
    revenue = {p.sku: int(rev.get(pid, 0)) for pid, p in listed.iterrows()}
    total = sum(revenue.values())
    ranking = {sku: i for i, sku in enumerate(sorted(revenue, key=lambda k: (-revenue[k], k)), start=1)}
    abc, above = {}, 0.0
    for sku in sorted(revenue, key=lambda k: (-revenue[k], k)):
        abc[sku] = None if total == 0 else "A" if above < 0.8 else "B" if above < 0.95 else "C"
        above += revenue[sku] / total if total else 0

    weeks = xyz_weeks(data, s.period[1])
    w_rows = rows(data, s, (weeks[0], weeks[-1] + pd.Timedelta(days=6))).assign(
        w=lambda f: f.date - pd.to_timedelta(f.date.dt.weekday, unit="D"))
    weekly = w_rows.groupby(["product_id", "w"]).units.sum()
    by_sku = {r["sku"]: r for r in body["rows"]}
    report.same("products:row set", sorted(by_sku), sorted(revenue))
    for pid, p in listed.iterrows():
        r = by_sku.get(p.sku)
        if r is None:
            continue
        since_launch = [w for w in weeks if w >= p.launched_on]
        series = np.array([weekly.get((pid, w), 0) for w in since_launch], dtype=float)
        cv = series.std(ddof=1) / series.mean() if len(series) >= 13 and series.mean() > 0 else None
        xyz = None if cv is None else "X" if cv < 0.5 else "Y" if cv <= 1.0 else "Z"
        want = dict(rank=ranking[p.sku], revenue_minor=revenue[p.sku], units=int(units.get(pid, 0)),
                    gross_margin_minor=revenue[p.sku] - int(cost.get(pid, 0)),
                    share=revenue[p.sku] / total if total else 0.0, baseline_revenue_minor=int(b_rev.get(pid, 0)),
                    growth=change(revenue[p.sku], int(b_rev.get(pid, 0)), s.complete), abc=abc[p.sku], xyz=xyz,
                    xyz_cv=float(round(cv, 4)) if cv is not None else None, xyz_weeks=len(series),
                    sparkline=[int(weekly.get((pid, w), 0)) for w in weeks[-13:]])
        for key, value in want.items():
            report.same(f"products:{p.sku}.{key}", r[key], value)


def check_regions(api, data, s, combo, report):
    regions = data.regions
    state_of = {rid: (rid if row.level == "state" else row.parent_region_id if row.level == "city" else None)
                for rid, row in regions.iterrows()}
    cur, base = rows(data, s, s.period), rows(data, s, s.comparison)

    def compare(body, key_fn, label):
        c = cur.assign(k=cur.region_id.map(key_fn)).dropna(subset=["k"]).groupby("k").revenue_minor.sum()
        b = base.assign(k=base.region_id.map(key_fn)).dropna(subset=["k"]).groupby("k").revenue_minor.sum()
        keys = sorted((set(c.index) | set(b.index)), key=lambda k: (-int(c.get(k, 0)), regions.loc[k].code))
        report.same(f"regions:{label} codes", [r["code"] for r in body["rows"]], [regions.loc[k].code for k in keys])
        total = int(c.sum())
        for row, k in zip(body["rows"], keys, strict=False):
            report.same(f"regions:{label}.{row['code']}.revenue", row["revenue_minor"], int(c.get(k, 0)))
            report.same(f"regions:{label}.{row['code']}.share", row["share"], int(c.get(k, 0)) / total if total else 0.0)
            report.same(f"regions:{label}.{row['code']}.growth", row["growth"],
                        change(int(c.get(k, 0)), int(b.get(k, 0)), s.complete))

    compare(api("analytics/regions", combo), lambda rid: state_of.get(rid), "states")
    for state_code in sorted({regions.loc[state_of[rid]].code for rid in cur.region_id.unique() if state_of.get(rid)}):
        state_id = regions.index[regions.code == state_code][0]
        body = api("analytics/regions", combo, level="city", parent=state_code)
        compare(body, lambda rid, sid=state_id: rid if regions.loc[rid].level == "city"
                and regions.loc[rid].parent_region_id == sid else None, f"cities of {state_code}")


def check_channels(api, data, s, combo, report):
    body = api("analytics/channels", combo)
    c = rows(data, s, s.period).groupby("channel").revenue_minor.sum()
    b = rows(data, s, s.comparison).groupby("channel").revenue_minor.sum()
    total, b_total = int(c.sum()), int(b.sum())
    by = {r["channel"]: r for r in body["rows"]}
    report.same("channels:set", sorted(by), sorted(set(c.index) | set(b.index)))
    for ch, r in by.items():
        report.same(f"channels:{ch}.revenue", r["revenue_minor"], int(c.get(ch, 0)))
        report.same(f"channels:{ch}.share", r["share"], int(c.get(ch, 0)) / total if total else 0.0)
        report.same(f"channels:{ch}.baseline_share", r["baseline_share"],
                    int(b.get(ch, 0)) / b_total if s.complete and b_total else None)


def check_product_events(api, data, report, sku: str):
    body = api(f"products/{sku}", {})
    pid = data.products.index[data.products.sku == sku][0]
    frm, to = pd.Timestamp(body["events_from"]), pd.Timestamp(body["events_to"])
    e = data.events[(data.events.date <= to) & (data.events.end_date >= frm)]
    plants = set(data.capable_plants.plant_id[data.capable_plants.product_id == pid])
    keep = ((e.event_type == "promotion") & (e.product_id == pid)) | e.event_type.isin(["public_holiday", "festival"]) \
        | ((e.event_type == "plant_shutdown") & e.plant_id.isin(plants))
    want = sorted((d.date().isoformat(), n) for d, n in zip(e[keep].date, e[keep].name, strict=True))
    got = sorted((ev["date"], ev["name"]) for ev in body["events"])
    report.same(f"product detail:{sku} events", got, want)


# Season windows (months) per seasonal SKU: Diwali-linked products peak in autumn, cooling
# and pumps before the monsoon. A season counts only when it lies wholly inside the history.
SEASONS = {"FDS-GFB-1KG": (9, 11), "FDS-SWT-500": (9, 11), "KIT-MXG-750": (9, 11),
           "COL-ACL-70": (3, 6), "COL-TFN-400": (3, 6), "IND-PMP-05": (3, 6)}
# Adjacent months whose expected demand differs by less than this are a tie that sampling
# noise decides (e.g. a peak centred on 1 May splits April and May almost evenly).
TIE = 0.03


def check_seasonal_peaks(api, data, report) -> list[str]:
    """Each season's peak month: actual units (API, monthly) vs expected demand (ground truth)."""
    gt = load_ground_truth()
    dates = pd.DatetimeIndex(_dates(gt))
    lines = []
    for sku, (first_month, last_month) in SEASONS.items():
        body = api("analytics/timeseries", dict(date_from=data.first.date().isoformat(),
                                               date_to=data.last.date().isoformat(), skus=[sku],
                                               granularity="month"))
        actual = pd.Series({pd.Timestamp(p["period_start"]): p["units"] for p in body["points"]})
        _, mu = expected_cell_demand(gt, sku)
        expected = pd.Series(mu.sum(axis=1), index=dates).resample("MS").sum()
        for year in sorted(set(actual.index.year)):
            season_start = pd.Timestamp(year, first_month, 1)
            season_end = pd.Timestamp(year, last_month, 1) + pd.offsets.MonthEnd(0)
            if season_start < data.first or season_end > data.last:
                continue  # only seasons wholly inside the stored history
            months = list(pd.date_range(season_start, season_end, freq="MS"))
            a, e = actual.reindex(months, fill_value=0), expected.reindex(months, fill_value=0)
            a_peak, e_peak = a.idxmax(), e.idxmax()
            tie = a_peak != e_peak and e[a_peak] >= (1 - TIE) * e[e_peak]
            report.same(f"seasonal:{sku} {year} peak month", a_peak.strftime("%b") if not tie else e_peak.strftime("%b"),
                        e_peak.strftime("%b"))
            note = "" if a_peak == e_peak else (
                f"   tie: expected {a_peak:%b} is {e[a_peak] / e[e_peak]:.1%} of {e_peak:%b}" if tie else "   <-- differs")
            lines.append(f"  {sku:13s} {year} season: actual peak {a_peak:%b} ({int(a.max()):,} units), "
                         f"expected peak {e_peak:%b}{note}")
    return lines


# --------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default=DEMO_USERS[0][0])
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()

    engine = sa.create_engine(normalize_url(get_settings().database_url))
    data = Data(engine)
    http = httpx.Client(base_url=args.base_url + "/api/v1", timeout=60)

    def sign_in() -> None:
        login = http.post("/auth/login", json={"email": args.email, "password": args.password, "remember": False})
        login.raise_for_status()
        http.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    sign_in()

    def api(path: str, combo: dict, **extra) -> dict:
        params = {k: v for k, v in combo.items() if k != "name"} | extra
        response = http.get("/" + path, params=params)
        if response.status_code == 401:
            # The access token lives 15 minutes; a slow run (a throttled laptop) outlives it.
            sign_in()
            response = http.get("/" + path, params=params)
        response.raise_for_status()
        return response.json()

    report = Report()
    for combo in COMBOS:
        s = scope_for(data, combo)
        before = sum(report.checked.values())
        for check in (check_summary, check_timeseries, check_products, check_regions, check_channels):
            check(api, data, s, combo, report)
        print(f"{combo['name']}: {sum(report.checked.values()) - before:,} figures")
    for sku in ("FDS-GFB-1KG", "COL-ACL-70"):
        check_product_events(api, data, report, sku)
    peaks = check_seasonal_peaks(api, data, report)

    print("\nFigures compared, by endpoint:")
    for name, count in sorted(report.checked.items()):
        print(f"  {name:16s} {count:6,}")
    print("\nSeasonal peaks (seasons wholly inside the history, 9 Oct 2023 - 8 Oct 2026):")
    print("\n".join(peaks))
    if report.failures:
        print(f"\n{len(report.failures)} MISMATCH(ES):")
        print("\n".join("  " + f for f in report.failures[:60]))
        return 1
    print(f"\nAll {sum(report.checked.values()):,} figures match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
