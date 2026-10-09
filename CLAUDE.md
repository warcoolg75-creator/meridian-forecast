# Meridian Forecast

A planner logs in, sees how each product is selling and where, gets an ML forecast of
demand for the next 1–26 weeks, is warned when a peak season is approaching, and turns
that into a production plan.

The project is built in 10 phases. Build only what the current phase asks for.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- PostgreSQL 16 (SQLite fallback via env var)
- pandas / numpy for data work

## Conventions

- Money is stored as integer minor units (`*_minor`, paise for INR).
- Quantities are integers.
- Dates and timestamps are ISO-8601, UTC.
- Every API response is a Pydantic model. Documented exception: file downloads
  (`GET /api/v1/imports/sales/template` returns `text/csv`).
- Every endpoint ships with a pytest test in the same change.

## Commands (run from the repo root)

- `make venv` / `make migrate` / `make seed` / `make rollup` / `make test` / `make run`
- On Windows `make` is not on PATH: use `C:\msys64\usr\bin\make.exe`, or run the
  wrapped command directly, e.g. `cd backend && python -m app.cli seed`.
- `make seed` always regenerates the **pinned dataset**: seed 42, history
  2023-10-09..2026-10-08 (`SEED` / `END_DATE` in the Makefile, `DEFAULT_SEED` /
  `DEFAULT_END_DATE` in `backend/app/seed/ground_truth.py`; a test keeps them in sync).
  Same bytes every run, every day. `make seed END_DATE=...` exists only for deliberate
  regeneration, after which the new `ground_truth.json` must be committed.

## Environment notes

- **No Docker, no docker-compose.** There is no Docker on the dev machine; ignore any
  earlier assumption of a docker-compose stack. Local dev runs on SQLite; PostgreSQL 16
  is exercised against a hosted database (Neon/Supabase) via `TEST_DATABASE_URL`.
- The virtualenv lives outside the repo (`%USERPROFILE%\.virtualenvs\meridian`, the
  Makefile's `VENV`). With Windows long paths disabled, Prophet (phase 5) cannot be
  installed into a venv inside this folder: its deepest file path exceeds 260 chars.
  Prophet 1.5, LightGBM 4.7, statsmodels 0.15 and scikit-learn 1.9 are installed in that
  venv (`ml` extra) and verified to fit there, despite the space in "Skanda V".
- **The em dash in this folder's name breaks native (C/C++) file I/O.** Windows' ANSI code
  page is 1252: LightGBM `save_model`/`model_file=` on a path inside the repo fails, and
  CmdStan (Prophet) writes the path into its CSV header as cp1252, which cmdstanpy cannot
  parse. Rules: never pass an `output_dir` inside the repo to Prophet/cmdstanpy (the
  default %TEMP% dir is fine); persist LightGBM with `model_to_string()` + Python file
  I/O or joblib; pure-Python I/O (json, pickle, joblib, sqlite3) is fine anywhere.
  Compiling Stan models (cmdstan's make) would also choke on the space in the venv path;
  Prophet ships a precompiled model, so do not compile.
- `DATABASE_URL` unset = SQLite at `backend/meridian.db`. `TEST_DATABASE_URL` (env or
  repo-root `.env`, gitignored) pointing at PostgreSQL runs the whole suite there plus the
  cross-dialect tests; unset, those tests are skipped (never delete them). The PG fixture
  drops only this project's tables, never the schema.

## Design rules established in phase 1

- Enums are VARCHAR + one named CHECK constraint (`app/models/base.py:enum_type`), not
  native PG enums. When autogenerating migrations, check for duplicated CHECKs.
- `daily_sales` is a rollup keyed by (date, product, region, channel). `source='orders'`
  rows belong to the rollup (`app/services/rollup.py`, idempotent delete + re-insert);
  `source='import'` rows come from CSV and are never overwritten by the rollup.
- Date bucketing in SQL goes through `app/services/bucketing.py`: every new bucketing
  expression needs a compiler for both `postgresql` and `sqlite` and a case in
  `tests/test_bucketing_dialects.py`.
- Seed data must stay deterministic: RNG streams are `(seed, stream, product_index)`,
  numpy and holidays are pinned exactly in `backend/pyproject.toml`, and
  `ground_truth.json` is written with sorted keys and LF endings.
- `backend/app/seed/ground_truth.json` is committed and is what phase 5 scores against.
  `test_committed_ground_truth_matches_the_pinned_generator` fails if anything changes it.
- `app/seed/ground_truth.py:expected_cell_demand` is the single definition of expected
  demand; the forecaster scoring phase should import it, not re-derive it. Note that
  supply shocks are part of that expectation but are unforecastable by design: decide in
  phase 5 whether to score shock days or mask them.
- Festival dates come from the `holidays` package; the only hardcoded (unverified) ones
  are Dhanteras in `app/seed/festivals.py`.
