"""docs/backtest-report.md, generated from the latest backtest run and, when there is one
from that backtest, the latest production run, with v1's runs beside them. Every number
comes from the database, except the v2 experiment figures in the constants below (variants a
backtest does not re-run). `make backtest` and `make forecast` both regenerate the file; edit
this module, not the file."""

import statistics
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.forecasting.backtest import CHAMPION, INTERVAL_CHECK_FROM, MARGIN, ORACLE, REPORTED_HORIZONS
from app.forecasting.metrics import skill
from app.forecasting.models import BASELINE, ENSEMBLE, MODEL_NAMES
from app.forecasting.scoring import FESTIVE_CATEGORIES
from app.forecasting.store import latest_of_version, latest_run, run_version
from app.models import BacktestMetric, ForecastRun, ForecastRunKind, Product

REPORT_PATH = REPO_ROOT / "docs" / "backtest-report.md"
TARGET = 0.15
COVERAGE_BAND = (0.75, 0.85)
RUNTIME_LIMIT_S = 15 * 60
LABEL = {"seasonal_naive": "Seasonal naive", "ets": "ETS", "prophet": "Prophet", "lightgbm": "LightGBM",
         ENSEMBLE: "Prophet + LightGBM mean", CHAMPION: "Champions", ORACLE: "Oracle (expected demand)"}
COLUMNS = ["model", "sku", "window", "shocks", "horizon", "n_weeks", "wape", "bias", "mase", "coverage_80",
           "coverage_95"]

# The v2 experiments, selection window only: pooled WAPE over the 11 headline SKUs and over the
# festive ones among them, targets 2025-10-06..2026-06-29, every origin that reaches them.
# A backtest runs only the adopted configuration, so the rejected variants are recorded here;
# the adopted rows can be checked against this run's own selection WAPE (the report prints it).
PROPHET_VARIANTS = (
    ("v1: no merges, every week fitted", 0.1821, 0.1599),
    ("Festival merges only", 0.1777, 0.1651),
    ("Merges + trailing dip rule", 0.1364, 0.1493),
    ("Merges + dip rule against trailing and year-ago weeks", 0.1745, 0.1599),
    ("Merges + the same, trailing alone in the first year (adopted)", 0.1403, 0.1484),
)
LIGHTGBM_VARIANTS = (
    ("v1: 13-week mean level", 0.1309, 0.1604),
    ("13-week median level (adopted)", 0.1262, 0.1579),
    ("Median level + offsets from every moving festival", 0.1308, 0.1644),
)
OFFSETS_BETTER_ON = ("FDS-GFB-1KG", "IND-MTR-1HP")


def pct(x: float | None, signed: bool = False) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    return f"{x:+.1%}" if signed else f"{x:.1%}"


