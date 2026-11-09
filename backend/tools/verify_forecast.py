"""Recompute every forecast-page figure from the tables and compare it with the running API.

    make run                    # in another terminal: the API on http://127.0.0.1:8000
    make verify-forecast        # VERIFY_ARGS="--base-url ... --email ... --password ..."

Independent by construction, like verify_analytics.py: the tables are read straight into
pandas (no app query code; sales from daily_sales, never the weekly_sales rollup), the
rules are re-implemented here from their written definitions (CLAUDE.md, phase 5a and 5b),
and the API is called over HTTP like the frontend does. What the three forecast pages
show, endpoint by endpoint:

  /forecasts/overview         per-SKU sums of p50, the same weeks last year, change, skill,
                              ABC (revenue, 52 weeks to the cutoff), forecastability, run header
  /forecasts/{sku}?horizon    every stored week and interval, for 4, 13 and 26 weeks
  /forecasts/{sku}/csv        equal to the JSON for the same SKU and horizon
  /forecasts/{sku}?view       the allocation by state and by channel (shares, rounding)
  /forecasts/{sku}/context    actuals, horizon events, held-out accuracy, past forecasts
  /backtest/leaderboard       pooled WAPE, skill, median per-SKU skill, coverage, the oracle floor
  /forecasts/oracle-test      the stored forward oracle test

Two further checks on the stored data itself:
  * the stored past forecasts (backtest_forecasts) reproduce backtest_metrics' per-SKU
    held-out champion scores at horizons 1 and 4 (all weeks), and their actuals equal the
    weekly sums of daily_sales;
  * the Gift Box's stored forecast peaks in the Diwali 2026 weeks (the weeks holding the 10
    days before Diwali), and Diwali is among the context's horizon events in its week.

Exit status 0 when every figure matches, 1 otherwise.
"""

import argparse
import csv
import io
import math
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402  (database URL only)
from app.db import normalize_url  # noqa: E402
from app.seed.users import DEMO_PASSWORD, DEMO_USERS  # noqa: E402

YEAR_SHIFT = timedelta(days=364)
HORIZONS = (4, 13, 26)
SHARE_WEEKS = 13
ABC_WEEKS = 52
ABC_A, ABC_B = 0.80, 0.95
GIFT_BOX = "FDS-GFB-1KG"
DIWALI_LEAD_DAYS = 10


@dataclass
class Report:
    checked: Counter = field(default_factory=Counter)
    failures: list[str] = field(default_factory=list)

    def same(self, where: str, got, want, exact: bool = False) -> None:
        self.checked[where.split(":")[0]] += 1
        if not exact and (isinstance(want, float) or isinstance(got, float)):
            ok = got is not None and want is not None and math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-12)
        else:
            ok = got == want
        if not ok:
            self.failures.append(f"{where}: API {got!r} != tables {want!r}")


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


