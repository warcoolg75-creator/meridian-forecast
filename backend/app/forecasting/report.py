"""docs/backtest-report.md, generated from the latest backtest run and, when there is one
from that backtest, the latest production run. Every number comes from the database, so
`make backtest` and `make forecast` both regenerate it; edit this module, not the file."""

import statistics
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
from app.forecasting.backtest import CHAMPION, ORACLE, REPORTED_HORIZONS
from app.forecasting.metrics import skill
from app.forecasting.models import BASELINE, MODEL_NAMES
from app.forecasting.scoring import FESTIVE_CATEGORIES
from app.forecasting.store import latest_run
from app.models import BacktestMetric, ForecastRunKind, Product

REPORT_PATH = REPO_ROOT / "docs" / "backtest-report.md"
TARGET = 0.15
COVERAGE_BAND = (0.75, 0.85)
LABEL = {"seasonal_naive": "Seasonal naive", "ets": "ETS", "prophet": "Prophet", "lightgbm": "LightGBM",
         CHAMPION: "Champions", ORACLE: "Oracle (expected demand)"}


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


def write_report(session: Session) -> Path:
    REPORT_PATH.parent.mkdir(exist_ok=True)
    REPORT_PATH.write_text(build_report(session), encoding="utf-8", newline="\n")
    return REPORT_PATH


def build_report(session: Session) -> str:
    run = latest_run(session, ForecastRunKind.BACKTEST)
    if run is None:
        return "# Backtest report\n\nNo backtest run yet: `make backtest`.\n"
    production = latest_run(session, ForecastRunKind.PRODUCTION)
    if production is not None and production.params.get("backtest_run_id") != run.id:
        production = None
    rows = session.execute(
        sa.select(BacktestMetric, Product.sku).outerjoin(Product, Product.id == BacktestMetric.product_id)
        .where(BacktestMetric.run_id == run.id)
    ).all()
    frame = pd.DataFrame([{
        "model": m.model, "sku": sku, "window": m.window.value, "shocks": m.shocks.value, "horizon": m.horizon,
        "n_weeks": m.n_weeks, "wape": m.wape, "bias": m.bias, "mase": m.mase,
        "coverage_80": m.coverage_80, "coverage_95": m.coverage_95,
    } for m, sku in rows])
    festive = set(session.scalars(sa.select(Product.sku).where(Product.category.in_(FESTIVE_CATEGORIES))))
    return "\n".join(_sections(Metrics(frame), run, run.params, production, festive))


