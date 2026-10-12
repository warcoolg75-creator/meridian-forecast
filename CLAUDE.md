# Meridian Forecast

A planner logs in, sees how each product is selling and where, gets an ML forecast of
demand for the next 1–26 weeks, is warned when a peak season is approaching, and turns
that into a production plan.

The project is built in 10 phases. Build only what the current phase asks for.
Phase 1 is closed (2026-10-12). Phase 0, the frontend scaffold and design system, was
deferred until after it and is closed (2026-10-13). Phase 2 has not started.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- PostgreSQL 17.11, the hosted version everything is verified against (SQLite fallback
  via env var)
- pandas / numpy for data work
- Frontend (`frontend/`): React 18, React Router 7, TypeScript 6, Vite 8, Tailwind CSS 4,
  TanStack Query 5, Recharts. These are pinned as a set: see below.

## Frontend version set (pinned together; do not upgrade one alone)

The versions in `frontend/package.json` depend on each other. Each pin below has a reason;
an "obvious" upgrade of one of them breaks the set. Change one only together with what
its reason names, and re-run `make build` and `make lint`.

| Package | Pinned | Why |
|---|---|---|
| React, react-dom, @types/react(-dom), react-is | 18 | The version chosen for this project. React 19 is a deliberate migration (it is also what React Router 8 needs), not a routine bump. react-is is pinned to 18 so Recharts runs against the same React major. |
| React Router | 7 | React Router 8 requires React >= 19.2.7. Upgrade it only together with React 19. |
| TypeScript | ~6.0 | typescript-eslint (the ESLint TypeScript plugin) supports TypeScript < 6.1. TypeScript 7, or even 6.1, breaks `npm run lint`, and `npm run build` runs lint first. Hence `~6.0`, not `^6`. |
| Vite | 8 | @vitejs/plugin-react 6 requires Vite 8. @tailwindcss/vite supports Vite up to 8: check its peer range before moving to 9. Vite 8 needs Node ^20.19 or >= 22.12 (`engines`). |
| Tailwind CSS (+ @tailwindcss/vite) | 4 | The design system is built on Tailwind 4's `@theme`: `tokens.css` is the theme and there is no config file. Tailwind 3 has no `@theme`, so going back means a second, mirrored config. |

## Conventions

- Money is stored as integer minor units (`*_minor`, paise for INR).
- Quantities are integers.
- Dates and timestamps are ISO-8601, UTC.
- Every API response is a Pydantic model. Documented exception: file downloads
  (`GET /api/v1/imports/sales/template` returns `text/csv`).
- Every endpoint ships with a pytest test in the same change.

## Commands (run from the repo root)

- `make venv` / `make migrate` / `make seed` / `make rollup` / `make test` / `make run`
- Frontend: `make dev` (API on :8000 plus Vite on http://127.0.0.1:5173, which proxies
  `/api`), `make web` (Vite only), `make build` (token checks, ESLint, type check, then
  `frontend/dist`), `make lint` (token checks, ESLint, Prettier). These run `npm ci` first
  whenever `frontend/package-lock.json` changes. `make hooks` installs pre-commit into the
  venv and enables `.pre-commit-config.yaml` (frontend hooks only so far).
- On Windows `make` is not on PATH: use `C:\msys64\usr\bin\make.exe`, or run the
  wrapped command directly, e.g. `cd backend && python -m app.cli seed`. Run it from
  PowerShell (see the PATH note under Environment notes for the frontend targets).
- With `.env` present, `make test` runs against the hosted PostgreSQL (and wipes its
  seeded data). For a SQLite-only run: `$env:TEST_DATABASE_URL = 'sqlite-only-run'` first.
- `make seed` always regenerates the **pinned dataset**: seed 42, history
  2023-10-09..2026-10-08 (`SEED` / `END_DATE` in the Makefile, `DEFAULT_SEED` /
  `DEFAULT_END_DATE` in `backend/app/seed/ground_truth.py`; a test keeps them in sync).
  Same bytes every run, every day. `make seed END_DATE=...` exists only for deliberate
  regeneration, after which the new `ground_truth.json` must be committed.

## Environment notes

- **No Docker, no docker-compose.** There is no Docker on the dev machine; ignore any
  earlier assumption of a docker-compose stack. Local dev runs on SQLite; PostgreSQL 17
  is exercised against a hosted database (Neon/Supabase) via `TEST_DATABASE_URL`.