class Data:
    def __init__(self, engine: sa.Engine):
        def read(sql: str, **kw) -> pd.DataFrame:
            return pd.read_sql(sa.text(sql), engine, **kw)

        runs = read("select id, kind, data_end_date, training_cutoff, params from forecast_runs order by id")
        runs["params"] = runs["params"].map(lambda p: p if isinstance(p, dict) else __import__("json").loads(p))
        production = runs[runs["kind"] == "production"].iloc[-1]
        self.run_id = int(production["id"])
        self.params = production["params"]
        self.data_end = _date(production["data_end_date"])
        self.cutoff = _date(production["training_cutoff"])
        backtest_id = self.params.get("backtest_run_id") or int(runs[runs["kind"] == "backtest"].iloc[-1]["id"])
        self.backtest_id = int(backtest_id)
        self.backtest_params = runs.set_index("id").loc[self.backtest_id, "params"]

        self.products = read("select id, sku, name, launched_on from products")
        self.products["launched_on"] = self.products["launched_on"].map(_date)
        self.sku_of = dict(zip(self.products["id"], self.products["sku"], strict=True))
        self.forecasts = read(f"select product_id, week, horizon, model, p50, lo80, hi80, lo95, hi95 "
                              f"from forecasts where run_id = {self.run_id}")
        self.forecasts["week"] = self.forecasts["week"].map(_date)
        self.forecasts["sku"] = self.forecasts["product_id"].map(self.sku_of)
        self.metrics = read(f"select model, product_id, window, shocks, horizon, n_weeks, wape, bias, mase, "
                            f"coverage_80, coverage_95 from backtest_metrics where run_id = {self.backtest_id}")
        self.metrics["sku"] = self.metrics["product_id"].map(self.sku_of)
        self.past = read(f"select product_id, origin, horizon, week, model, actual, p50, lo80, hi80, lo95, hi95 "
                         f"from backtest_forecasts where run_id = {self.backtest_id}")
        for c in ("origin", "week"):
            self.past[c] = self.past[c].map(_date)
        self.past["sku"] = self.past["product_id"].map(self.sku_of)

        daily = read("select date, product_id, region_id, channel, units, revenue_minor from daily_sales")
        daily["date"] = daily["date"].map(_date)
        daily["week"] = daily["date"].map(monday)
        daily["sku"] = daily["product_id"].map(self.sku_of)
        self.daily = daily
        self.first_day = daily["date"].min()
        self.weekly = daily.groupby(["sku", "week"])["units"].sum().astype(int).to_dict()
        regions = read("select id, code, name, level, parent_region_id from regions").set_index("id")
        state_id = {i: (i if r.level == "state" else r.parent_region_id) for i, r in regions.iterrows()}
        self.daily["state"] = self.daily["region_id"].map(lambda i: regions.loc[state_id[i], "code"])
        self.state_name = {r["code"]: r["name"] for _, r in regions.iterrows() if r["level"] == "state"}
        self.events = read("select e.date, e.end_date, e.name, e.event_type, r.code as region_code "
                           "from calendar_events e left join regions r on r.id = e.region_id")
        for c in ("date", "end_date"):
            self.events[c] = self.events[c].map(_date)

    def held_out(self, model: str, sku: str | None, horizon: int | None = None, shocks: str = "included"):
        m = self.metrics
        rows = m[(m["model"] == model) & (m["window"] == "held_out") & (m["shocks"] == shocks)
                 & (m["sku"].isna() if sku is None else m["sku"] == sku)
                 & (m["horizon"].isna() if horizon is None else m["horizon"] == horizon)]
        return None if rows.empty else rows.iloc[0]


def _date(value) -> date:
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    return pd.Timestamp(value).date()


def _none(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def skill(model_wape, base_wape):
    model_wape, base_wape = _none(model_wape), _none(base_wape)
    return None if model_wape is None or not base_wape else 1 - model_wape / base_wape


def largest_remainder(total: int, shares: list[float]) -> list[int]:
    raw = [total * s for s in shares]
    parts = [int(r) for r in raw]
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - parts[i]), i))
    for i in order[: total - sum(parts)]:
        parts[i] += 1
    return parts


# --------------------------------------------------------------------------- checks


def check_overview(api, d: Data, report: Report) -> None:
    body = api("forecasts/overview")
    report.same("overview: run id", body["run"]["id"], d.run_id)
    report.same("overview: data end", body["run"]["data_end_date"], d.data_end.isoformat())
    report.same("overview: training cutoff", body["run"]["training_cutoff"], d.cutoff.isoformat())
    report.same("overview: models", body["models"], sorted(d.forecasts["model"].unique()))
    report.same("overview: promotions", body["assumptions"]["promotions"], d.params["assumptions"]["promotions"])
    abc_from = d.cutoff - timedelta(weeks=ABC_WEEKS - 1)
    report.same("overview: abc window", (body["abc_from"], body["abc_to"]),
                (abc_from.isoformat(), (d.cutoff + timedelta(days=6)).isoformat()))
    window = d.daily[(d.daily["date"] >= abc_from) & (d.daily["date"] <= d.cutoff + timedelta(days=6))]
    revenue = window.groupby("sku")["revenue_minor"].sum().reindex(d.products["sku"], fill_value=0)
    total, above, abc = revenue.sum(), 0.0, {}
    for sku in sorted(revenue.index, key=lambda s: (-revenue[s], s)):
        abc[sku] = "A" if above < ABC_A else "B" if above < ABC_B else "C"
        above += revenue[sku] / total
    xyz = {r["sku"]: r for r in d.backtest_params.get("xyz", [])}
    rows = {r["sku"]: r for r in body["items"]}
    report.same("overview: skus", sorted(rows), sorted(d.forecasts["sku"].unique()))
    for sku, f in d.forecasts.groupby("sku"):
        row = rows.get(sku)
        if row is None:
            continue
        launch = monday(d.products.set_index("sku").loc[sku, "launched_on"])
        for h in (4, 13):
            weeks = f[f["horizon"] <= h]
            ahead = int(weeks["p50"].sum())
            before = [w - YEAR_SHIFT for w in weeks["week"]]
            if any(b < launch or b < monday(d.first_day) for b in before):
                past, change = None, None
            else:
                past = sum(d.weekly.get((sku, b), 0) for b in before)
                change = ahead / past - 1 if past else None
            report.same(f"overview: {sku} next_{h}", row[f"next_{h}"], ahead)
            report.same(f"overview: {sku} last_year_{h}", row[f"last_year_{h}"], past)
            report.same(f"overview: {sku} change_{h}", row[f"change_{h}"], change)
        champion, base = d.held_out("champion", sku), d.held_out("seasonal_naive", sku)
        report.same(f"overview: {sku} skill", row["skill"],
                    skill(champion["wape"] if champion is not None else None,
                          base["wape"] if base is not None else None))
        report.same(f"overview: {sku} abc", row["abc"], abc[sku])
        report.same(f"overview: {sku} forecastability", row["forecastability"], xyz.get(sku, {}).get("error_xyz"))
        report.same(f"overview: {sku} error_cv", row["error_cv"], xyz.get(sku, {}).get("error_cv"))
        report.same(f"overview: {sku} model", row["model"], f["model"].iloc[0])
        report.same(f"overview: {sku} short_history", row["short_history"],
                    sku in d.params.get("short_history_skus", []))


