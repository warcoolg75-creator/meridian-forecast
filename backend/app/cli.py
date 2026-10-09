"""Command-line entry points.

    python -m app.cli seed   [--seed 42] [--end-date 2026-10-08] [--years 3]   (defaults = the pinned dataset)
    python -m app.cli rollup [--date-from YYYY-MM-DD] [--date-to YYYY-MM-DD]
"""

import argparse
import sys
from datetime import date

from alembic import command
from alembic.config import Config

from app.config import BACKEND_DIR
from app.db import get_engine, get_sessionmaker
from app.seed.generate import format_report, generate
from app.seed.ground_truth import DEFAULT_END_DATE, DEFAULT_SEED
from app.services.rollup import rebuild_daily_sales


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
          f"skipped {result.skipped_for_imports:,} cells that have imported rows")
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

    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):  # a cp1252 console must not crash on a non-ASCII name
        sys.stdout.reconfigure(errors="replace")
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
