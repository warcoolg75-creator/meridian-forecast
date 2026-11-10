"""Command-line entry points.

    python -m app.cli seed   [--seed 42] [--end-date 2026-10-08] [--years 3]   (defaults = the pinned dataset)
    python -m app.cli rollup [--date-from YYYY-MM-DD] [--date-to YYYY-MM-DD]
    python -m app.cli rollup-periods [--date-from YYYY-MM-DD] [--date-to YYYY-MM-DD]
    python -m app.cli backtest [--seed 42]   score every model at 13 rolling origins; report
    python -m app.cli forecast [--seed 42]   train the champions on all history; write a run
    python -m app.cli backtest-forecasts      store the latest backtest's held-out champion forecasts (h 1-4)
    python -m app.cli signals-backfill [--source CODE ...] [--news-from-start]
                                         external signals from 2023-10-09, news the last 90 days (context only)
    python -m app.cli signals-refresh  [--source CODE ...]   the same, incrementally
    python -m app.cli signals-status                         row counts and gaps per series

Every command masks secrets in what it prints, including an uncaught exception's
traceback (app/signals/redact.py): the FRED key travels in request URLs.
"""

import argparse
import sys
import time
import traceback
from datetime import date

from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR, get_settings
from app.db import get_engine, get_sessionmaker
from app.seed.generate import format_report, generate
from app.seed.ground_truth import DEFAULT_END_DATE, DEFAULT_SEED
from app.services.rollup import rebuild_daily_sales, rebuild_period_rollups


def upgrade_to_head() -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["configure_logger"] = False
    with get_engine().begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def _seed(args: argparse.Namespace) -> int:
    upgrade_to_head()
    with get_sessionmaker()() as session:
        report = generate(session, seed=args.seed, end_date=args.end_date, years=args.years)
    print(format_report(report))
    return 0