def check_forecast_and_csv(api, http_get, d: Data, report: Report) -> None:
    for sku, f in d.forecasts.groupby("sku"):
        for horizon in HORIZONS:
            body = api(f"forecasts/{sku}", horizon=horizon)
            want = [{"week": r.week.isoformat(), "horizon": int(r.horizon), "p50": int(r.p50), "lo80": int(r.lo80),
                     "hi80": int(r.hi80), "lo95": int(r.lo95), "hi95": int(r.hi95)}
                    for r in f[f["horizon"] <= horizon].sort_values("week").itertuples()]
            report.same(f"forecast: {sku} {horizon}w weeks", body["forecast"]["weeks"], want)
            text = http_get(f"forecasts/{sku}/csv", horizon=horizon)
            rows = list(csv.DictReader(io.StringIO(text)))
            as_csv = [{"sku": sku, "week": w["week"], "horizon": str(w["horizon"]), "model": body["forecast"]["model"],
                       **{k: str(w[k]) for k in ("p50", "lo80", "hi80", "lo95", "hi95")}}
                      for w in body["forecast"]["weeks"]]
            report.same(f"csv: {sku} {horizon}w equals the JSON", rows, as_csv)
            report.same(f"csv: {sku} {horizon}w equals the table", [r["p50"] for r in rows],
                        [str(w["p50"]) for w in want])


def check_allocation(api, d: Data, report: Report) -> None:
    share_from = d.cutoff - timedelta(weeks=SHARE_WEEKS - 1)
    window = d.daily[(d.daily["week"] >= share_from) & (d.daily["week"] <= d.cutoff)]
    for sku, f in d.forecasts.groupby("sku"):
        f = f.sort_values("week")
        for view, key in (("state", "state"), ("channel", "channel")):
            body = api(f"forecasts/{sku}", view=view, horizon=26)
            units = window[window["sku"] == sku].groupby(key)["units"].sum().sort_index()
            units = units[units > 0]
            shares = (units / units.sum()).tolist()
            split = [largest_remainder(int(p), shares) for p in f["p50"]]
            groups = body["allocation"]["groups"]
            report.same(f"allocation: {sku} {view} groups", [g["code"] for g in groups], list(units.index))
            for i, g in enumerate(groups):
                report.same(f"allocation: {sku} {view} {g['code']} share", g["share"], round(shares[i], 6))
                report.same(f"allocation: {sku} {view} {g['code']} p50", [w["p50"] for w in g["weeks"]],
                            [parts[i] for parts in split])
            if view == "state":
                report.same(f"allocation: {sku} state names", [g["name"] for g in groups],
                            [d.state_name[c] for c in units.index])