- **On Windows the frontend make targets prepend MSYS's `/usr/bin` to PATH, so npm
  resolves.** Make run from PowerShell inherits the Windows PATH, which lacks
  `C:\msys64\usr\bin`. npm's launcher in `C:\Program Files\nodejs` is a bash script
  (`#!/usr/bin/env bash`), so without bash on PATH every npm recipe died with make's
  "Error 127" (command not found). The Makefile sets `export PATH := /usr/bin:$(PATH)` for
  `dev`, `web`, `build`, `lint` and the `npm ci` stamp target, on Windows only: on Linux
  or macOS the prepend could shadow a newer Node (e.g. from nvm). Backend targets do not
  need it because they call the venv's Python by absolute path. Do not remove it because
  `npm` works in your own shell: that shell has a different PATH from make's.
- The virtualenv lives outside the repo (`%USERPROFILE%\.virtualenvs\meridian`, the
  Makefile's `VENV`). With Windows long paths disabled, Prophet (phase 5) cannot be
  installed into a venv inside this folder: its deepest file path exceeds 260 chars.
  Prophet 1.5, LightGBM 4.7, statsmodels 0.15 and scikit-learn 1.9 are installed in that
  venv (`ml` extra) and verified to fit there, despite the space in "Skanda V".
- **Historical, does not apply to the current path:** the repo used to live in a folder
  whose name contained an em dash, and that broke native (C/C++) file I/O. It now lives at
  `D:\For college\college\projects\meridian-forecast` (pure ASCII; spaces are fine).
  Re-tested 2026-10-11: LightGBM `save_model` + `Booster(model_file=)` and Prophet
  `fit(output_dir=...)` + CSV read-back both work with output inside the repo, including
  file and folder names with spaces. If the repo is ever moved to a non-ASCII path again,
  the old rules return: Windows' ANSI code page is 1252, so LightGBM `save_model` fails and
  CmdStan writes the path into its CSV header as cp1252, which cmdstanpy cannot parse;
  keep Prophet's `output_dir` in %TEMP% and persist LightGBM with `model_to_string()`.
- Still current: compiling Stan models (cmdstan's make) would choke on the space in the
  venv path; Prophet ships a precompiled model, so do not compile.
- After moving the repo, re-run `pip install -e . --no-deps` from `backend/`: the venv's
  editable install stores the absolute source path.
- `DATABASE_URL` unset = SQLite at `backend/meridian.db`. `TEST_DATABASE_URL` (env or
  repo-root `.env`, gitignored) pointing at PostgreSQL runs the whole suite there plus the
  cross-dialect tests; unset, those tests are skipped (never delete them). The PG fixture
  drops only this project's tables, never the schema. The file must be named exactly
  `.env`: Notepad's `.env.txt` is neither read by the app nor covered by `.gitignore`.
- The hosted test database is Supabase, reached through the **session pooler** in
  ap-south-1 (port 5432). Do not switch to the direct endpoint: it is IPv6-only on the
  free tier and does not resolve from the dev network. `SELECT version()` (2026-10-11):
  `PostgreSQL 17.11 on x86_64-pc-linux-gnu, compiled by gcc (GCC) 15.2.0, 64-bit`.
  That is the target version (it replaced the original PostgreSQL 16 target, which was
  never verified). Collation is `en_US.UTF-8` while SQLite compares
  bytes, so `ORDER BY` on strings can differ between the two once codes put punctuation
  in different positions; today's SKUs and region codes sort identically.
- That database is also the PG fixture's scratch space: with `.env` present, `make test`
  drops and recreates the tables, wiping anything `make seed` put there. The full suite
  takes ~7-9 min there. `make seed` against it is network-bound: 58-148 s measured over
  Wi-Fi (vs ~10-13 s on SQLite), and one run lost its connection mid-insert (the seed is
  one transaction, so it rolled back cleanly; rerun it). The pinned dataset takes
  ~106 MB of the free tier's 500 MB.

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
- Row-level security: migration 0002 enables RLS on every table on PostgreSQL (no-op on
  SQLite), without FORCE and without policies, so Supabase's Data API roles (`anon`,
  `authenticated`) see no rows while the app, connecting as the tables' owner, is
  unaffected. Every migration that creates a table must enable RLS on it too;
  `tests/test_row_level_security.py` fails on PostgreSQL otherwise.
- Reading `.rowcount` of an INSERT needs `execution_options={"preserve_rowcount": True}`:
  SQLAlchemy 2.1 keeps rowcount only for UPDATE/DELETE, and psycopg 3.3 resets it when
  the cursor closes, so it reads -1 on PostgreSQL (SQLite happens to keep it).

## Design system (frontend)

- **Tokens live in one file, `frontend/src/styles/tokens.css`**: a Tailwind 4
  `@theme static` block, with no `tailwind.config`. Each variable is both a CSS custom
  property and the source of a utility: `--color-maroon-500` -> `bg-maroon-500`,
  `--text-step-2` -> `text-step-2`, `--spacing-4` -> `p-4`, `--radius-card` ->
  `rounded-card`, `--shadow-rest` -> `shadow-rest`.
- **No hex codes outside tokens.css**, anywhere in the repo (CLAUDE.md included). Frontend
  code outside it may not use colour functions either: new colours are derived in
  tokens.css by mixing palette colours, never invented. `frontend/scripts/check-tokens.mjs`
  enforces both.
- **Maroon means primary action or brand, never "bad".** Errors, losses, shortfalls and
  destructive actions are clay.
- **Sage, amber and clay carry positive, warning and negative**, and nothing else: not
  decoration, not chart categories.
- **Contrast rule (WCAG AA, normal-size text needs 4.5:1 against cream-50):** ink-400
  (3.33:1) and amber-600 (3.68:1) fail and must never be used for readable text.
  - ink-400 is for placeholders (never the only label), disabled text, control borders
    (it meets the 3:1 a control outline needs) and decorative icons.
  - amber-600 is for warning icons, status dots, borders, and badge fills that carry no
    text. Text on a solid amber-600 fill fails with every palette colour (cream-50
    3.68:1, ink-900 4.39:1), so warning badges are the amber-100 tint with amber-800 text
    and an amber-600 dot.
  - **Warning text uses `text-warning-text`: amber-800 (6.16:1),** amber-600 mixed 65%
    with ink-900 in tokens.css. On the amber-100 tint it is 5.39:1.
  - maroon-300 (3.85:1), maroon-100, the creams and the -100 tints fail as text too. Only
    colours marked "AA pass" on `/styleguide` may carry readable text.
- **Components use the semantic aliases** (`bg-canvas`, `bg-surface`, `border-line`,
  `border-line-strong`, `text-fg`, `text-fg-muted`, `bg-primary`, `text-positive`,
  `text-warning-text`, `text-negative`, ...). Raw palette names are for the styleguide and
  rare one-offs.
- **Off-palette or off-scale fails the build.** tokens.css resets Tailwind's default
  colours, fonts, weights, text sizes, leading, spacing, radii and shadows, so only token
  utilities exist. Tailwind silently ignores unknown classes, so ESLint
  (`better-tailwindcss/no-unknown-classes`) makes them errors. It also bans arbitrary
  values (`p-[13px]`, `bg-(--x)`) and inline `style` props; the styleguide is the one
  exception for `style`, because it renders tokens discovered at runtime. `npm run build`
  runs check-tokens and ESLint before Vite.
- Type: Fraunces for headings (h1-h4 get it by default) and Inter for body text and every
  number. **Every number shown as data uses the `figure` utility** (Inter, tabular lining
  figures, even inside a heading): KPIs, deltas, table cells, axis labels. Tables, inputs,
  `output`, `data` and `time` get tabular figures by default. Prose does not: Inter's
  tabular feature also widens the hyphen to digit width, which opens gaps in words like
  "cream-50". Sizes are named steps only: `text-step-n2` (12px), `text-step-n1` (14px), `text-step-0` (16px body),
  then `text-step-1` to `text-step-5`, which scale between a 360px and a 1440px viewport.
- Spacing is a 4px scale: steps 0-6, 8, 10, 12, 16, 20 and 24 (`p-4` = 16px), nothing in
  between. Radius: `rounded-control` 6px (buttons, inputs), `rounded-card` 8px,
  `rounded-full`. Shadows: `shadow-rest`, `shadow-raised` and `shadow-overlay`, tinted
  from ink-900 at 4-12% opacity.
- Cards are `<Card>`: cream-50 surface, cream-200 hairline, `shadow-rest`. There is no
  white in the palette.
- `/styleguide` (lazy-loaded, linked from nowhere) renders every token from the live
  stylesheet with its contrast verdict. Check it before a page uses a new token.

## Known issues

- **`/sales/daily` deep pagination re-runs the full aggregation for every page.** Each
  request recomputes the count and the whole GROUP BY, then OFFSETs into it. Paging
  through the day-level sku x region x channel breakdown (207,981 rows, 21 pages of
  10,000) took 255 s on the hosted PostgreSQL vs 31 s on SQLite (2026-10-11). Results are
  correct; only speed suffers. Fix in phase 4, when the dashboard starts querying
  `/sales/daily`: likely keyset pagination or a cached aggregate. Deliberately not fixed
  in phase 1.