def _rollup(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as session, session.begin():
        result = rebuild_daily_sales(session, args.date_from, args.date_to)
    scope = f"{args.date_from or 'start'} .. {args.date_to or 'end'}"
    print(f"daily_sales rebuilt for {scope}: deleted {result.deleted:,} order rows, inserted {result.inserted:,}, "
          f"skipped {result.skipped_for_imports:,} cells that have imported rows; "
          f"rollups: {result.weekly_rows:,} weekly and {result.monthly_rows:,} monthly rows")
    return 0


def _rollup_periods(args: argparse.Namespace) -> int:
    with get_sessionmaker()() as session, session.begin():
        result = rebuild_period_rollups(session, args.date_from, args.date_to)
    scope = f"{args.date_from or 'start'} .. {args.date_to or 'end'}"
    print(f"weekly_sales and monthly_sales rebuilt from daily_sales for {scope}: "
          f"{result.weekly_rows:,} weekly and {result.monthly_rows:,} monthly rows (daily_sales untouched)")
    return 0


def _backtest(args: argparse.Namespace) -> int:
    # Imported here: the forecasting stack (Prophet, LightGBM) is the optional `ml` extra.
    from app.forecasting.backtest import run_backtest
    from app.forecasting.data import load_history
    from app.forecasting.models import all_models
    from app.forecasting.report import write_report
    from app.forecasting.store import save_backtest

    started = time.perf_counter()
    with get_sessionmaker()() as session:
        history = load_history(session)
    models = all_models()
    result = run_backtest(history, seed=args.seed, models=models, progress=print)
    duration = time.perf_counter() - started
    warnings = [f"ETS did not converge: {w}" for m in models for w in getattr(m, "convergence_warnings", [])]
    with get_sessionmaker()() as session, session.begin():
        run = save_backtest(session, history, result, args.seed, duration, warnings)
    print(f"backtest run {run.id}: {len(result.metrics)} metrics, champions {result.champions}; {duration:.0f}s")
    with get_sessionmaker()() as session:
        print(f"report: {write_report(session)}")
    return 0


def _forecast(args: argparse.Namespace) -> int:
    from app.forecasting.data import load_history
    from app.forecasting.models import ENSEMBLE, MODEL_NAMES, VERSION
    from app.forecasting.production import digest, forecast_rows, model_forecasts
    from app.forecasting.report import write_report
    from app.forecasting.scoring import forward_scores
    from app.forecasting.store import latest_run, save_production
    from app.models import ForecastRunKind

    started = time.perf_counter()
    with get_sessionmaker()() as session:
        history = load_history(session)
        backtest = latest_run(session, ForecastRunKind.BACKTEST)
        if backtest is None:
            print("No backtest run: run make backtest first (it picks each SKU's champion).", file=sys.stderr)
            return 1
        params = backtest.params
    every_model = model_forecasts(history, {*MODEL_NAMES, ENSEMBLE}, args.seed)
    rows = forecast_rows(history, params["champions"], params["interval_quantiles"], args.seed, every_model)
    run_params = {
        "version": VERSION, "backtest_run_id": backtest.id, "champions": params["champions"],
        "short_history_skus": params["short_history_skus"], "digest": digest(rows),
        "assumptions": {"promotions": "none planned after the data end", "supply_shocks": "never forecast"},
        "forward_oracle": forward_scores(history, rows, params["headline_skus"], every_model),
    }
    duration = time.perf_counter() - started
    with get_sessionmaker()() as session, session.begin():
        run = save_production(session, history, rows, run_params, args.seed, duration)
    print(f"forecast run {run.id}: {len(rows)} rows, digest {run_params['digest']}; {duration:.0f}s")
    with get_sessionmaker()() as session:
        print(f"report: {write_report(session)}")
    return 0


def _backtest_forecasts(args: argparse.Namespace) -> int:
    from app.forecasting.data import load_history
    from app.forecasting.past_forecasts import recompute, save
    from app.forecasting.store import latest_run
    from app.models import ForecastRunKind

    started = time.perf_counter()
    with get_sessionmaker()() as session:
        history = load_history(session)
        run = latest_run(session, ForecastRunKind.BACKTEST)
        if run is None:
            print("No backtest run: run make backtest first.", file=sys.stderr)
            return 1
        rows, mismatches, checked = recompute(session, history, run, args.seed, progress=print)
    if mismatches:
        print(f"Refusing to write: {len(mismatches)} of {checked} stored scores of backtest run {run.id} "
              "were not reproduced exactly:", file=sys.stderr)
        for m in mismatches[:20]:
            print(f"  {m}", file=sys.stderr)
        return 1
    with get_sessionmaker()() as session, session.begin():
        written = save(session, run.id, rows)
    print(f"backtest run {run.id}: all {checked} per-SKU held-out champion scores at h1 and h4 reproduced exactly; "
          f"wrote {written} held-out forecast-weeks (h 1-4); {time.perf_counter() - started:.0f}s")
    return 0


def _signals(mode: str):
    def handler(args: argparse.Namespace) -> int:
        from app.models import FetchMode, FetchStatus
        from app.signals.pipeline import run_signals

        upgrade_to_head()
        started = time.perf_counter()
        reports = run_signals(get_sessionmaker(), get_settings(), FetchMode(mode), only=args.source,
                              progress=lambda msg: print(msg, flush=True), fail_fast=args.fail_fast,
                              news_from_start=getattr(args, "news_from_start", False))
        changed = sum(r.counts.changed for r in reports)
        print(f"signals {mode}: {len(reports)} sources, {changed} rows inserted, updated or deleted; "
              f"{time.perf_counter() - started:.0f}s")
        bad = [r.source for r in reports if r.status in (FetchStatus.FAILED, FetchStatus.PARTIAL)]
        if bad:
            print(f"Not every source succeeded: {', '.join(bad)} (see make signals-status). The others were "
                  "stored; the app shows the failed ones as stale.", file=sys.stderr)
        return 1 if bad else 0
    return handler


def _signals_status(_args: argparse.Namespace) -> int:
    from app.signals.catalog import load_catalog
    from app.signals.status import format_status

    upgrade_to_head()
    with get_sessionmaker()() as session:
        print(format_status(session, [t.category for t in load_catalog().file.news.topics]))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    seed = commands.add_parser("seed", help="Wipe the database and regenerate all synthetic data")
    seed.add_argument("--seed", type=int, default=DEFAULT_SEED)
    seed.add_argument("--end-date", type=date.fromisoformat, default=DEFAULT_END_DATE,
                      help=f"Last day of history (default: {DEFAULT_END_DATE}, the pinned dataset whose "
                           "ground_truth.json is committed). Override only to regenerate deliberately.")
    seed.add_argument("--years", type=int, default=3)
    seed.set_defaults(handler=_seed)

    rollup = commands.add_parser("rollup", help="Rebuild daily_sales from sales_order_lines (idempotent)")
    rollup.add_argument("--date-from", type=date.fromisoformat, default=None)
    rollup.add_argument("--date-to", type=date.fromisoformat, default=None)
    rollup.set_defaults(handler=_rollup)

    periods = commands.add_parser(
        "rollup-periods",
        help="Rebuild only weekly_sales and monthly_sales from the existing daily_sales (daily_sales is not touched)")
    periods.add_argument("--date-from", type=date.fromisoformat, default=None)
    periods.add_argument("--date-to", type=date.fromisoformat, default=None)
    periods.set_defaults(handler=_rollup_periods)

    backtest = commands.add_parser("backtest", help="Score every model at 13 rolling origins; write the report")
    backtest.add_argument("--seed", type=int, default=DEFAULT_SEED)
    backtest.set_defaults(handler=_backtest)

    forecast = commands.add_parser("forecast", help="Train each SKU's champion on all history; write a run")
    forecast.add_argument("--seed", type=int, default=DEFAULT_SEED)
    forecast.set_defaults(handler=_forecast)

    past = commands.add_parser(
        "backtest-forecasts",
        help="Recompute the latest backtest and store its held-out champion forecasts (h 1-4), only if it "
             "reproduces the stored scores exactly")
    past.add_argument("--seed", type=int, default=DEFAULT_SEED)
    past.set_defaults(handler=_backtest_forecasts)

    for mode, help_text in (("backfill", "Fetch every external signal from 2023-10-09, news from the last 90 days "
                                         "(resumable)"),
                            ("refresh", "Fetch what is new since the last run, plus each source's revision window")):
        signals = commands.add_parser(f"signals-{mode}", help=help_text)
        signals.add_argument("--source", action="append", choices=["open_meteo", "fred", "wikimedia", "gdelt"],
                             help="Only this source (repeatable). Default: all four.")
        signals.add_argument("--fail-fast", action="store_true",
                             help="Stop at the first failure and raise it, instead of isolating each source")
        if mode == "backfill":
            signals.add_argument("--news-from-start", action="store_true",
                                 help="News from 2023-10-09 too, not only the last 90 days: about 52 GDELT "
                                      "requests at one a minute, enough to get an address blocked for hours")
        signals.set_defaults(handler=_signals(mode))
    status = commands.add_parser("signals-status", help="Row counts and gaps per signal series and news category")
    status.set_defaults(handler=_signals_status)

    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # a cp1252 console must not crash on a non-ASCII name
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    # Mask secrets in everything printed from here on, an uncaught traceback included.
    from app.signals.redact import install_redaction, secret_values
    guard = install_redaction(secret_values(get_settings()))
    try:
        return args.handler(args)
    except Exception:  # printed masked, as the interpreter would print it, then exit 1
        sys.stderr.write(guard.redact(traceback.format_exc()))
        sys.stderr.flush()
        return 1
    finally:
        sys.stdout.flush()
        sys.stderr.flush()


if __name__ == "__main__":
    raise SystemExit(main())