def check_context(api, d: Data, report: Report) -> None:
    for sku, f in d.forecasts.groupby("sku"):
        body = api(f"forecasts/{sku}/context")
        launch = monday(d.products.set_index("sku").loc[sku, "launched_on"])
        weeks = [d.cutoff - timedelta(weeks=k) for k in range(51, -1, -1)]
        report.same(f"context: {sku} actuals", body["actuals"],
                    [{"week": w.isoformat(), "units": None if w < launch else d.weekly.get((sku, w), 0)}
                     for w in weeks])
        first, last = f["week"].min(), f["week"].max() + timedelta(days=6)
        ev = d.events[d.events["event_type"].isin(["public_holiday", "festival"])
                      & (d.events["date"] >= first) & (d.events["date"] <= last)].sort_values(["date", "name"])
        report.same(f"context: {sku} events", [(e["date"], e["name"], e["week"], e["region_code"])
                                               for e in body["events"]],
                    [(r.date.isoformat(), r.name, monday(r.date).isoformat(), _none(r.region_code))
                     for r in ev.itertuples()])
        champion, base = d.held_out("champion", sku), d.held_out("seasonal_naive", sku)
        acc = body["accuracy"]
        report.same(f"context: {sku} accuracy model", acc["model"], d.backtest_params["champions"][sku])
        for k in ("wape", "bias", "coverage_80", "coverage_95"):
            report.same(f"context: {sku} {k}", acc[k], _none(champion[k]))
        report.same(f"context: {sku} n_weeks", acc["n_weeks"], int(champion["n_weeks"]))
        report.same(f"context: {sku} baseline_wape", acc["baseline_wape"], None if base is None else base["wape"])
        report.same(f"context: {sku} skill", acc["skill"],
                    skill(champion["wape"], None if base is None else base["wape"]))
        report.same(f"context: {sku} held_out_from", body["held_out_from"], d.backtest_params["held_out_start"])
        past = d.past[(d.past["sku"] == sku) & (d.past["horizon"] <= 4)].sort_values("week")
        report.same(f"context: {sku} past forecasts", body["past_forecasts"],
                    [{"week": r.week.isoformat(), "origin": r.origin.isoformat(), "weeks_before": int(r.horizon),
                      "actual": int(r.actual), "p50": float(r.p50), "lo80": float(r.lo80), "hi80": float(r.hi80)}
                     for r in past.itertuples()])


def check_stored_past_forecasts(d: Data, report: Report) -> None:
    """The stored past forecasts against the stored scores: the h1 and h4 metrics (all
    weeks) recomputed from backtest_forecasts must equal backtest_metrics, bit for bit."""
    held_out_from = date.fromisoformat(d.backtest_params["held_out_start"])
    report.same("past: rows", len(d.past), 13 * d.past["sku"].nunique())
    report.same("past: all in the held-out window", bool((d.past["week"] >= held_out_from).all()), True)
    report.same("past: one forecast per week", bool(not d.past.duplicated(["sku", "week"]).any()), True)
    for r in d.past.itertuples():
        report.same(f"past: {r.sku} {r.week} actual", int(r.actual), d.weekly.get((r.sku, r.week)))
    for sku, rows in d.past.groupby("sku"):
        for h in (1, 4):
            r = rows[rows["horizon"] == h]
            stored = d.held_out("champion", sku, h)
            y, p = r["actual"].to_numpy(dtype=float), r["p50"].to_numpy()
            total = float(np.sum(y))
            mine = {"n_weeks": len(r),
                    "wape": float(np.sum(np.abs(y - p))) / total,
                    "bias": float(np.sum(p - y)) / total,
                    "coverage_80": float(np.mean((y >= r["lo80"].to_numpy()) & (y <= r["hi80"].to_numpy()))),
                    "coverage_95": float(np.mean((y >= r["lo95"].to_numpy()) & (y <= r["hi95"].to_numpy())))}
            for k, v in mine.items():
                report.same(f"past: {sku} h{h} {k} reproduces backtest_metrics", v,
                            int(stored[k]) if k == "n_weeks" else float(stored[k]), exact=True)


def check_leaderboard(api, d: Data, report: Report) -> None:
    body = api("backtest/leaderboard", window="held_out", shocks="included")
    headline = d.backtest_params["headline_skus"]
    report.same("leaderboard: headline skus", body["headline_skus"], headline)
    m = d.metrics
    pooled = m[(m["window"] == "held_out") & (m["shocks"] == "included") & m["sku"].isna() & m["horizon"].isna()]
    base = pooled[pooled["model"] == "seasonal_naive"].iloc[0]["wape"]
    rows = {r["model"]: r for r in body["models"]}
    report.same("leaderboard: models", sorted(rows), sorted(pooled["model"]))
    for r in pooled.itertuples():
        row = rows[r.model]
        report.same(f"leaderboard: {r.model} wape", row["wape"], r.wape)
        report.same(f"leaderboard: {r.model} coverage_80", row["coverage_80"], _none(r.coverage_80))
        report.same(f"leaderboard: {r.model} n_weeks", row["n_weeks"], int(r.n_weeks))
        report.same(f"leaderboard: {r.model} skill", row["skill"],
                    None if r.model == "seasonal_naive" else skill(r.wape, base))
        per_sku = [skill(d.held_out(r.model, s)["wape"], d.held_out("seasonal_naive", s)["wape"]) for s in headline
                   if d.held_out(r.model, s) is not None and d.held_out("seasonal_naive", s) is not None]
        per_sku = [s for s in per_sku if s is not None]
        report.same(f"leaderboard: {r.model} median per-SKU skill", row["median_sku_skill"],
                    None if r.model == "seasonal_naive" or not per_sku else statistics.median(per_sku))
    order = [x["model"] for x in body["models"]]
    report.same("leaderboard: ordered by WAPE", order, list(pooled.sort_values("wape")["model"]))
    report.same("leaderboard: oracle floor present", "oracle" in rows, True)