def num(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None or pd.isna(x) else f"{x:.{digits}f}"


class Metrics:
    def __init__(self, frame: pd.DataFrame):
        self.frame = frame

    def get(self, model: str, field: str, window: str = "held_out", shocks: str = "included",
            sku: str | None = None, horizon: int | None = None) -> float | None:
        f = self.frame
        if f.empty:
            return None
        rows = f[(f["model"] == model) & (f["window"] == window) & (f["shocks"] == shocks)
                 & (f["sku"].isna() if sku is None else f["sku"] == sku)
                 & (f["horizon"].isna() if horizon is None else f["horizon"] == horizon)]
        if rows.empty:
            return None
        value = rows.iloc[0][field]
        return None if pd.isna(value) else float(value)

    def skill(self, model: str, window: str = "held_out", shocks: str = "included", sku: str | None = None,
              horizon: int | None = None) -> float | None:
        return skill(self.get(model, "wape", window, shocks, sku, horizon),
                     self.get(BASELINE, "wape", window, shocks, sku, horizon))

    def median_sku_skill(self, model: str, skus: list[str], window: str = "held_out") -> float | None:
        values = [s for s in (self.skill(model, window, sku=sku) for sku in skus) if s is not None]
        return statistics.median(values) if values else None


@dataclass
class Version:
    """One version's backtest run, its metrics and its production run (any may be missing)."""

    run: ForecastRun | None
    m: Metrics
    production: ForecastRun | None

    @property
    def p(self) -> dict:
        return self.run.params if self.run else {}

    @property
    def forward(self) -> dict | None:
        return self.production.params.get("forward_oracle") if self.production else None


def write_report(session: Session) -> Path:
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(build_report(session), encoding="utf-8", newline="\n")
    return REPORT_PATH


def load_metrics(session: Session, run_id: int) -> Metrics:
    rows = session.execute(
        sa.select(BacktestMetric, Product.sku).outerjoin(Product, Product.id == BacktestMetric.product_id)
        .where(BacktestMetric.run_id == run_id)
    ).all()
    return Metrics(pd.DataFrame([{
        "model": m.model, "sku": sku, "window": m.window.value, "shocks": m.shocks.value, "horizon": m.horizon,
        "n_weeks": m.n_weeks, "wape": m.wape, "bias": m.bias, "mase": m.mase,
        "coverage_80": m.coverage_80, "coverage_95": m.coverage_95,
    } for m, sku in rows], columns=COLUMNS))


def build_report(session: Session) -> str:
    run = latest_run(session, ForecastRunKind.BACKTEST)
    if run is None:
        return "# Backtest report\n\nNo backtest run yet: `make backtest`.\n"
    version = run_version(run)
    new = Version(run, load_metrics(session, run.id),
                  latest_of_version(session, ForecastRunKind.PRODUCTION, version, backtest_run_id=run.id))
    old_run = latest_of_version(session, ForecastRunKind.BACKTEST, "v1") if version != "v1" else None
    old = Version(old_run, load_metrics(session, old_run.id) if old_run else Metrics(pd.DataFrame(columns=COLUMNS)),
                  latest_of_version(session, ForecastRunKind.PRODUCTION, "v1", backtest_run_id=old_run.id)
                  if old_run else None)
    festive = set(session.scalars(sa.select(Product.sku).where(Product.category.in_(FESTIVE_CATEGORIES))))
    return "\n".join(_sections(new, old, version, festive))


def _champion_coverage(m: Metrics, skus: list[str], field: str) -> float | None:
    """Weighted by forecast-weeks: the SKUs' champion coverage, pooled."""
    total, covered = 0, 0.0
    for sku in skus:
        value, n = m.get(CHAMPION, field, sku=sku), m.get(CHAMPION, "n_weeks", sku=sku)
        if value is not None and n:
            total += int(n)
            covered += value * n
    return covered / total if total else None


def _by_champion(champions: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sku, model in sorted(champions.items()):
        out.setdefault(model, []).append(sku)
    return out


def _inside(x: float | None) -> bool:
    return x is not None and COVERAGE_BAND[0] <= x <= COVERAGE_BAND[1]


def _diwali_passed(forward: dict | None) -> str:
    if not forward:
        return "n/a"
    skus = forward["diwali"]["skus"]
    return f"{sum(r['pass'] for r in skus)} of {len(skus)}"


def _champions_text(champions: dict[str, str]) -> str:
    counts = {m: len(s) for m, s in _by_champion(champions).items()}
    return ", ".join(f"{LABEL[m]} {n}" for m, n in sorted(counts.items(), key=lambda kv: -kv[1]))


def _sections(new: Version, old: Version, version: str, festive: set[str]) -> list[str]:
    m, p, run, production = new.m, new.p, new.run, new.production
    m1, p1 = old.m, old.p
    notes = p["notes"]
    headline, short = p["headline_skus"], p["short_history_skus"]
    champions, champions1 = p["champions"], p1.get("champions", {})
    held = (p["held_out_start"], run.training_cutoff.isoformat())
    head_skill = m.skill(CHAMPION)
    champ_wape, naive_wape = m.get(CHAMPION, "wape"), m.get(BASELINE, "wape")
    median_skill = m.median_sku_skill(CHAMPION, headline)
    per_sku = {s: m.skill(CHAMPION, sku=s) for s in headline}
    losers = sorted(s for s, v in per_sku.items() if v is not None and v <= 0)
    weak = sorted(s for s, v in per_sku.items() if v is not None and 0 < v < TARGET)
    cov80 = m.get(CHAMPION, "coverage_80")
    met = head_skill is not None and head_skill >= TARGET
    f, f1 = new.forward, old.forward
    out: list[str] = []
    w = out.append

    w(f"# Backtest report: weekly demand forecasts (phase 5a, {version})\n")
    w(f"Generated from backtest run {run.id} ({run.trained_at:%Y-%m-%d %H:%M} UTC)"
      + (f" and forecast run {production.id}" if production else "")
      + (f"; v1 is backtest run {old.run.id}" + (f" and forecast run {old.production.id}" if old.production else "")
         + ", kept beside it" if old.run else "")
      + f". Pinned dataset, sales to {run.data_end_date}; the last complete week starts {run.training_cutoff}. "
      f"`make backtest` took {run.duration_seconds:.0f} s on the dev laptop. Regenerated by `make backtest` and "
      "`make forecast`; edit `backend/app/forecasting/report.py`, not this file.\n")

    if old.run:
        w("## Read this first\n")
        w("- **The held-out window has now been looked at twice**, once for v1 and once for v2. Every v2 change "
          "was decided on the selection window, on a split inside it (chosen on targets before "
          f"{INTERVAL_CHECK_FROM}, judged on the weeks from then to the held-out start), and the held-out window "
          "and the forward oracle test were then re-scored once, with nothing changed afterwards. But what "
          "prompted the changes came from v1's held-out results, so **v2's held-out figures are a second look, "
          "not a clean out-of-sample result**.")
        w("- **The festival changes were motivated by v1's Diwali-check failure** (4 of 6 festive champions "
          "peaked in the Diwali weeks of the forward oracle test). In v1 the Namkeen's Prophet forecast peaked in "
          "w/c 2026-10-12, three weeks before expected demand's peak (w/c 2026-11-02), and the Induction "
          "Cooktop's champion was ETS, which has no calendar. That result is why Prophet's festival regressors and LightGBM's festival features were "
          "revisited. The replacements were chosen on the selection window, by a rule written before looking "
          "at their effect on Diwali 2026 (merge festivals that are within a week of each other in every year; "
          "no parameter tuned on the two festive seasons), but the trigger was a forward-test result, so "
          "**v2's Diwali check is not a clean test either**.")
        w("- **The interval caveat from v1 still holds**: the interval method was recalibrated because of v1's "
          "first held-out result (see Intervals), so held-out coverage is not a fully clean number in either "
          "version. v2's wider intervals for short-history SKUs were prompted by v1's held-out Air Fryer "
          "coverage (40% at 80%) and decided on a simulation inside the selection window.")
        w("- A bug was found while building v2: LightGBM's \"mean level\" setting silently used the median for "
          "every SKU after the first (a parameter shadowed by a loop variable). It affected only the v2 "
          "experiments' copy of the v1 LightGBM (13.6% selection WAPE instead of v1's own 13.1%), never v1's "
          "runs and never the adopted median setting. Fixed and covered by a test; the LightGBM decision below "
          "is stated against v1's real 13.1%.\n")

    w("## Summary\n")
    verdict = (f"**The 15% target is met on this window**: the champions' error is {pct(head_skill)} lower than "
               f"seasonal naive's" if met else
               f"**The 15% target is not met**: the champions' error is only {pct(head_skill)} lower than "
               f"seasonal naive's")
    w(f"{verdict} (WAPE {pct(champ_wape)} against {pct(naive_wape)}) on the held-out window, the last 13 complete "
      f"weeks (w/c {held[0]} to {held[1]}), pooled over the {len(headline)} SKUs that have a seasonal-naive "
      f"forecast and over horizons 1-26. **That window is off-season**: it holds no festive peak and misses the "
      "summer peak, so it measures off-season performance, not the festival timing the models were designed "
      "for. The festive-season breakdown below comes from the selection window (Oct-Nov 2025, the window the "
      "choices were made on, so it flatters them), and the forward oracle test scores the production "
      "forecast across Diwali 2026 against expected demand.\n")
    w(f"Pooled WAPE is volume-weighted: the bearing (about 5,000 units a week) dominates it and the Gift Box "
      f"(about 20) barely registers. Per SKU, the median skill is {pct(median_skill)}"
      + (f"; the champion does not beat seasonal naive on {', '.join(losers)}" if losers else "")
      + (f"; it beats it by less than 15% on {', '.join(weak)}" if weak else "")
      + f". The oracle, which knows the true expected demand, scores {pct(m.get(ORACLE, 'wape'))}. The "
      f"champions' 80% intervals cover {pct(cov80)} of held-out weeks (target 75-85%); not a fully clean "
      "held-out number (see Intervals).\n")

    if old.run:
        w("## v1 against v2\n")
        w("| | v1 | v2 |")
        w("|---|---|---|")
        rows = [
            ("Champions", _champions_text(champions1), _champions_text(champions)),
            ("Held-out WAPE, champions (pooled)", pct(m1.get(CHAMPION, "wape")), pct(champ_wape)),
            ("Held-out skill against seasonal naive", pct(m1.skill(CHAMPION), True), pct(head_skill, True)),
            ("Held-out median per-SKU skill", pct(m1.median_sku_skill(CHAMPION, headline), True),
             pct(median_skill, True)),
            ("Held-out 80% coverage, champions", pct(m1.get(CHAMPION, "coverage_80")), pct(cov80)),
            ("Held-out 95% coverage, champions", pct(m1.get(CHAMPION, "coverage_95")),
             pct(m.get(CHAMPION, "coverage_95"))),
            ("Held-out WAPE without shock weeks", pct(m1.get(CHAMPION, "wape", shocks="excluded")),
             pct(m.get(CHAMPION, "wape", shocks="excluded"))),
            ("Selection WAPE, champions (v1 picked each SKU's on it)", pct(m1.get(CHAMPION, "wape", "selection")),
             pct(m.get(CHAMPION, "wape", "selection"))),
            ("Festive 2025 WAPE, champions (selection window)", pct(m1.get(CHAMPION, "wape", "festive_2025")),
             pct(m.get(CHAMPION, "wape", "festive_2025"))),
            ("Forward oracle skill, all headline SKUs", pct(f1["pooled"]["skill"], True) if f1 else "n/a",
             pct(f["pooled"]["skill"], True) if f else "n/a"),
            ("**Forward oracle skill, festive SKUs**",
             f"**{pct(f1['festive_pooled']['skill'], True)}**" if f1 else "n/a",
             f"**{pct(f['festive_pooled']['skill'], True)}**" if f else "n/a"),
            ("Diwali 2026: festive champions peaking in the Diwali weeks", _diwali_passed(f1), _diwali_passed(f)),
            ("`make backtest` runtime", f"{old.run.duration_seconds:.0f} s", f"{run.duration_seconds:.0f} s"),
        ]
        for label, a, b in rows:
            w(f"| {label} | {a} | {b} |")
        w("\nForward oracle WAPE is against expected demand, not noisy actuals: compare it only with itself. The "
          "festive line is the one this project's promise rests on: the festive peak is what a planner needs "
          "the forecast for.\n")

        w("## Acceptance criteria\n")
        w("| Criterion | v1 | v2 |")
        w("|---|---|---|")
        w("| No-leakage test exists and passes | `tests/test_forecast_leakage.py`; passed in v1's `make test` "
          "| same test, extended to v2's models; run by `make test` (a test result is not stored with a run) |")
        w("| Determinism test passes | `tests/test_forecast_determinism.py` passed; three production runs gave "
          "one digest | same test, with the ensemble champion; run by `make test` |")
        w(f"| Festive SKUs peak in the Diwali 2026 weeks | {_diwali_passed(f1)}: "
          f"{'met' if f1 and all(r['pass'] for r in f1['diwali']['skus']) else '**not met**'} "
          f"| {_diwali_passed(f)}: "
          f"{'met' if f and all(r['pass'] for r in f['diwali']['skus']) else '**not met**'} |")
        w(f"| Held-out 80% coverage within 75-85% for each champion | {_coverage_verdict(m1, champions1)} "
          f"| {_coverage_verdict(m, champions)} |")
        w(f"| `make backtest` finishes locally (limit 15 min) | {old.run.duration_seconds:.0f} s: met "
          f"| {run.duration_seconds:.0f} s: {'met' if run.duration_seconds <= RUNTIME_LIMIT_S else '**not met**'} |")
        w("| `make test` passes on SQLite, no PostgreSQL tests without the flag | passed | run by `make test` "
          "(not recorded here) |")
        w("")

        _decisions(w, m, m1, notes)

    w("## What worked and what didn't\n")
    model_wapes = {name: m.get(name, "wape") for name in MODEL_NAMES}
    better = [n for n in MODEL_NAMES if model_wapes[n] is not None and champ_wape is not None
              and model_wapes[n] < champ_wape]
    for name in better:
        w(f"- **{LABEL[name]} alone beat the champions on the held-out window** (WAPE {pct(model_wapes[name])} "
          f"against {pct(champ_wape)}). Not acted on: choosing on the held-out window would empty its headline.")
    for name in MODEL_NAMES:
        if name == BASELINE:
            continue
        w(f"- {LABEL[name]}: held-out WAPE {pct(model_wapes[name])} (v1 {pct(m1.get(name, 'wape'))}), "
          f"{pct(m.skill(name))} lower than seasonal naive; selection window {pct(m.get(name, 'wape', 'selection'))} "
          f"(v1 {pct(m1.get(name, 'wape', 'selection'))}).")
    w(f"- Seasonal naive is biased low ({pct(m.get(BASELINE, 'bias'), True)} held-out): it repeats last year and "
      "misses growth. It also cannot move a festival: Diwali was 11 days earlier in 2025 than in 2024.")
    shock, shock1 = notes.get("after_shock", {}), p1.get("notes", {}).get("after_shock", {})
    if shock:
        w(f"- **A supply shock in the last training week**, all origins: WAPE at horizons 1-4 when the week "
          f"before the origin was a shock week ({shock[BASELINE]['after_shock_weeks']} forecast-weeks per model), "
          "against every other origin:\n")
        w("  | Model | v2 after a shock | v2 otherwise | v1 after a shock | v1 otherwise |")
        w("  |---|---|---|---|---|")
        for name, v in shock.items():
            if name == ORACLE:
                continue
            o = shock1.get(name, {})
            w(f"  | {LABEL[name]} | {pct(v['after_shock'])} | {pct(v['otherwise'])} | {pct(o.get('after_shock'))} "
              f"| {pct(o.get('otherwise'))} |")
        w("")
    if f:
        for r in [r for r in f["diwali"]["skus"] if not r["pass"]]:
            peaks = f.get("peaks_by_model", {})
            others = ", ".join(f"{LABEL[n]} {peaks[n].get(r['sku'])}" for n in (*MODEL_NAMES, ENSEMBLE)
                               if n in peaks and n != r["model"])
            w(f"- **{r['sku']} misses the Diwali 2026 peak**: its champion ({LABEL[r['model']]}) peaks in the week "
              f"of {r['champion_peak']}; expected demand peaks in the week of {r['expected_peak']}. Other models' "
              f"peaks: {others}.")
    if short:
        sku = short[0]
        w(f"- Short history, outside the headline: {', '.join(short)} (launched Feb 2026, no seasonal-naive "
          f"forecast exists before Feb 2027). Champion {LABEL[champions[sku]]} (LightGBM alone: Prophet needs two "
          f"years), intervals from the young-SKU table: held-out WAPE {pct(m.get(CHAMPION, 'wape', sku=sku))} "
          f"(v1 {pct(m1.get(CHAMPION, 'wape', sku=sku))}), 80% coverage {pct(m.get(CHAMPION, 'coverage_80', sku=sku))} "
          f"(v1 {pct(m1.get(CHAMPION, 'coverage_80', sku=sku))}).")
    w("")

    w("## Leaderboard\n")
    w("Pooled over the headline SKUs, horizons 1-26, all weeks. Skill = 1 - WAPE / seasonal naive's WAPE. "
      "MASE: mean absolute error over the in-sample seasonal-naive error of each training history (below 1 "
      "beats last year's actuals on the training data). Coverage is measured on the held-out window only. "
      f"Champions: {LABEL[ENSEMBLE]} for every SKU in v2, a per-SKU pick in v1.\n")
    w("| Model | Held-out WAPE | v1 | Skill | Median per-SKU skill | Bias | MASE | 80% cov. | 95% cov. "
      "| Selection WAPE | v1 |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for name in (*MODEL_NAMES, CHAMPION, ORACLE):
        w(f"| {LABEL[name]} | {pct(m.get(name, 'wape'))} | {pct(m1.get(name, 'wape'))} "
          f"| {pct(m.skill(name), True) if name != BASELINE else '-'} "
          f"| {pct(m.median_sku_skill(name, headline), True) if name != BASELINE else '-'} "
          f"| {pct(m.get(name, 'bias'), True)} | {num(m.get(name, 'mase'))} | {pct(m.get(name, 'coverage_80'))} "
          f"| {pct(m.get(name, 'coverage_95'))} | {pct(m.get(name, 'wape', 'selection'))} "
          f"| {pct(m1.get(name, 'wape', 'selection'))} |")
    w("")

    w("## Champion against seasonal naive, per SKU (held-out)\n")
    w("| SKU | Champion | WAPE | Seasonal naive | Skill | Bias | 80% cov. | 95% cov. | Weeks | v1 champion "
      "| v1 skill |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for sku in sorted(champions):
        w(f"| {sku}{' (short history)' if sku in short else ''} | {LABEL[champions[sku]]} "
          f"| {pct(m.get(CHAMPION, 'wape', sku=sku))} | {pct(m.get(BASELINE, 'wape', sku=sku))} "
          f"| {pct(m.skill(CHAMPION, sku=sku), True)} | {pct(m.get(CHAMPION, 'bias', sku=sku), True)} "
          f"| {pct(m.get(CHAMPION, 'coverage_80', sku=sku))} | {pct(m.get(CHAMPION, 'coverage_95', sku=sku))} "
          f"| {int(m.get(CHAMPION, 'n_weeks', sku=sku) or 0)} "
          f"| {LABEL.get(champions1.get(sku), 'n/a')} | {pct(m1.skill(CHAMPION, sku=sku), True)} |")
    w(f"\nMedian per-SKU skill: **{pct(median_skill)}** (pooled: {pct(head_skill)}). 'Weeks' counts forecast-"
      "weeks: each of the 13 held-out weeks is forecast from up to 9 origins.\n")

    w("## By horizon (held-out, pooled)\n")
    w("| Horizon | " + " | ".join(LABEL[n] for n in (*MODEL_NAMES, CHAMPION, ORACLE)) + " | Champion skill | v1 |")
    w("|---|" + "---|" * (len(MODEL_NAMES) + 4))
    for h in REPORTED_HORIZONS:
        w(f"| {h} | " + " | ".join(pct(m.get(n, 'wape', horizon=h)) for n in (*MODEL_NAMES, CHAMPION, ORACLE))
          + f" | {pct(m.skill(CHAMPION, horizon=h), True)} | {pct(m1.skill(CHAMPION, horizon=h), True)} |")
    w("\nEach horizon has only about 3 origins x 11 SKUs in the held-out window; the pooled 1-26 figure is the "
      "stable one.\n")

    w("## The oracle floor\n")
    w("The oracle forecasts the ground truth's expected demand, so its error is pure Poisson sampling noise: "
      "the floor no model can beat. 'Reducible' is how much of seasonal naive's excess error over the floor the "
      "champions remove: (naive - champion) / (naive - oracle).\n")
    w("| Window | Oracle | Champions | Seasonal naive | Reducible error removed | v1 |")
    w("|---|---|---|---|---|---|")
    for window, label in (("held_out", "Held-out"), ("selection", "Selection"), ("festive_2025", "Festive 2025")):
        row = []
        for mm in (m, m1):
            o, c, n = mm.get(ORACLE, "wape", window), mm.get(CHAMPION, "wape", window), mm.get(BASELINE, "wape", window)
            row.append(((n - c) / (n - o) if None not in (o, c, n) and n != o else None, o, c, n))
        (removed, o, c, n), (removed1, *_) = row
        w(f"| {label} | {pct(o)} | {pct(c)} | {pct(n)} | {pct(removed)} | {pct(removed1)} |")
    w("")

    w("## With and without supply-shock weeks\n")
    w("Shock weeks (from the ground truth: a SKU-week holding any day of that SKU's supply shock) are not "
      "forecastable by design. Scored both ways:\n")
    w("| Model | Held-out, all weeks | Held-out, no shock weeks | Selection, all weeks | Selection, no shock weeks |")
    w("|---|---|---|---|---|")
    for name in (*MODEL_NAMES, CHAMPION, ORACLE):
        w(f"| {LABEL[name]} | {pct(m.get(name, 'wape'))} | {pct(m.get(name, 'wape', shocks='excluded'))} "
          f"| {pct(m.get(name, 'wape', 'selection'))} | {pct(m.get(name, 'wape', 'selection', 'excluded'))} |")
    w(f"\nChampion skill without shock weeks: {pct(m.skill(CHAMPION, shocks='excluded'))} held-out "
      f"(v1 {pct(m1.skill(CHAMPION, shocks='excluded'))}).\n")

    w("## Festive season 2025 (selection window: not a held-out result)\n")
    w(f"Target weeks Sep-Nov 2025. **These weeks are in the selection window**: the choices were made on them, "
      f"so the scores here are flattered. The first origin is w/c 2025-10-06, so the earliest scored week is "
      f"{notes['festive_first_target']}; September 2025 is before any origin. Diwali 2025 was 20 Oct.\n")
    w("| Model | WAPE | Skill vs seasonal naive | Bias | v1 WAPE |")
    w("|---|---|---|---|---|")
    for name in (*MODEL_NAMES, CHAMPION, ORACLE):
        w(f"| {LABEL[name]} | {pct(m.get(name, 'wape', 'festive_2025'))} "
          f"| {pct(m.skill(name, 'festive_2025'), True) if name != BASELINE else '-'} "
          f"| {pct(m.get(name, 'bias', 'festive_2025'), True)} | {pct(m1.get(name, 'wape', 'festive_2025'))} |")
    festive_skus = [s for s in headline if s in festive]
    w("\nPer festive SKU (Packaged Foods and Kitchen Appliances):\n")
    w("| SKU | Champion | Champion WAPE | Seasonal naive WAPE | Skill | v1 champion | v1 WAPE |")
    w("|---|---|---|---|---|---|---|")
    for sku in festive_skus:
        w(f"| {sku} | {LABEL[champions[sku]]} | {pct(m.get(CHAMPION, 'wape', 'festive_2025', sku=sku))} "
          f"| {pct(m.get(BASELINE, 'wape', 'festive_2025', sku=sku))} "
          f"| {pct(m.skill(CHAMPION, 'festive_2025', sku=sku), True)} | {LABEL.get(champions1.get(sku), 'n/a')} "
          f"| {pct(m1.get(CHAMPION, 'wape', 'festive_2025', sku=sku))} |")
    w("")

    _intervals(w, m, m1, notes, champions, champions1, short, cov80)

    w("## Bias\n")
    w("ETS, Prophet and LightGBM forecast log(1 + units) and transform back, which gives a median, not a mean. "
      "That suits WAPE but reads low on skewed SKUs. Not corrected; reported:\n")
    w("| Model | Held-out bias | Selection bias | Festive 2025 bias |")
    w("|---|---|---|---|")
    for name in (*MODEL_NAMES, CHAMPION):
        w(f"| {LABEL[name]} | {pct(m.get(name, 'bias'), True)} | {pct(m.get(name, 'bias', 'selection'), True)} "
          f"| {pct(m.get(name, 'bias', 'festive_2025'), True)} |")
    w("\nNegative = forecasts too low. Per-SKU bias is in the champion table above.\n")

    w("## XYZ on forecast errors\n")
    w("Phase 4's XYZ measures volume variability (CV of the last 52 weeks' units). Re-measured on the "
      "champion's forecast errors (std of actual - p50 over mean actual, horizons 1-13, every backtest week), "
      "same thresholds (X < 0.5, Y up to 1.0, Z above):\n")
    w("| SKU | Champion | Volume CV | Volume XYZ | Error CV | Error XYZ | Moved |")
    w("|---|---|---|---|---|---|---|")
    for row in p["xyz"]:
        moved = "-" if row["volume_xyz"] == row["error_xyz"] else f"{row['volume_xyz']} to {row['error_xyz']}"
        w(f"| {row['sku']} | {LABEL.get(row['champion'], row['champion'])} | {num(row['volume_cv'])} "
          f"| {row['volume_xyz'] or 'n/a'} | {num(row['error_cv'])} | {row['error_xyz'] or 'n/a'} | {moved} |")
    w("\nVolume XYZ says how much demand swings; error XYZ says how much of the swing the forecast misses. A "
      "regular festive peak is variable but predictable, so it should move toward X.\n")

    _forward(w, f, f1)

    w("## Reproducibility\n")
    versions = ", ".join(f"{k} {v}" for k, v in sorted(run.library_versions.items()))
    w(f"- Seed {run.random_seed}; {versions}.")
    if production:
        w(f"- Production forecast digest (SHA-256 of every row): `{production.params['digest']}`. Same seed, data "
          "and versions give the same digest; `tests/test_forecast_determinism.py` checks it.")
    if old.production:
        w(f"- v1's digest: `{old.production.params['digest']}`.")
    if p.get("warnings"):
        w(f"- Fit warnings ({len(p['warnings'])}): " + "; ".join(p["warnings"][:8])
          + (" ..." if len(p["warnings"]) > 8 else ""))
    w(f"- Origins: {', '.join(p['origins'])}. Held-out window from {p['held_out_start']}.")
    w("")
    return out


def _coverage_verdict(m: Metrics, champions: dict[str, str]) -> str:
    if not champions:
        return "n/a"
    parts, ok = [], True
    for model, skus in _by_champion(champions).items():
        c80 = _champion_coverage(m, skus, "coverage_80")
        ok &= _inside(c80)
        parts.append(f"{LABEL[model]} {pct(c80)}")
    return ", ".join(parts) + (": met" if ok else ": **not met**")


def _decisions(w, m: Metrics, m1: Metrics, notes: dict) -> None:
    w("## How v2 was decided (selection window only)\n")
    w(f"Each decision below was made on the selection window, most on a split inside it: chosen on targets "
      f"before {INTERVAL_CHECK_FROM}, judged on the weeks from then to the held-out start. The checks marked "
      "'this run' are recomputed by every `make backtest`; the variant tables come from the v2 experiments "
      "(constants in `report.py`, because a backtest runs only the adopted configuration).\n")

    check = notes.get("champion_check") or {}
    if check:
        w("### Champion: the mean of Prophet and LightGBM, for every SKU\n")
        w(f"This run, judged from {check['judged_from']} (pooled over the headline SKUs; festive = Packaged Foods "
          "and Kitchen Appliances):\n")
        w("| Strategy | Pooled WAPE | Median per-SKU skill | Festive WAPE |")
        w("|---|---|---|---|")
        for key, label in (("v1", "v1: each SKU's lowest WAPE"),
                           ("margin", f"(a) a per-SKU champion only if {MARGIN:.0%} better than the default "
                                      f"({LABEL[check['margin']['default']]}); calendar-aware only for festive SKUs"),
                           ("mean", "(b) the mean of Prophet and LightGBM (adopted)")):
            r = check[key]
            w(f"| {label} | {pct(r['pooled_wape'])} | {pct(r['median_sku_skill'], True)} | {pct(r['festive_wape'])} |")
        w(f"| Seasonal naive | {pct(check['baseline_pooled_wape'])} | - | - |")
        w("\nThe adopted strategy is the one with the lowest pooled WAPE on the later weeks; (a)'s default is "
          "the single model with the lowest pooled WAPE on the earlier weeks, not the model that won the "
          "held-out window in v1. The mean is calendar-aware by construction (both parts use the festival "
          "calendar), so the festive SKUs get calendar-aware champions only, without a rule of their own. The "
          "Air Fryer, which Prophet cannot fit, gets LightGBM alone.\n")

    w("### LightGBM: the 13-week median as its level\n")
    w("Every sales feature and the target are measured against a recent level. v1 used the 13-week mean, which "
      "one shock week drags down for the next 13 weeks; the median is barely moved by it.\n")
    w("| LightGBM | Selection WAPE, headline SKUs | Festive SKUs |")
    w("|---|---|---|")
    for label, pooled, fest in LIGHTGBM_VARIANTS:
        w(f"| {label} | {pct(pooled)} | {pct(fest)} |")
    w(f"\nCross-checks against the backtest runs: v1's LightGBM selection WAPE "
      f"{pct(m1.get('lightgbm', 'wape', 'selection'))} (v1 run), this run's {pct(m.get('lightgbm', 'wape', 'selection'))} "
      f"(the experiments' adopted row: {pct(LIGHTGBM_VARIANTS[1][1])}).\n")
    moving = notes.get("moving_festivals", [])
    w(f"**Festival offsets: tried, not adopted.** For every festival whose date moves by more than a week "
      f"between years ({', '.join(moving)}: cheap to add all of them, so all were tried, not Diwali alone), two "
      "features: the target week's days from the festival, and how that differs from the year-ago week's "
      "days from last year's festival. They worsened pooled selection WAPE "
      f"({pct(LIGHTGBM_VARIANTS[2][1])} against {pct(LIGHTGBM_VARIANTS[1][1])}) and helped only "
      f"{len(OFFSETS_BETTER_ON)} of 11 SKUs ({', '.join(OFFSETS_BETTER_ON)}), so the adoption rule (no worse "
      "pooled selection WAPE) rejects them.\n")

    w("### Prophet: merged festivals and a dip rule\n")
    merges = notes.get("festival_merges", [])
    w("**Festival merges.** The rule: festivals among Prophet's regressors whose dates fall within 7 days of "
      "each other in every year of the calendar become one combined regressor (their window columns summed). "
      "Weekly data cannot tell such festivals apart, so separate regressors get large opposite effects that "
      "cancel in the past but not when the two dates fall differently against the weeks. Merges this run "
      f"made: {'; '.join(' + '.join(g) for g in merges) if merges else 'none'}. Dhanteras and Diwali, always two "
      "days apart, were checked for the same problem: "
      + ("they have it, and are merged too." if any({"dhanteras", "diwali"} <= set(g) for g in merges)
         else "the rule does not merge them on this calendar.")
      + " No prior was tuned; the default regressor prior is kept.\n")
    w("**The dip rule.** A week whose units collapsed is left out of Prophet's fit, so a supply shock in the "
      "last training weeks does not bend the trend. Selection-window experiments:\n")
    w("| Prophet | Selection WAPE, headline SKUs | Festive SKUs |")
    w("|---|---|---|")
    for label, pooled, fest in PROPHET_VARIANTS:
        w(f"| {label} | {pct(pooled)} | {pct(fest)} |")
    w(f"\nThis run's Prophet selection WAPE: {pct(m.get('prophet', 'wape', 'selection'))} (the experiments' "
      f"adopted row: {pct(PROPHET_VARIANTS[-1][1])}).\n")
    audit = notes.get("dip_audit") or {}
    if audit:
        rules = [r for r in audit if r != "to"]
        names = {"trailing": "Below half the trailing 13-week median",
                 "trailing_and_year_ago": "... and below half the same weeks last year",
                 "trailing_and_year_ago_if_known": "... the same, trailing alone in the first year (adopted)"}
        w(f"**Audited before it was relied on.** Every week each rule leaves out (history to w/c {audit['to']}), "
          "against the ground truth's shock days, which are read for scoring only and never reach a model. "
          "Precision = dropped weeks that hold a shock day; recall = shock weeks dropped (and shock weeks with 3 "
          "or more shock days dropped).\n")
        w("| Rule | Dropped | Precision | Recall | Recall, 3+ shock days | Dropped without a shock, by SKU |")
        w("|---|---|---|---|---|---|")
        for rule in rules:
            a = audit[rule]["all"]
            wrong = {s: v["dropped"] - v["true"] for s, v in audit[rule]["per_sku"].items() if v["dropped"] > v["true"]}
            w(f"| {names.get(rule, rule)} | {a['dropped']} | {pct(a['precision'])} | {pct(a['recall'])} "
              f"| {pct(a['recall_3_day'])} | {', '.join(f'{s} {n}' for s, n in sorted(wrong.items())) or 'none'} |")
        w("\nThe trailing rule alone deleted real seasonal declines: the Air Cooler's fall after summer and the "
          "Gift Box's after Diwali look like collapses against the 13 weeks before them. Requiring the week to be "
          "below half the same weeks last year as well removes those, and the adopted rule falls back to the "
          "trailing check only where there is no last year yet. Its remaining wrong drops are first-year weeks. "
          "Chosen over the trailing rule although the trailing rule scored lower WAPE, because the trailing rule "
          "works partly by deleting the seasonal drops Prophet is meant to learn.\n")
        w("Per SKU (dropped / precision / recall):\n")
        w("| SKU | Shock weeks | " + " | ".join(names.get(r, r).replace("... ", "") for r in rules) + " |")
        w("|---|---|" + "---|" * len(rules))
        for sku in sorted(audit[rules[0]]["per_sku"]):
            cells = []
            for rule in rules:
                v = audit[rule]["per_sku"][sku]
                cells.append(f"{v['dropped']} / {pct(v['precision'])} / {pct(v['recall'])}")
            w(f"| {sku} | {audit[rules[0]]['per_sku'][sku]['shock_weeks']} | " + " | ".join(cells) + " |")
        w("")

    young = notes.get("young_check") or {}
    if young:
        w("### Short-history SKUs: wider intervals\n")
        w("Long-history SKUs were forecast as if they were young: at each origin, half of them keep only their "
          "last 30 weeks (as if launched then) and LightGBM is trained with the other half intact. Their errors "
          "make the 'young' interval table, used for any SKU with under 52 weeks of data. This run, on the "
          f"selection window (calibrated before {INTERVAL_CHECK_FROM}, measured from it):\n")
        w("| Intervals from | 80% coverage of young SKUs | 95% coverage | Forecast-weeks |")
        w("|---|---|---|---|")
        for key, label in (("young", "Young-SKU errors (adopted)"), ("long_history", "LightGBM's long-history errors")):
            r = young[key]
            w(f"| {label} | {pct(r['coverage_80'])} | {pct(r['coverage_95'])} | {r['n']} |")
        ratios = young.get("width_ratio_80", {})
        w("\nThe young table's 80% intervals are "
          + ", ".join(f"{v:.1f}x as wide at horizons {g}" for g, v in ratios.items())
          + " as LightGBM's long-history ones (log scale).\n")


def _intervals(w, m: Metrics, m1: Metrics, notes: dict, champions: dict, champions1: dict, short: list[str],
               cov80: float | None) -> None:
    w("## Intervals\n")
    check = notes["interval_check"]
    w("Every model's 80% and 95% intervals come from its own backtest errors, log((actual + 1) / (forecast + 1)), "
      "as empirical quantiles per model and horizon group (1-4, 5-13, 14-26), pooled across SKUs; since v2, a "
      "SKU with under 52 weeks of data gets the young-SKU table instead. The held-out window's intervals use "
      "selection-window errors only; production uses every backtest error.\n")
    w("**Recalibrated once in v1, and the held-out result is what triggered it.** The first version used "
      "quantiles per SKU, and its held-out coverage came out low (champions 67.5% at 80%, backtest run 1). That "
      "result is why the method was revisited. The replacement was then chosen on a split inside the selection "
      f"window (calibrated on targets before {check['calibrated_before']}, measured on the rest), where the same "
      "failure showed: a SKU's champion is picked because its selection errors were small, so those errors "
      "understate what comes next. Choosing on the selection window does not undo the trigger: **the held-out "
      "coverage of the pooled method is not a fully clean held-out number**, because the held-out window had "
      "already been seen when the method changed. Both versions (selection split recomputed this run):\n")
    w("| Method | Champions' 80%, selection split | 95%, selection split | Champions' 80%, held-out |")
    w("|---|---|---|---|")
    w(f"| Per SKU (first version) | {pct(check['per_sku']['coverage_80'])} | {pct(check['per_sku']['coverage_95'])} "
      "| 67.5% (backtest run 1) |")
    w(f"| Pooled per model (used) | {pct(check['pooled']['coverage_80'])} | {pct(check['pooled']['coverage_95'])} "
      f"| {pct(cov80)} (measured after the change; v1 {pct(m1.get(CHAMPION, 'coverage_80'))}) |")
    w("\nHeld-out coverage by champion model (v2), with v1's:\n")
    w("| Version | Champion model | SKUs | 80% coverage | In 75-85%? | 95% coverage |")
    w("|---|---|---|---|---|---|")
    for label, mm, champs in (("v2", m, champions), ("v1", m1, champions1)):
        for model_name, skus in _by_champion(champs).items():
            c80, c95 = _champion_coverage(mm, skus, "coverage_80"), _champion_coverage(mm, skus, "coverage_95")
            w(f"| {label} | {LABEL[model_name]} | {', '.join(skus)} | {pct(c80)} "
              f"| {'yes' if _inside(c80) else '**no**'} | {pct(c95)} |")
    long = [s for s in champions if s not in short]
    w(f"\nv2 split by interval table: long-history SKUs {pct(_champion_coverage(m, long, 'coverage_80'))} at 80%"
      + "".join(f"; {s} (young-SKU table) {pct(m.get(CHAMPION, 'coverage_80', sku=s))} at 80% (v1 "
                f"{pct(m1.get(CHAMPION, 'coverage_80', sku=s))})" for s in short) + ".")
    inside_skus = [s for s in champions if _inside(m.get(CHAMPION, "coverage_80", sku=s))]
    w(f"Per SKU {len(inside_skus)} of {len(champions)} land in 75-85%; a single SKU's held-out window is 13 weeks, "
      "so one bad week moves its coverage by up to 9 forecast-weeks. The champion's p50 falls outside its own "
      f"80% interval in {pct(notes['champion_p50_outside_80'])} of held-out forecasts (the p50 is never moved "
      "into it).\n")


def _forward(w, f: dict | None, f1: dict | None) -> None:
    w("## Forward oracle test (production forecast against expected demand)\n")
    if f is None:
        w("No production run from this backtest yet: `make forecast`.\n")
        return
    w(f"The production forecast (w/c {f['weeks'][0]} to {f['weeks'][1]}) spans Diwali 2026, which no backtest "
      "saw. It is scored against the ground truth's expected demand for those weeks, computed with no "
      "promotions and no shocks (the forecast's own assumptions; the generator's own function, with its "
      "window extended into the weeks its holiday list already covers). Seasonal naive's forward forecast "
      "is scored the same way. **These are errors against an expectation, not noisy actuals: they are not "
      "comparable with the backtest WAPE above.**\n")
    w("| Group | Champion WAPE | Seasonal naive WAPE | Skill | v1 champion WAPE | v1 skill |")
    w("|---|---|---|---|---|---|")
    for label, key in (("All headline SKUs", "pooled"), ("**Festive SKUs**", "festive_pooled")):
        g, g1 = f[key], (f1 or {}).get(key, {})
        w(f"| {label} ({len(g['skus'])}) | {pct(g['champion_wape'])} | {pct(g['naive_wape'])} "
          f"| {pct(g['skill'], True)} | {pct(g1.get('champion_wape'))} | {pct(g1.get('skill'), True)} |")
    old = {r["sku"]: r for r in (f1 or {}).get("per_sku", [])}
    w("\n| SKU | Champion | Champion WAPE | Seasonal naive WAPE | Skill | v1 champion | v1 skill |")
    w("|---|---|---|---|---|---|---|")
    for row in f["per_sku"]:
        o = old.get(row["sku"], {})
        w(f"| {row['sku']}{' (festive)' if row['festive'] else ''} | {LABEL[row['model']]} "
          f"| {pct(row['champion_wape'])} | {pct(row['naive_wape'])} | {pct(row['skill'], True)} "
          f"| {LABEL.get(o.get('model'), 'n/a')} | {pct(o.get('skill'), True)} |")
    d = f["diwali"]
    old_peaks = {r["sku"]: r for r in (f1 or {}).get("diwali", {}).get("skus", [])}
    w(f"\n**Diwali 2026 ({d['date']})**: the festive buying falls in the weeks of {' and '.join(d['peak_weeks'])}. "
      f"{_diwali_passed(f)} festive champions peak there (v1: {_diwali_passed(f1)}):\n")
    w("| SKU | Champion | Champion's peak week | Expected demand's peak week | Seasonal naive's peak week | Pass "
      "| v1 champion's peak |")
    w("|---|---|---|---|---|---|---|")
    for r in d["skus"]:
        o = old_peaks.get(r["sku"])
        w(f"| {r['sku']} | {LABEL[r['model']]} | {r['champion_peak']} | {r['expected_peak']} "
          f"| {r['naive_peak'] or 'n/a'} | {'yes' if r['pass'] else '**no**'} "
          f"| {(o['champion_peak'] + ' (' + LABEL[o['model']] + ')') if o else 'n/a'} |")
    by_model = f.get("peaks_by_model")
    if by_model:
        w("\nEvery model's peak week (Sep-Dec 2026), whether or not it is the champion; in the Diwali weeks = "
          "bold:\n")
        names = [n for n in (*MODEL_NAMES, ENSEMBLE) if n in by_model]
        w("| SKU | " + " | ".join(LABEL[n] for n in names) + " |")
        w("|---|" + "---|" * len(names))
        for sku in sorted(by_model[names[0]]):
            cells = []
            for n in names:
                week = by_model[n].get(sku)
                cells.append("n/a" if week is None else f"**{week}**" if week in d["peak_weeks"] else week)
            w(f"| {sku} | " + " | ".join(cells) + " |")
    w("")