def _sections(m: Metrics, run, p: dict, production, festive: set[str]) -> list[str]:
    headline, short = p["headline_skus"], p["short_history_skus"]
    champions = p["champions"]
    held = (p["held_out_start"], run.training_cutoff.isoformat())
    head_skill = m.skill(CHAMPION)
    champ_wape, naive_wape = m.get(CHAMPION, "wape"), m.get(BASELINE, "wape")
    median_skill = m.median_sku_skill(CHAMPION, headline)
    per_sku = {s: m.skill(CHAMPION, sku=s) for s in headline}
    losers = sorted(s for s, v in per_sku.items() if v is not None and v <= 0)
    weak = sorted(s for s, v in per_sku.items() if v is not None and 0 < v < TARGET)
    model_wapes = {name: m.get(name, "wape") for name in MODEL_NAMES}
    best_single = min((n for n in MODEL_NAMES if model_wapes[n] is not None), key=lambda n: model_wapes[n])
    cov80 = m.get(CHAMPION, "coverage_80")
    oracle_wape = m.get(ORACLE, "wape")
    met = head_skill is not None and head_skill >= TARGET
    out: list[str] = []
    w = out.append

    w("# Backtest report: weekly demand forecasts (phase 5a)\n")
    w(f"Generated from backtest run {run.id} ({run.trained_at:%Y-%m-%d %H:%M} UTC)"
      + (f" and forecast run {production.id}" if production else "")
      + f". Pinned dataset, sales to {run.data_end_date}; the last complete week starts {run.training_cutoff}. "
      f"`make backtest` took {run.duration_seconds:.0f} s on the dev laptop. Regenerated by `make backtest` and "
      "`make forecast`; edit `backend/app/forecasting/report.py`, not this file.\n")

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
      "champions were picked on, so it flatters them), and the forward oracle test scores the production "
      "forecast across Diwali 2026 against expected demand.\n")
    w(f"Pooled WAPE is volume-weighted: the bearing (about 5,000 units a week) dominates it and the Gift Box "
      f"(about 20) barely registers. Per SKU, the median skill is {pct(median_skill)}"
      + (f"; the champion does not beat seasonal naive on {', '.join(losers)}" if losers else "")
      + (f"; it beats it by less than 15% on {', '.join(weak)}" if weak else "")
      + f". The oracle, which knows the true expected demand, scores {pct(oracle_wape)}: what is left between it "
      f"and the champions is still reducible. The champions' 80% intervals cover {pct(cov80)} of held-out weeks "
      f"(target 75-85%); **not a fully clean held-out number**: the interval method was changed because of the "
      f"first held-out result (see Intervals).\n")

    w("## What worked and what didn't\n")
    if best_single != CHAMPION and model_wapes[best_single] is not None and champ_wape is not None \
            and model_wapes[best_single] < champ_wape:
        w(f"- **Picking a champion per SKU did worse than using {LABEL[best_single]} everywhere** on the held-out "
          f"window (WAPE {pct(champ_wape)} against {pct(model_wapes[best_single])}). The per-SKU pick was made on "
          "the selection window, where several SKUs' winners were decided by small margins; on fresh weeks some "
          "of them lost. Not changed after seeing this: re-picking on the held-out window would make its "
          "headline meaningless. A pick that needs a clear margin, or one model for all, is the thing to test "
          "next, on the selection window.")
    for name in MODEL_NAMES:
        if name == BASELINE:
            continue
        s = m.skill(name)
        w(f"- {LABEL[name]}: held-out WAPE {pct(model_wapes[name])}, {pct(s)} lower than seasonal naive; "
          f"selection window {pct(m.get(name, 'wape', 'selection'))}.")
    w(f"- Seasonal naive is biased low ({pct(m.get(BASELINE, 'bias'), True)} held-out): it repeats last year and "
      "misses growth. It also cannot move a festival: Diwali was 11 days earlier in 2025 than in 2024.")
    shock = p["notes"].get("after_shock", {})
    if shock:
        parts = [f"{LABEL[n]} {pct(v['after_shock'])} against {pct(v['otherwise'])}" for n, v in shock.items()
                 if n != ORACLE and v["after_shock"] is not None]
        w(f"- **A supply shock in the last training week drags the next forecasts down.** WAPE at horizons 1-4 "
          f"when the week before the origin was a shock week ({shock[BASELINE]['after_shock_weeks']} forecast-weeks "
          f"per model), against every other origin: {'; '.join(parts)}. Shocks are not forecastable and are "
          "never an input, but a model should not carry one forward: ETS on the log scale moves least, "
          "LightGBM's last-weeks lags and Prophet's trend carry it. Example: the bearing's week of 2026-08-31 "
          "sold 667 units against about 8,000; at the next origin LightGBM forecast 2,825 for a week that sold "
          "8,226. Not fixed here (it was found on the held-out window); a shock-robust level, such as a 13-week "
          "median instead of a mean, is the change to test on the selection window.")
    lgbm_cover = _champion_coverage(m, [s for s, c in champions.items() if c == "lightgbm"], "coverage_80")
    if lgbm_cover is not None and not COVERAGE_BAND[0] <= lgbm_cover <= COVERAGE_BAND[1]:
        w(f"- **LightGBM's 80% intervals miss the 75-85% band** where it is champion ({pct(lgbm_cover)}); the Air "
          f"Fryer pulls it down ({pct(m.get(CHAMPION, 'coverage_80', sku='KIT-AFR-45'))}): a new product's errors "
          "are wider than the long-history SKUs' errors its pooled intervals come from. Reported, not "
          "recalibrated on the held-out window.")
    if production is not None:
        failed = [r for r in production.params["forward_oracle"]["diwali"]["skus"] if not r["pass"]]
        for r in failed:
            w(f"- **{r['sku']} misses the Diwali 2026 peak**: its champion ({LABEL[r['model']]}) peaks in the week "
              f"of {r['champion_peak']}; expected demand peaks in the week of {r['expected_peak']}"
              + (" (ETS has no calendar: it repeats last year's shape)." if r["model"] == "ets" else "."))
    w("- Champions per SKU: " + ", ".join(f"{s} {LABEL[c]}" for s, c in sorted(champions.items())) + ".")
    if short:
        w(f"- Short history, outside the headline: {', '.join(short)} (launched Feb 2026, no seasonal-naive "
          "forecast exists before Feb 2027). LightGBM only, its yearly pattern borrowed from its category: "
          f"held-out WAPE {pct(m.get(CHAMPION, 'wape', sku=short[0]))}, 80% coverage "
          f"{pct(m.get(CHAMPION, 'coverage_80', sku=short[0]))}.")
    w("")

    w("## Leaderboard\n")
    w("Pooled over the headline SKUs, horizons 1-26, all weeks. Skill = 1 - WAPE / seasonal naive's WAPE. "
      "MASE: mean absolute error over the in-sample seasonal-naive error of each training history (below 1 "
      "beats last year's actuals on the training data). Coverage is measured on the held-out window only; "
      "on the selection window the intervals were calibrated.\n")
    w("| Model | Held-out WAPE | Skill | Median per-SKU skill | Bias | MASE | 80% cov. | 95% cov. "
      "| Selection WAPE | Selection skill |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for name in (*MODEL_NAMES, CHAMPION, ORACLE):
        w(f"| {LABEL[name]} | {pct(m.get(name, 'wape'))} | {pct(m.skill(name), True) if name != BASELINE else '-'} "
          f"| {pct(m.median_sku_skill(name, headline), True) if name != BASELINE else '-'} "
          f"| {pct(m.get(name, 'bias'), True)} | {num(m.get(name, 'mase'))} | {pct(m.get(name, 'coverage_80'))} "
          f"| {pct(m.get(name, 'coverage_95'))} | {pct(m.get(name, 'wape', 'selection'))} "
          f"| {pct(m.skill(name, 'selection'), True) if name != BASELINE else '-'} |")
    w("")

    w("## Champion against seasonal naive, per SKU (held-out)\n")
    w("| SKU | Champion | Champion WAPE | Seasonal naive WAPE | Skill | Bias | 80% cov. | 95% cov. | Weeks |")
    w("|---|---|---|---|---|---|---|---|---|")
    for sku in sorted(champions):
        w(f"| {sku}{' (short history)' if sku in short else ''} | {LABEL[champions[sku]]} "
          f"| {pct(m.get(CHAMPION, 'wape', sku=sku))} | {pct(m.get(BASELINE, 'wape', sku=sku))} "
          f"| {pct(m.skill(CHAMPION, sku=sku), True)} | {pct(m.get(CHAMPION, 'bias', sku=sku), True)} "
          f"| {pct(m.get(CHAMPION, 'coverage_80', sku=sku))} | {pct(m.get(CHAMPION, 'coverage_95', sku=sku))} "
          f"| {int(m.get(CHAMPION, 'n_weeks', sku=sku) or 0)} |")
    w(f"\nMedian per-SKU skill: **{pct(median_skill)}** (pooled: {pct(head_skill)}). 'Weeks' counts forecast-"
      "weeks: each of the 13 held-out weeks is forecast from up to 9 origins.\n")

    w("## By horizon (held-out, pooled)\n")
    w("| Horizon | " + " | ".join(LABEL[n] for n in (*MODEL_NAMES, CHAMPION, ORACLE)) + " | Champion skill |")
    w("|---|" + "---|" * (len(MODEL_NAMES) + 3))
    for h in REPORTED_HORIZONS:
        w(f"| {h} | " + " | ".join(pct(m.get(n, 'wape', horizon=h)) for n in (*MODEL_NAMES, CHAMPION, ORACLE))
          + f" | {pct(m.skill(CHAMPION, horizon=h), True)} |")
    w("\nEach horizon has only about 3 origins x 11 SKUs in the held-out window; the pooled 1-26 figure is the "
      "stable one.\n")

    w("## The oracle floor\n")
    w("The oracle forecasts the ground truth's expected demand, so its error is pure Poisson sampling noise: "
      "the floor no model can beat. 'Reducible' is how much of seasonal naive's excess error over the floor the "
      "champions remove: (naive - champion) / (naive - oracle).\n")
    w("| Window | Oracle | Champions | Seasonal naive | Reducible error removed |")
    w("|---|---|---|---|---|")
    for window, label in (("held_out", "Held-out"), ("selection", "Selection"), ("festive_2025", "Festive 2025")):
        o, c, n = m.get(ORACLE, "wape", window), m.get(CHAMPION, "wape", window), m.get(BASELINE, "wape", window)
        removed = (n - c) / (n - o) if None not in (o, c, n) and n != o else None
        w(f"| {label} | {pct(o)} | {pct(c)} | {pct(n)} | {pct(removed)} |")
    w("")

    w("## With and without supply-shock weeks\n")
    w("Shock weeks (from the ground truth: a SKU-week holding any day of that SKU's supply shock) are not "
      "forecastable by design. Scored both ways:\n")
    w("| Model | Held-out, all weeks | Held-out, no shock weeks | Selection, all weeks | Selection, no shock weeks |")
    w("|---|---|---|---|---|")
    for name in (*MODEL_NAMES, CHAMPION, ORACLE):
        w(f"| {LABEL[name]} | {pct(m.get(name, 'wape'))} | {pct(m.get(name, 'wape', shocks='excluded'))} "
          f"| {pct(m.get(name, 'wape', 'selection'))} | {pct(m.get(name, 'wape', 'selection', 'excluded'))} |")
    w(f"\nChampion skill without shock weeks: {pct(m.skill(CHAMPION, shocks='excluded'))} held-out.\n")

    w("## Festive season 2025 (selection window: not a held-out result)\n")
    w(f"Target weeks Sep-Nov 2025. **These weeks are in the selection window**: the champions were picked on "
      f"them, so their scores here are flattered. The first origin is w/c 2025-10-06, so the earliest scored "
      f"week is {p['notes']['festive_first_target']}; September 2025 is before any origin. Diwali 2025 was 20 Oct.\n")
    w("| Model | WAPE | Skill vs seasonal naive | Bias |")
    w("|---|---|---|---|")
    for name in (*MODEL_NAMES, CHAMPION, ORACLE):
        w(f"| {LABEL[name]} | {pct(m.get(name, 'wape', 'festive_2025'))} "
          f"| {pct(m.skill(name, 'festive_2025'), True) if name != BASELINE else '-'} "
          f"| {pct(m.get(name, 'bias', 'festive_2025'), True)} |")
    festive_skus = [s for s in headline if s in festive]
    w("\nPer festive SKU (Packaged Foods and Kitchen Appliances):\n")
    w("| SKU | Champion | Champion WAPE | Seasonal naive WAPE | Skill |")
    w("|---|---|---|---|---|")
    for sku in festive_skus:
        w(f"| {sku} | {LABEL[champions[sku]]} | {pct(m.get(CHAMPION, 'wape', 'festive_2025', sku=sku))} "
          f"| {pct(m.get(BASELINE, 'wape', 'festive_2025', sku=sku))} "
          f"| {pct(m.skill(CHAMPION, 'festive_2025', sku=sku), True)} |")
    w("")

    w("## Intervals\n")
    check = p["notes"]["interval_check"]
    w("Every model's 80% and 95% intervals come from its own backtest errors, log((actual + 1) / (forecast + 1)), "
      "as empirical quantiles per model and horizon group (1-4, 5-13, 14-26), pooled across SKUs. The held-out "
      "window's intervals use selection-window errors only; production uses every backtest error.\n")
    w("**Recalibrated once, and the held-out result is what triggered it.** The first version used quantiles per "
      "SKU, and its held-out coverage came out low (champions 67.5% at 80%, backtest run 1). That result is why "
      "the method was revisited. The replacement was then chosen on a split inside the selection window "
      f"(calibrated on targets before {check['calibrated_before']}, measured on the rest), where the same failure "
      "showed: a SKU's champion is picked because its selection errors were small, so those errors understate "
      "what comes next. Choosing on the selection window does not undo the trigger: **the held-out coverage of "
      "the pooled method is not a fully clean held-out number**, because the held-out window had already been "
      "seen when the method changed. Both versions:\n")
    w("| Method | Champions' 80%, selection split | 95%, selection split | Champions' 80%, held-out |")
    w("|---|---|---|---|")
    w(f"| Per SKU (first version) | {pct(check['per_sku']['coverage_80'])} | {pct(check['per_sku']['coverage_95'])} "
      "| 67.5% (backtest run 1) |")
    w(f"| Pooled per model (used) | {pct(check['pooled']['coverage_80'])} | {pct(check['pooled']['coverage_95'])} "
      f"| {pct(cov80)} (measured after the change) |")
    w("\nHeld-out coverage with the pooled method:\n")
    w("| Champion model | SKUs | 80% coverage | In 75-85%? | 95% coverage |")
    w("|---|---|---|---|---|")
    by_model: dict[str, list[str]] = {}
    for sku, c in champions.items():
        by_model.setdefault(c, []).append(sku)
    for model_name, skus in sorted(by_model.items()):
        # Coverage of this model's forecasts on the SKUs it is champion for.
        c80 = _champion_coverage(m, skus, "coverage_80")
        c95 = _champion_coverage(m, skus, "coverage_95")
        inside = c80 is not None and COVERAGE_BAND[0] <= c80 <= COVERAGE_BAND[1]
        w(f"| {LABEL[model_name]} | {', '.join(sorted(skus))} | {pct(c80)} | {'yes' if inside else '**no**'} "
          f"| {pct(c95)} |")
    inside_skus = [s for s in champions if (v := m.get(CHAMPION, "coverage_80", sku=s)) is not None
                   and COVERAGE_BAND[0] <= v <= COVERAGE_BAND[1]]
    w(f"\nAll champions pooled: {pct(cov80)} at 80%, {pct(m.get(CHAMPION, 'coverage_95'))} at 95%. Per SKU "
      f"(table above) {len(inside_skus)} of {len(champions)} land in 75-85%; a single SKU's held-out window is "
      "13 weeks, so one bad week moves its coverage by up to 9 forecast-weeks. The champion's p50 falls outside "
      f"its own 80% interval in {pct(p['notes']['champion_p50_outside_80'])} of held-out forecasts (the p50 is "
      "never moved into it).\n")

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

    w("## Forward oracle test (production forecast against expected demand)\n")
    if production is None:
        w("No production run from this backtest yet: `make forecast`.\n")
    else:
        f = production.params["forward_oracle"]
        w(f"The production forecast (w/c {f['weeks'][0]} to {f['weeks'][1]}) spans Diwali 2026, which no backtest "
          "saw. It is scored against the ground truth's expected demand for those weeks, computed with no "
          "promotions and no shocks (the forecast's own assumptions; the generator's own function, with its "
          "window extended into the weeks its holiday list already covers). Seasonal naive's forward forecast "
          "is scored the same way. **These are errors against an expectation, not noisy actuals: they are not "
          "comparable with the backtest WAPE above.**\n")
        w("| Group | Champion WAPE | Seasonal naive WAPE | Skill |")
        w("|---|---|---|---|")
        for label, g in (("All headline SKUs", f["pooled"]), ("Festive SKUs", f["festive_pooled"])):
            w(f"| {label} ({len(g['skus'])}) | {pct(g['champion_wape'])} | {pct(g['naive_wape'])} "
              f"| {pct(g['skill'], True)} |")
        w("\n| SKU | Champion | Champion WAPE | Seasonal naive WAPE | Skill |")
        w("|---|---|---|---|---|")
        for row in f["per_sku"]:
            w(f"| {row['sku']}{' (festive)' if row['festive'] else ''} | {LABEL[row['model']]} "
              f"| {pct(row['champion_wape'])} | {pct(row['naive_wape'])} | {pct(row['skill'], True)} |")
        d = f["diwali"]
        passed = sum(r["pass"] for r in d["skus"])
        w(f"\n**Diwali 2026 ({d['date']})**: the festive buying falls in the weeks of {' and '.join(d['peak_weeks'])}. "
          f"{passed} of {len(d['skus'])} festive champions peak there:\n")
        w("| SKU | Champion | Champion's peak week | Expected demand's peak week | Seasonal naive's peak week | Pass |")
        w("|---|---|---|---|---|---|")
        for r in d["skus"]:
            w(f"| {r['sku']} | {LABEL[r['model']]} | {r['champion_peak']} | {r['expected_peak']} "
              f"| {r['naive_peak'] or 'n/a'} | {'yes' if r['pass'] else '**no**'} |")
        by_model = f.get("peaks_by_model")
        if by_model:
            w("")
            w("Every model's peak week (Sep-Dec 2026), whether or not it is the champion; in the Diwali weeks = bold:")
            w("")
            names = [n for n in MODEL_NAMES if n in by_model]
            w("| SKU | " + " | ".join(LABEL[n] for n in names) + " |")
            w("|---|" + "---|" * len(names))
            for sku in sorted(by_model[names[0]]):
                cells = []
                for n in names:
                    week = by_model[n].get(sku)
                    cells.append("n/a" if week is None else f"**{week}**" if week in d["peak_weeks"] else week)
                w(f"| {sku} | " + " | ".join(cells) + " |")
        w("")

    w("## Reproducibility\n")
    versions = ", ".join(f"{k} {v}" for k, v in sorted(run.library_versions.items()))
    w(f"- Seed {run.random_seed}; {versions}.")
    if production:
        w(f"- Production forecast digest (SHA-256 of every row): `{production.params['digest']}`. Same seed, data "
          "and versions give the same digest; `tests/test_forecast_determinism.py` checks it.")
    if p.get("warnings"):
        w(f"- Fit warnings ({len(p['warnings'])}): " + "; ".join(p["warnings"][:8])
          + (" ..." if len(p["warnings"]) > 8 else ""))
    w(f"- Origins: {', '.join(p['origins'])}. Held-out window from {p['held_out_start']}.")
    w("")
    return out


def _champion_coverage(m: Metrics, skus: list[str], field: str) -> float | None:
    """Weighted by forecast-weeks: the SKUs' champion coverage, pooled."""
    total, covered = 0, 0.0
    for sku in skus:
        value, n = m.get(CHAMPION, field, sku=sku), m.get(CHAMPION, "n_weeks", sku=sku)
        if value is not None and n:
            total += int(n)
            covered += value * n
    return covered / total if total else None