def check_oracle_test(api, d: Data, report: Report) -> None:
    body = api("forecasts/oracle-test")
    stored = d.params["forward_oracle"]
    report.same("oracle-test: weeks", [body["weeks_from"], body["weeks_to"]], stored["weeks"])
    for part, key in (("pooled", "pooled"), ("festive", "festive_pooled")):
        for k in ("skus", "champion_wape", "naive_wape", "skill"):
            report.same(f"oracle-test: {part} {k}", body[part][k], stored[key][k])


def check_gift_box_peak(api, d: Data, report: Report) -> str:
    diwali = d.events[d.events["name"].str.startswith("Diwali") & (d.events["date"].map(lambda x: x.year) == 2026)]
    day = diwali["date"].iloc[0]
    lead = [day - timedelta(days=k) for k in range(1, DIWALI_LEAD_DAYS + 1)]
    weeks = sorted({monday(x) for x in lead})
    f = d.forecasts[d.forecasts["sku"] == GIFT_BOX]
    peak = f.loc[f["p50"].idxmax(), "week"]
    report.same("peak: Gift Box peaks in the Diwali 2026 weeks", peak in weeks, True)
    events = api(f"forecasts/{GIFT_BOX}/context")["events"]
    marked = [e for e in events if e["name"].startswith("Diwali")]
    report.same("peak: Diwali is a horizon event in its week", [e["week"] for e in marked],
                [monday(day).isoformat()])
    return (f"Gift Box: stored forecast peaks in w/c {peak.isoformat()} ({int(f['p50'].max()):,} units); "
            f"Diwali {day.isoformat()}, its weeks {', '.join(w.isoformat() for w in weeks)}; "
            f"marked in w/c {monday(day).isoformat()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--email", default=DEMO_USERS[0][0])
    parser.add_argument("--password", default=DEMO_PASSWORD)
    args = parser.parse_args()

    data = Data(sa.create_engine(normalize_url(get_settings().database_url)))
    if data.past.empty:
        print("No stored past forecasts: run make backtest-forecasts first.", file=sys.stderr)
        return 1
    http = httpx.Client(base_url=args.base_url + "/api/v1", timeout=60)

    def sign_in() -> None:
        login = http.post("/auth/login", json={"email": args.email, "password": args.password, "remember": False})
        login.raise_for_status()
        http.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    def get(path: str, **params) -> httpx.Response:
        response = http.get("/" + path, params=params)
        if response.status_code == 401:  # the access token lives 15 minutes
            sign_in()
            response = http.get("/" + path, params=params)
        response.raise_for_status()
        return response

    sign_in()
    report = Report()
    check_overview(lambda p, **k: get(p, **k).json(), data, report)
    check_forecast_and_csv(lambda p, **k: get(p, **k).json(), lambda p, **k: get(p, **k).text, data, report)
    check_allocation(lambda p, **k: get(p, **k).json(), data, report)
    check_context(lambda p, **k: get(p, **k).json(), data, report)
    check_stored_past_forecasts(data, report)
    check_leaderboard(lambda p, **k: get(p, **k).json(), data, report)
    check_oracle_test(lambda p, **k: get(p, **k).json(), data, report)
    peak = check_gift_box_peak(lambda p, **k: get(p, **k).json(), data, report)

    print(f"Forecast run {data.run_id}, backtest run {data.backtest_id}.\n\nFigures compared, by check:")
    for name, count in sorted(report.checked.items()):
        print(f"  {name:12s} {count:6,}")
    print(f"\n{peak}")
    if report.failures:
        print(f"\n{len(report.failures)} MISMATCH(ES):")
        print("\n".join("  " + f for f in report.failures[:60]))
        return 1
    print(f"\nAll {sum(report.checked.values()):,} figures match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
