# Meridian Forecast

A planner logs in, sees how each product is selling and where, gets an ML forecast of
demand for the next 1–26 weeks, is warned when a peak season is approaching, and turns
that into a production plan.

The project is built in 10 phases. Build only what the current phase asks for.
Phase 1 is closed (2026-10-12). Phase 0, the frontend scaffold and design system, was
deferred until after it and is closed (2026-10-13). Phase 2, the public brand page and
authentication, is built (2026-10-13). Phase 3, the app shell and the chart/KPI component
library, is built (2026-10-13). Phase 4, sales analytics, is closed (2026-11-04). Phase 5a,
the forecasting engine and backtest (backend only), is closed (2026-11-09) after v1 and one
v2 improvement round; its forecasting is frozen (see Known issues). Phase 5b, the forecast
page, has not started. Phase 10 ends with a sealed final test, planned below under
Forecasting and not to be built or looked at before then.

## Stack

- Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- Auth: pwdlib (argon2id) and PyJWT. Not passlib: it is unmaintained and reads
  `argon2.__version__`, which argon2-cffi has deprecated, so its argon2 support will break.
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
| tailwind-merge | 3 | Behind `cn()`. v3 is the line for Tailwind 4 (v2 was for 3); move it with Tailwind, and check its default theme keys (`color`, `text`, `font`, `radius`, `shadow`, `tracking`) still match what `lib/cn.ts` overrides. No dependencies of its own. |

## Conventions

- Money is stored as integer minor units (`*_minor`, paise for INR).
- Quantities are integers.
- Dates and timestamps are ISO-8601, UTC.
- Every API response is a Pydantic model. Documented exception: file downloads
  (`GET /api/v1/imports/sales/template` returns `text/csv`).
- Every endpoint ships with a pytest test in the same change.

## Commands (run from the repo root)

- `make venv` / `make migrate` / `make seed` / `make rollup` / `make test` / `make run`
- `make rollup-periods`: rebuild only `weekly_sales` / `monthly_sales` from the existing
  `daily_sales` (it never touches `daily_sales`; `make rollup` rebuilds both).
- `make backtest`: every model at 13 rolling origins; writes the metrics, each SKU's
  champion and `docs/backtest-report.md` (v2: 413 s on the dev laptop; v1 took 68-299 s,
  depending on how hard it throttles). `make forecast`: the champions trained on every
  complete week; writes a forecast run and refreshes the report (16-47 s). Backtest first: forecast refuses
  without one. Both need the `ml` extra.
- `make verify-analytics`: recompute every analytics figure in pandas straight from the
  tables and compare it with the running API (`make run` first). Exit 1 on any mismatch.
- Frontend: `make dev` (API on :8000 plus Vite on http://127.0.0.1:5173, which proxies
  `/api`), `make web` (Vite only), `make build` (token checks, ESLint, type check, then
  `frontend/dist`), `make lint` (token checks, ESLint, Prettier). These run `npm ci` first
  whenever `frontend/package-lock.json` changes. `make hooks` installs pre-commit into the
  venv and enables `.pre-commit-config.yaml` (frontend hooks only so far).
- On Windows `make` is not on PATH: use `C:\msys64\usr\bin\make.exe`, or run the
  wrapped command directly, e.g. `cd backend && python -m app.cli seed`. Run it from
  PowerShell (see the PATH note under Environment notes for the frontend targets).
- **`make test`, and any bare `pytest`, runs on SQLite. Always, `.env` or not.**
  PostgreSQL is opt-in on the command line only: `make test-pg`, i.e. `MERIDIAN_PG_TESTS=1`
  (exactly "1") in pytest's environment. It drops and recreates this project's tables on
  `TEST_DATABASE_URL`, wiping the hosted copy of the pinned dataset; reseed afterwards.
  `.env` supplies the URL, never the decision. Why: until phase 4 the URL in `.env` alone
  switched the suite to PostgreSQL, and on 2026-10-20 a bare pytest emptied Supabase.
  Without the opt-in, `tests/conftest.py` also refuses any non-SQLite connection
  (SQLAlchemy `do_connect`) and any lookup of or connection to another machine (an audit
  hook; psycopg resolves host names in Python, so the hook sees them), and
  `tests/test_test_database_guard.py` proves both. Proof run (2026-10-20): the full suite
  with `.env` present and no flag made 0 lookups of or connections to the hosted host.
- `make seed` always regenerates the **pinned dataset**: seed 42, history
  2023-10-09..2026-10-08 (`SEED` / `END_DATE` in the Makefile, `DEFAULT_SEED` /
  `DEFAULT_END_DATE` in `backend/app/seed/ground_truth.py`; a test keeps them in sync).
  Same bytes every run, every day. `make seed END_DATE=...` exists only for deliberate
  regeneration, after which the new `ground_truth.json` must be committed. It also creates
  the four demo users (one per role, public password; see the auth rules below).

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
  repo-root `.env`, gitignored) names the PostgreSQL database `make test-pg` runs the
  whole suite on, plus the cross-dialect tests; without the opt-in those tests are skipped
  (never delete them). The PG fixture drops only this project's tables, never the schema. The file must be named exactly
  `.env`: Notepad's `.env.txt` is neither read by the app nor covered by `.gitignore`.
- The hosted test database is Supabase, reached through the **session pooler** in
  ap-south-1 (port 5432). Do not switch to the direct endpoint: it is IPv6-only on the
  free tier and does not resolve from the dev network. `SELECT version()` (2026-10-11):
  `PostgreSQL 17.11 on x86_64-pc-linux-gnu, compiled by gcc (GCC) 15.2.0, 64-bit`.
  That is the target version (it replaced the original PostgreSQL 16 target, which was
  never verified). Collation is `en_US.UTF-8` while SQLite compares
  bytes, so `ORDER BY` on strings can differ between the two once codes put punctuation
  in different positions; today's SKUs and region codes sort identically.
- **Free-tier Supabase pauses a project after about a week without activity.** The
  session pooler then refuses every connection with "FATAL: (ENOTFOUND) tenant/user ...
  not found" (seen 2026-11-08, after the last activity on 2026-10-20). **That message means
  paused: do not debug the URL, the pooler or `.env`.** Ask the user to restore the project
  from the Supabase dashboard; there is no way to do it from here. Nothing is lost:
  restored 2026-11-09 with the same pooler string (`.env` unchanged since 2026-10-11) and
  every row intact (207,981 `daily_sales` rows, both rollups equal to their GROUP BY, RLS on
  all 17 tables, read-only check). Migration 0005 was then applied there (20 tables).
- That database is also the PG fixture's scratch space: `make test-pg` drops and
  recreates the tables, wiping anything `make seed` put there. The full suite takes
  ~7-9 min there. `make seed` against it (`DATABASE_URL` set to it) is network-bound:
  58-301 s measured over Wi-Fi (vs ~10-13 s on SQLite), and one run lost its connection
  mid-insert (the seed is one transaction, so it rolled back cleanly; rerun it). The
  pinned dataset takes ~106 MB of the free tier's 500 MB. Last reseeded 2026-10-20 after
  the wipe: 207,981 `daily_sales` rows, `weekly_sales` / `monthly_sales` equal to their
  GROUP BY, `ground_truth.json` byte-identical.

## Deployment

- **In production the API must run in ap-south-1, next to the database.** The hosted
  PostgreSQL (Supabase, ap-south-1) spends 0.2-46 ms per dashboard call (EXPLAIN ANALYZE,
  2026-10-20), yet the p95 measured from the dev laptop was 297-1,702 ms: every round
  trip there costs 35-55 ms, and a request makes 5-9 of them (pool pre-ping, BEGIN, 1-5
  statements, ROLLBACK). In the same region a round trip is about 1 ms, so a call costs
  roughly its database time plus a few milliseconds. An API in any other region pays the
  full round trip on every one of those, and laptop-to-Supabase timings say nothing about
  production speed.

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
- **Autogenerated migrations render CHECK constraints as raw text, compiled for SQLite**, so
  a column named after a PostgreSQL reserved word comes out bare. Migration 0005 had
  `CHECK (window IN (...))` for `backtest_metrics.window`: fine on SQLite, a syntax error on
  PostgreSQL (first seen on Supabase 2026-11-09; the failed migration rolled back whole).
  Quote such identifiers (`'"window" IN (...)'`); `tests/test_migration_identifiers.py`
  fails on any bare reserved-word column in a migration's CHECK or `op.execute` SQL. The
  models are fine: SQLAlchemy builds Enum CHECKs as expressions and quotes per dialect.
- **Once a migration has been applied to any shared database (Supabase, or anything
  deployed), it is frozen: a fix goes in a new migration.** Editing an applied migration
  leaves that database with a schema no file describes. 0005 was fixed in place only
  because no shared or deployed database had ever reached it: Supabase's one attempt
  rolled back, and the only copies at 0005 were local SQLite dev databases (whose CHECK
  differs only in quoting).
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
- **`cn()` merges, it does not just join** (`lib/cn.ts`, tailwind-merge): when two classes
  set the same property the later one wins, which is how a caller overrides a component's
  default (LineIcon's `size-6` with `size-4`). Its theme is read from tokens.css at build
  time (colours, `text-step-*`, fonts and weights, radii, shadows, tracking, and the
  `h-chart-*` / `max-h-scroll-*` sizes), so a new token in those namespaces needs nothing.
  A new namespace, or an `@utility` that should merge with a built-in, must be added
  there. The overrides matter: tailwind-merge's defaults read any word after `text-` as a
  colour, so `text-step-1 text-fg` would have lost its size. Until 2026-11-04 `cn()` only
  joined strings and the CSS order decided, so `size-6` beat `size-4` and `size-5`: every
  icon asking for 16 or 20px drew at 24px, and the products sparklines got `h-10 w-full`
  instead of their `h-8 w-24`. Audit of the switch: all 217 class-list literals in `src/`
  merge to themselves (no false conflicts), and over 34 page states the 17 calls whose
  result changed were all a caller's class overriding a component default.
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
- Phase-2 tokens: `text-step-6` (hero headline, 36 to 61px), `tracking-wordmark` (the
  letterspaced MERIDIAN), and the motion tokens behind the `reveal` (fade and rise on scroll,
  via `<Reveal>`) and `hover-lift` utilities: 300ms, 12px rise, 2px lift. All motion is
  off under prefers-reduced-motion.
- On dark (maroon-900) surfaces the default maroon focus ring is invisible (1.87:1). Add
  `focus-visible:outline-cream-50` to every focusable element there.
- Phase-3 tokens: `--color-series-1..3` and `--color-band` (see Chart rules), and
  `--color-scrim` (ink-900 at 40%, behind the drawer). `--size-chart-sm/md/lg` (192, 288,
  384px) and `--size-scroll-list/table` (240, 480px) are **not spacing**: they generate
  only `h-chart-*` and `max-h-scroll-*`, custom `@utility` rules in `index.css`, because
  the spacing scale stops at 96px and Tailwind has no height scale. Do not add large
  steps to `--spacing-*` instead. Motion utilities `slide-over` (the drawer) and `fade-in`
  (toasts) use the motion tokens and are off under prefers-reduced-motion.
- Words where figures default to tabular (tables, chart category axes) take
  `normal-nums`: tabular figures widen the hyphen in "FX-015" or "Non-stick".
- `/styleguide` composites translucent tokens (band, scrim) over cream-50 before
  measuring contrast; it used to measure the opaque colour.

## Chart rules (phase 3)

- **Maroon is the primary series.** Further series use the measured slots below and ink,
  never new hues.
- **A confidence band is maroon at low opacity** (`--color-band`, maroon-500 at 14%),
  never a second colour.
- **Never colour a data series sage, amber or clay**: those mean good, warning and bad,
  not identity.
- **Every axis is labelled with its unit, and every chart has an accessible
  description.** In the components both are required props, and every chart also
  renders its plotted values as a visually hidden table, so a screen reader can read
  the numbers, not just the summary.

**The series palette is measured, not chosen, and it has exactly three slots.** In order:
series-1 maroon-500, series-2 ink-400, series-3 maroon-900. Measured 2026-10-13 with the
dataviz skill's `validate_palette.js`: ΔE is Euclidean distance in OKLab x100, colour
blindness is simulated with Machado-Oliveira-Fernandes 2009 at severity 1.0, against
cream-50. Target ΔE >= 8 under simulation (6 is a floor that needs secondary encoding)
and >= 15 with normal vision (a hard floor). Lines and grouped bars can put any two
series side by side, so every pair counts:

| Pair | Worst simulated ΔE | Normal vision ΔE | Verdict |
|---|---|---|---|
| maroon-500 / ink-400 | 18.1 (deuteranopia) | 22.0 | pass |
| ink-400 / maroon-900 | 34.9 (deuteranopia) | 36.1 | pass |
| maroon-500 / maroon-900 | 14.7 (protanopia) | 17.1 | pass (the worst pair of the three) |
| maroon-300 / ink-400 | **2.1** (deuteranopia) | **9.2** | fail: indistinguishable |
| maroon-500 / ink-600 | **1.9** (deuteranopia) | **11.2** | fail: indistinguishable |

Contrast against cream-50, for marks (3:1 needed): maroon-500 7.78, ink-400 3.33,
maroon-900 14.53. (maroon-300 is 3.85 and ink-600 7.28; contrast was never their problem.)

What this rules out, so no later session "helpfully" adds it:
- **No lighter maroon tint as a series.** It was the original instruction ("derived
  maroon tints and ink") and it is wrong: maroon-300 cannot be told apart from ink-400
  under deuteranopia (ΔE 2.1) and barely with normal vision (9.2). Any tint light enough
  to differ from maroon-500 lands on ink-400's lightness. It fails whatever its slot,
  because every pair counts.
- **No ink-600 as a series**: it collapses into maroon-500 under deuteranopia (ΔE 1.9).
- **No fourth series.** There is no fourth colour that separates from all three.
  `TimeSeriesChart` and `BarChart` render an error state ("Too many series: 4") instead
  of drawing; `/styleguide/components` shows it. Fold small series into "Other", or use
  separate charts.
- The validator also flags its lightness-band and chroma checks for this palette: ink is
  grey and maroon-900 is dark by design. That is the cost of maroon-and-ink only, and the
  reason identity never rests on colour alone: a legend whenever there are two or more
  series, the tooltip, and the hidden data table.
- Re-run the validator for any palette change, with all pairs (`--pairs all`), and
  update this table.

Mark specs (`components/charts/`): 2px lines, the forecast dashed (6 4) after a solid
ink-400 divider at the last actual period (the dashed line and the band start from that
point so they join up); bars at most 24px thick with 4px rounded ends, 2px apart in a
group; hairline cream-200 grid; ticks `text-step-n2` with `figure` for numbers and dates,
`normal-nums` for category words; axis titles as HTML above (vertical axis) and below
(horizontal axis) the plot. Compact ticks use three significant digits (2,250 is
"2.25K", not a rounded "2.3K"). Recharts animations are off under prefers-reduced-motion
(`usePrefersReducedMotion`). Value axes are `width="auto"` (sized to the widest tick): a
fixed 48px cut the rupee sign off "₹2.25Cr". The time series keeps 32px on the right for
its last date tick ("Oct 2026" is 50px wide, centred on the plot's edge).

### Up and down (after phase 4)

- **"Up" and "down" always mean against the comparison period** (the same period last
  year by default), never a line's own week-on-week slope. The data is seasonal: a line
  coloured by its slope would turn clay after every Diwali, which is the season, not a
  decline.
- **Series lines are never recoloured**: series colour is identity. Sage and clay encode
  only the sign of a difference, and colour is never the only signal: every coloured
  value also carries a sign (a true minus, U+2212, from `formatSignedPercent`) and an
  arrow (`SignedChange`, `KpiCard`), and the hidden tables give the signed difference
  with "(up)" / "(down)".
- **Sage and clay never sit on or directly beside a maroon series.** Measured
  2026-10-20 (validator method above; simulated = the worse of protanopia and
  deuteranopia, tritanopia noted where it is lower):

| Pair | Normal vision ΔE | Worst simulated ΔE | Verdict |
|---|---|---|---|
| sage-600 / clay-600 | 15.2 | 6.5 (deutan) | floor: legal only with position + sign + arrow |
| sage-600 / maroon-500 | 18.2 | **5.6** (deutan) | fail |
| clay-600 / maroon-500 | **9.0** | 8.6 (deutan; tritan 6.9) | fail: barely distinct even with full colour vision |
| sage-600 / ink-400 | **13.7** | 10.6 (protan) | fail (normal vision) |
| clay-600 / ink-400 | 15.8 | 12.8 (deutan) | pass |
| sage / clay washes over cream-50 at 14%, 18%, 24% | **1.8, 2.4, 3.1** | **0.8, 0.9, 1.3** (deutan) | fail: indistinguishable at any opacity under 100% |

  Contrast on cream-50: sage-600 5.41, clay-600 5.74. The ink-400 comparison line drops
  below 3:1 on those washes (2.77, 2.63, 2.40).
- **So there is no shaded gap between a current and a comparison line, and there must
  not be one.** It was specified, measured (the last row) and dropped: low-opacity sage
  and clay next to a maroon line cannot work on this palette. Do not try it again with
  other opacities; the washes are under ΔE 3.1 at every opacity tried.
- **Clay was not darkened.** Separating clay from sage (normal >= 15, simulated >= 8)
  needs clay-600 mixed into ink-900 at 60% clay or less (60%: ΔE 15.4 / 10.3 vs sage).
  At 60%, 55% and 50% the destructive button against the maroon primary falls to
  simulated ΔE 4.8, 5.1, 5.6 (from 8.6); at 60% negative text comes within ΔE 7.7 of
  muted ink-600 text (from 12.4) and the destructive hover within ΔE 2.6 of its rest
  state (from 4.3). Only 45% and 40% clear maroon again (6.3, 7.3), and at 45% negative
  text is ΔE 14.0 from body text and the hover 2.0. Every WCAG ratio would have improved
  (error text 5.74 to 8.94, badge text 4.97 to 7.75), so contrast was never the problem:
  the up/down charts rely on position and sign with clay-600 as it is.
- **Where the sign is shown:** `DivergingBarChart` (bars about a zero line, sage up,
  clay down, rounded far ends): the change strip under the dashboard's and a product's
  time series, its own panel (`ChangeStrip`); and "Growth by product" beside Top
  products, sorted, `centreZero`, no maroon in it. Position carries the meaning; colour
  only reinforces it. Plus `SignedChange` on KPI deltas and the products table.
- **The strip lines up with the chart above it**: both fix their value axis to
  `ALIGNED_AXIS_WIDTH` (64px), the time series takes `alignToBars` (half a band of
  padding each side, so its points sit where bars centre) and both share a `syncId`, so
  hovering one shows the same period in the other. Measured: every bar within 0.23px of
  its point at 1440, 768 and 360.
- **A bucket with a missing or partial comparison gets no colour**: a neutral ink ring on
  the zero line (a change that rounds to 0.0% gets a neutral 2px mark), and the reason
  in the tooltip and the hidden table. The API gives `baseline_days_covered` per point
  and `baseline_history` (the data's first day, or the filtered products' launch, so a
  week before the Air Fryer launched is "no comparison", not "nothing sold"). A product
  with no comparison is left out of Growth by product, named with its reason under it.

## App shell and component library (phase 3)

- **Shell** (`components/shell/`): below 768px a top bar whose hamburger opens a
  slide-over drawer (a modal `<dialog>`: focus trap, Escape and focus return come from
  the browser); 768-1023px an icons-only rail with labels as tooltips on hover and
  keyboard focus; from 1024px the full sidebar, collapsible. The collapse choice is
  stored per browser in localStorage `meridian.sidebar.collapsed`, every access in
  try/catch, expanded when storage is unavailable; it applies only from 1024px.
- **Focus after mouse use.** `:focus-visible` alone is not enough: browsers turn it on
  for whatever is focused as soon as any key is pressed (a screenshot shortcut will do),
  so a nav link clicked with the mouse later showed a full maroon box. So: AppLayout
  moves focus to `<main>` after every navigation (named by the page's h1,
  `#page-title`; the first load never moves focus); controls that stay on the page
  release focus after a pointer click (`isPointerClick`, `lib/pointer.ts`; a
  keyboard-fired click has `detail` 0); the drawer opens with focus on its panel and,
  closed with the mouse, does not hand focus back to the hamburger. Keyboard use keeps
  every ring. Every focus style in the shell is `focus-visible:`, the skip link's too;
  do not add `focus:` ones.
- Who sees Planning comes from one constant, `PLANNING_ROLES` (`auth/roles.ts`), read by
  both the route guard and the nav (`shell/nav.ts`). Add new role-gated sections the
  same way.
- Breadcrumbs come from route `handle: { crumb }` (`useMatches`); give every new route
  one. Every `/app` page renders inside `<PageScaffold title subtitle actions>`, which
  also sets the tab title.
- **Data components take `isLoading`, `error` and `onRetry`** (TanStack Query's
  `isPending`, `error`, `refetch`) and detect empty data themselves. Charts go through
  `ChartFrame`, which never draws axes without data and keeps the plot's height (and the
  axis titles' lines) in every state, so nothing jumps when data arrives.
- **`sr-only` goes on a wrapper, never on a `<table>`**: a table ignores the 1px width
  and grows to its content. The hidden chart tables did this and made the page 1157px
  wide at 360px.
- **Popover blur**: closing on blur must ignore a null `relatedTarget` **and an
  ancestor of the popover**. Pressing on a label or padding inside the panel moves focus to
  the nearest focusable ancestor: `<body>`, or `<main>`, which is focusable (tabIndex -1)
  since the phase-3 focus fix. Treating that as "left" closed the panel before the click
  landed: in phase 3 "Custom range" never opened, in phase 4 no date preset or multi-select
  choice applied in the app (the styleguide has no focusable `<main>`, so it passed
  there). Clicks outside are the pointerdown listener's job.
- **Absolutely positioned content inside a scroll container needs a positioned ancestor
  inside it**: `sr-only` text in a table cell escaped the table's `overflow-auto` (its
  containing block was the page) and widened the products page to 873px at 360px.
  DataTable's scroll container is `relative` for this reason.
- `KpiCard`: the arrow shows direction, the colour whether it is good; `upIsGood={false}`
  for stockouts, returns, forecast error. Anything that rounds to 0.0% is flat (ink).
- `DataTable` is controlled (sort, page); `useClientTable` does both in the browser for
  rows already loaded. Server paging for `/sales/daily` passes its own state in.
- `FilterBar` owns no data: options in, a complete `Filters` object out. An empty list
  means all. Date presets count back from `asOf`, the last day with data, not today.
- Formatting lives in `lib/format.ts` (en-IN grouping, paise to rupees) and
  `lib/dates.ts` (ISO dates, UTC arithmetic and display).
- `/styleguide/components` shows every component in every state on
  `pages/styleguide/fixtures.ts`: invented data, products with "FX-" SKUs, marked as
  fixtures on the page. Only the styleguide may import it.

## Sales analytics (phase 4)

- **Endpoints** (`/api/v1/analytics/coverage|summary|timeseries|products|regions|channels`,
  `GET /api/v1/products/{sku}`): signed-in users only, any role. `/sales/daily` now
  requires sign-in too (sales data is not public); the product list and regions stay
  public master data. All take `date_from`, `date_to`, `skus`, `regions` (any level; a
  state includes its cities), `channels`, `granularity`, `comparison`. Defaults: `date_to`
  = the last day with data, `date_from` = 13 weeks before it; a range past the history is
  clipped to it, so a comparison never sets a partial period against a full one.
- **Every sum is in the database**, one statement per question. Python only divides
  (shares, growth), ranks, classifies and zero-fills buckets.
- **Reads go through `app/services/sales_source.py`**: whole weeks / months from
  `weekly_sales` / `monthly_sales`, edge days from `daily_sales`. The rollups are pure
  GROUP BYs of `daily_sales`, rebuilt for the touched periods by the rollup job and by CSV
  imports in the same transaction (`rebuild_period_rollups`); `tests/test_period_rollups.py`
  asserts they always match. Anything new that writes `daily_sales` must call it.
- **Comparison**: `same_period_last_year` (default) is the same days **364 days (52 weeks)
  earlier**, so weekdays line up (the data has a day-of-week profile); `previous_period`
  is the window of equal length just before. Each chart bucket is compared with exactly
  its own days shifted back (bucket of `d + shift`). When the comparison window reaches
  before the history, every change is null and the UI says why (`comparison.complete`).
- **Moving festivals**: the 364-day shift aligns weekdays, not festivals (Diwali: 12 Nov
  2023, 31 Oct 2024, 20 Oct 2025). For `same_period_last_year` the time series returns
  `moving_events`: holidays and festivals whose two dates differ by more than 3 days once
  shifted (fixed-date holidays move 1-2 days and are left out), or that fall in only one
  period. The dashboard names them under the year-over-year chart.
- **Orders = `COUNT` of `sales_orders`**, never `SUM(daily_sales.order_count)`, which
  counts an order once per product line: 350,104 lines vs 223,271 orders (+57%). A SKU
  filter is an EXISTS on the order's lines. CSV-imported sales carry no orders.
- **Gross margin = revenue - units x the product's unit cost** = (price actually paid -
  unit cost) x units, so discounts count. Average selling price = revenue / units.
- **ABC-XYZ** (`app/services/analytics/classify.py`, thresholds as named constants):
  - ABC by revenue share over the requested period: walking down the revenue ranking, a
    product is A while the share of the products above it is under 80%, B under 95%, C
    after. The product that crosses 80% (or 95%) is in the higher class; the top product
    is always A.
  - XYZ by the coefficient of variation (sample std / mean) of weekly units: X < 0.5,
    Y 0.5-1.0, Z > 1.0, over a **fixed** trailing 52 full weeks ending on or before
    `date_to`, counting only weeks starting on or after launch and inside the history,
    missing weeks as zero; under 13 such weeks: not yet classifiable (null).
  - Why fixed: over the default 13-week window every one of the 12 SKUs was X (3 months
    cannot show a seasonal cycle); over 52 weeks: X 7, Y 4, Z 1, stable at other end dates.
    Why "since launch": the Air Fryer (launched 2026-02-08) read CV 0.95 over 52 weeks and
    2.20 over 3 years from pre-launch zeros; since launch it is 0.53.
  - **XYZ here measures volume variability, not predictability.** A seasonal SKU with a
    regular, forecastable festival peak lands in Z (the Gift Box, CV ~1.6). **Phase 5
    should reclassify on the CV of forecast errors** once forecasts exist.
- **Pagination**: `/sales/daily` is keyset-paged (`cursor` / `next_cursor`, no `offset`
  or `total`); see Known issues for the measurements.
- **SQLite performance notes** (the local p95 target is 300 ms per call):
  - `MIN(x), MAX(x)` in one SELECT scans the table; two ordered `LIMIT 1` subqueries use
    the index (`data_bounds`: 21-100 ms down to 0.1 ms, paid by every call).
  - Date arithmetic is string functions on SQLite: sum per (window, date) first, then
    shift and bucket the few hundred grouped rows.
  - The comparison series reads whole weeks from `weekly_sales` wherever a shifted week
    stays in one bucket (`shifted_row_selects`); only weeks straddling a month boundary
    are read day by day.
  - Measured locally over HTTP (2026-10-20, 30 requests each): every dashboard call
    p95 <= 136 ms for 13- and 52-week views, weekly and monthly (34 ms on a run without
    throttling). This laptop drops its clock after a few seconds of load, so timings vary
    up to 4x between runs.
- **On the hosted PostgreSQL** (2026-10-20, every transaction READ ONLY, in-process
  client on this laptop, 30 requests per call): p50 197-486 ms, p95 297-1,702 ms. That
  is the network: 35-55 ms per round trip and 5-9 round trips per request (pool pre-ping,
  BEGIN, 1-5 statements, ROLLBACK, plus the harness's two read-only checks), with Wi-Fi
  spikes in the p95. The database itself spends 0.2-46 ms per call (EXPLAIN ANALYZE,
  planning + execution; the slowest is a 52-week summary). Its answers equal SQLite's for
  all 24 calls (3,089 values). Hence the rule under Deployment: the API runs in ap-south-1
  next to the database.
- **Verification**: `make verify-analytics` compares 1,816 figures over 5 filter
  combinations (incl. a state that must include its cities, a channel, two SKUs against
  the previous period, a city by month) plus the seasonal peaks: each seasonal SKU's peak
  month in every season wholly inside the history matches the peak of
  `expected_cell_demand` (a month within 3% of the expected peak counts as a tie).
- **Frontend**: filter state lives in the URL (`pages/app/useAnalyticsView.ts`): `range`
  (a preset, re-resolved against the latest data) or `range=custom&from&to`, repeated
  `sku` / `region` / `channel`, `g`, `compare=previous`; page keys `metric`, `sort` /
  `order`, `drill`. Rupees use Indian grouping (`formatRupees`) in tables and tooltips,
  compact lakh / crore on KPI cards. No map: ranked bars and tables answer "where".
- Chart annotation tokens: `--color-annotation` (ink-400) and `--color-annotation-band`
  (ink-400 at 18%) mark holidays (rules) and promotions (washes). Only on charts whose
  series do not use ink-400, i.e. single-series charts such as a product's history.

## Forecasting (phase 5a)

- **Modelled level: units per SKU per Monday week**, from `weekly_sales`, complete weeks
  only (the last is w/c 2026-09-28; the data ends Thursday 2026-10-08, so h1 is w/c
  2026-10-05 and that week's four recorded days are not used, as at every backtest origin).
  **Region and channel figures are allocated, not modelled**: the SKU's p50 split by its
  trailing 13-week shares of units (by state, a city counting toward its state, or by
  channel) as of the run's cutoff, largest-remainder rounded so the parts add up. Medians
  only: a share of an interval is not an interval. The API labels them `allocated: true`.
- **Four models behind one interface** (`app/forecasting/models/`: given a `SalesHistory`
  and its calendar, return each SKU's p50 for h 1-26): seasonal naive (the baseline, the
  same week last year); ETS on log(1 + units), damped trend, period 52; Prophet on
  log(1 + units) with festival windows and promotion days as regressors (MAP fit, no
  sampling); LightGBM, one global direct multi-horizon model whose sales features are
  anchored at the origin and read through `_before`, which returns NaN for any later week.
  The log-space models return medians: their bias is reported, never silently corrected.
  `all_models()` returns the v2 configuration (`PROPHET_V2`, `LIGHTGBM_V2` in
  `models/__init__.py`); the constructors' defaults are v1's, so v1 stays reproducible.
- **Champion since v2: the mean of Prophet and LightGBM for every SKU** (`ENSEMBLE`,
  stored as model `prophet_lightgbm`; LightGBM alone for the Air Fryer, which Prophet cannot
  fit). Chosen over v1's per-SKU pick and over a 10%-margin pick on the internal split; the
  backtest re-checks that comparison every run (`notes.champion_check`). Being calendar-aware
  by construction, it also covers "festive SKUs get calendar-aware champions only". Without
  both parts (the fast test fixtures) the per-SKU pick is the fallback.
- **v2 settings**, each decided on the selection window only:
  - Prophet merges festivals that fall within 7 days of each other in **every** year of
    the calendar into one regressor (`merged_festivals`): on the pinned data Dhanteras +
    Diwali and Durga Puja + Dussehra. Separately they got large opposite effects that
    cancelled in the past but not in 2026. Default prior kept; nothing tuned on festive
    origins.
  - Prophet leaves out of its fit a week below half its trailing 13-week median **and**
    below half the same weeks last year (t-53..t-51), trailing alone where there is no last
    year (`collapsed_weeks`, rule `trailing_and_year_ago_if_known`). The trailing rule alone
    scored lower WAPE but deleted real seasonal falls (the Air Cooler after summer, the Gift
    Box after Diwali): audited against ground-truth shock days, 50% precision against 71%.
    The audit is re-run every backtest (`notes.dip_audit`, scoring only).
  - LightGBM measures its sales features and target against the 13-week **median** (one
    shock week cannot drag it down). The parameter is `level_stat`: when it was called
    `level`, the loop's own `level` (the anchor's log level) shadowed it, and "mean" silently
    became the median for every SKU after the first. `test_forecast_v2.py` checks every SKU.
  - LightGBM festival offsets (days from each festival that moves more than a week between
    years, and the change against the year-ago week): tried for all ten moving festivals,
    not adopted (pooled selection WAPE 13.1% against 12.6%; better on 2 of 11 SKUs).
- **Short history is excluded, never fitted badly.** Weeks of data a SKU needs at the
  origin: seasonal naive 53 (and the week a year earlier must exist), ETS and Prophet 104
  (two seasons), LightGBM 13 (its level; seasonality comes from the category). The Air
  Fryer (35 weeks) gets LightGBM only, is flagged `short_history`, and is outside every
  headline figure: no seasonal-naive forecast exists for it before Feb 2027.
- **Known in advance**: holidays and festivals (the calendar runs to 2027-04). **Recorded
  promotions are treated as planned**, i.e. known in advance: an assumption. None is
  recorded after the data end, so the production forecast assumes none, and says so.
  **Supply shocks are never an input**, and past shock weeks are not cleaned out of the
  training data (that would mean reading the ground truth).
- Festival features (`calendar.py`): per festival, the days of the week in four generic
  windows (14-8 days before, 7-1 before, the day, 1-7 after), not the generator's windows
  or multipliers. Prophet gets 25 of them (about 150 points cannot carry 68 regressors);
  LightGBM gets all 68, and the same for the week a year earlier.
- **Leakage**: a model only ever receives `history.until(origin - 1)`.
  `tests/test_forecast_leakage.py` scrambles every week after an origin and requires
  bit-identical forecasts from all four models (a planted leak, `until` returning the
  whole history, fails it), checks LightGBM's anchor features, and checks the imports:
  **only `oracle.py` reads the ground truth, and only the scoring modules (`backtest.py`,
  `scoring.py`, `report.py`) read `oracle.py`**.
- **Backtest windows**: 13 origins, every 4 weeks across the last 52 weeks. The selection
  window (targets before 2026-07-06) is where every choice is made (v2: on a split inside
  it, chosen before 2026-04-06 and judged from then); the held-out
  window (the last 13 complete weeks) gives the headline and is never used to pick a model
  or an interval. Every score is computed with and without shock weeks (from the ground
  truth), against the oracle's floor, and for a festive subset (Sep-Nov 2025 targets,
  labelled as selection-window). Headline = 1 - WAPE(champions) / WAPE(seasonal naive),
  pooled over the SKUs with a seasonal-naive forecast, h 1-26; the report adds per-SKU and
  median skill because pooled WAPE is volume-weighted.
- **Intervals** (`intervals.py`): quantiles of each model's backtest log errors per horizon
  group (1-4, 5-13, 14-26), **pooled across SKUs**. Per-SKU quantiles were tried first and
  under-covered: a champion's own selection errors are small because that is why it was
  picked (on a split inside the selection window: 63% at 80% per SKU, 82% pooled). The
  switch was triggered by the first held-out result (67.5%), so the held-out coverage since
  is not a fully clean held-out number. Held-out intervals come from selection errors only;
  production from all. The p50 is never moved
  into its interval (so the DB check orders the bounds but does not require it).
  **Since v2, a SKU with under 52 weeks of data uses the `young` table** (`table_key`):
  LightGBM's errors on long-history SKUs cut to their last 30 weeks at each origin (half
  of them at a time, the other half intact), about 2-4x as wide. On the internal split it
  covered simulated young SKUs at ~79% where the long-history table covered ~55%.
- **The forward oracle test** (`scoring.py`): the production forecast against expected
  demand with no promotions and no shocks (the generator's own function, its window
  extended into the 182 days its holiday list covers; it refuses beyond). Not comparable
  with backtest WAPE, and reported separately. It also checks the Diwali 2026 peak: festive
  champions (Packaged Foods, Kitchen Appliances) must peak in the weeks holding the 10 days
  before Diwali (w/c 2026-10-26 and 11-02).
- **Deterministic**: fixed seeds, LightGBM `deterministic` on one thread, Prophet's MAP
  fit, integer units; the `ml` extra is pinned exactly and each run stores its library
  versions. `make forecast` records a SHA-256 digest of its rows: three runs from two
  separate backtests gave the same `b983b87d...`. `tests/test_forecast_determinism.py`.
- **Results** (details: `docs/backtest-report.md`, generated, never edited by hand; it
  keeps v1 beside v2). **The held-out window and the forward oracle test have each been
  looked at twice** (v1, then v2, once each); v2's changes were prompted by v1's held-out
  results and v1's Diwali check, so neither v2 figure is a clean out-of-sample result.
  Never re-score them again to choose anything. v1 = backtest run 4 / forecast run 6
  (runs store no `version`; v2 runs store `"version": "v2"`); v2 = backtest run 7 /
  forecast run 8.

  | | v1 | v2 |
  |---|---|---|
  | Held-out WAPE (skill vs seasonal naive) | 16.8% (+46.6%) | 13.6% (+56.9%) |
  | Median per-SKU skill | +33.6% | +50.4% |
  | Champions' 80% / 95% coverage, held-out | 76.1% / 91.9% | 79.7% / 94.7% |
  | Forward oracle skill, all headline SKUs | +55.3% | +70.1% |
  | **Forward oracle skill, festive SKUs** | **+5.5%** | **+53.6%** |
  | Diwali 2026 check (festive champions in the Diwali weeks) | 4 of 6 | 5 of 6 |
  | `make backtest` | 290 s | 413 s (the young-SKU simulation adds 26 LightGBM fits) |

  Oracle floor 1.5% held-out. Forecast-error XYZ moves the Gift Box from Z to Y (error CV
  0.61), and four Y SKUs to X. v2 digest `0f1c879b...`. See Known issues for what is
  still open.

### Plan for phase 10, not now: a sealed final test

Phase 5a's held-out window and forward oracle test have each been seen twice, so neither
can give a clean result again. The project's final, honest number comes from data no one
has seen, scored once:

- **Generate demand for the 52 weeks after 2026-10-08** (2026-10-09 to 2027-10-07) with
  the same generator and seed, **without changing any pinned history or a single byte of
  `ground_truth.json`** (it must still hash to B93DCEE4..., and
  `test_committed_ground_truth_matches_the_pinned_generator` must still pass). Keep the
  sealed weeks out of the app's database and out of anything a model trains on; like
  `oracle.py`, only the final scoring code may read them.
- **If extending the generator would change the pinned history, say so at that point and
  stop for a decision**; never regenerate the pinned dataset to make room. Things to check
  then: whether the RNG streams (`(seed, stream, product_index)`) draw day by day so that a
  longer window shifts the earlier draws, and that the ground truth's holiday list covers
  only 182 days past the data end, while 52 weeks need about a year.
- **Score the final model on it exactly once, at the end of the project**: the same
  metrics as the backtest (WAPE, skill against seasonal naive, median per-SKU skill, 80% /
  95% coverage, the festive SKUs on their own line, and the Diwali 2026 peak check, this
  time against generated sales rather than expected demand; Diwali 2027 falls after the
  sealed year), reported beside phase 5a's figures. Nothing is changed after seeing it.
- **Do not generate it or look at it before phase 10.** Until then it does not exist, so
  nothing can be tuned against it.

## Authentication rules established in phase 2

- Access token: 15 minutes, sent as `Authorization: Bearer`, held only in client memory
  (`frontend/src/auth/tokenStore.ts`), never in localStorage, sessionStorage or a readable
  cookie. Refresh token: 7 days, in the `meridian_refresh` cookie (httpOnly, Secure,
  SameSite=Lax, Path=/api/v1/auth). "Remember me" makes it a persistent cookie; otherwise
  it is a browser-session cookie.
- Refresh tokens rotate: each one works once (`refresh_tokens` table, by JWT id). A used
  or revoked token presented again revokes its whole sign-in family. Sign-out revokes the
  family; changing a password revokes every family and issues a fresh one.
- Failed sign-ins share one message ("Email or password is incorrect.") for an unknown
  email, a wrong password and an inactive account. An unknown email is still verified
  against `DUMMY_PASSWORD_HASH`, at the same argon2 cost, so timing reveals nothing either.
  A test asserts that path runs; keep it when touching `authenticate()`.
- Login rate limit: 5 failures per (client IP, email) per sliding 15 minutes, then 429
  with Retry-After. Unknown emails are limited too. A success resets the count. See
  Known issues.
- Roles: `require_role(*roles)` in `app/api/deps.py` (401 signed out, 403 wrong role).
  `POST /api/v1/imports/sales` is admin and planner only. Since phase 4 sales data
  (`/sales/daily`, `/analytics/*`, `/products/{sku}`) needs any signed-in role; the product
  list and regions stay public.
  On the frontend `<RequireAuth roles=...>` mirrors this: `/app/planning` is admin and
  planner only.
- `JWT_SECRET` signs the tokens. Unset, a dev-only key is generated once into
  `backend/.jwt-secret` (gitignored). Tests set a fixed key in `conftest.py`.
- All timestamps use `UTCDateTime` (`app/models/base.py`): aware UTC on both dialects;
  writing a naive datetime raises.
- Demo users (`app/seed/users.py`) exist only through `make seed`, with a public password.
  The login page's "Use demo account" buttons are behind `import.meta.env.DEV`; the
  production bundle was checked to contain neither the buttons nor the password.
- Frontend: `refreshSession()` is single-flight, because two parallel refreshes would
  look like a replayed token (React StrictMode runs the start-up effect twice in dev).
  `apiFetch()` retries once after a 401. `AuthProvider` stays "loading" until the start-up
  refresh answers, so a reload never flashes the login page.
- Backend tests use `https://testserver`, because httpx withholds Secure cookies over http.
- The forecast and backtest endpoints (`/api/v1/forecasts`, `/forecasts/{sku}`,
  `/backtest/metrics`, `/backtest/leaderboard`) need any signed-in role, like sales data.

## Known issues

- **Phase 5a is closed with three open items, recorded and deliberately unfixed.** Both
  evaluation windows (the held-out 13 weeks and the forward oracle test) have been seen
  twice, once per version; every further change chosen while looking at them would fit
  them. **Do not iterate on the forecasting against them again.** The only clean test left
  is phase 10's sealed one (below). Numbers from backtest run 7 / forecast run 8:
  - **Sweets (FDS-SWT-500) peaks three weeks before Diwali 2026.** The champion (the
    Prophet + LightGBM mean) peaks in w/c 2026-10-12; expected demand peaks in w/c
    2026-10-26, inside the Diwali weeks (10-26, 11-02). Its LightGBM half peaks on
    10-12, its Prophet half on 11-02. So the Diwali check is 5 of 6 festive champions, and
    that acceptance criterion is not met.
  - **LightGBM carries a supply shock forward.** WAPE at horizons 1-4 when the week before
    the origin was a shock week: 31.9%, against 14.4% at every other origin (v1: 34.4%
    against 15.4%), over 80 forecast-weeks. The 13-week median level barely helped: its
    last-weeks lag features still see the shock. The ensemble dilutes it (18.2% against
    12.7%); Prophet's dip rule fixed Prophet's (26.7% to 9.1%).
  - **The Air Fryer's (KIT-AFR-45) 80% intervals cover 62.0% of held-out weeks** (target
    75-85%; 50 forecast-weeks), with the young-SKU table. v1 covered 40.0%. The champions
    pooled are inside the band (78.7%), so the per-champion criterion is met while this
    one SKU is not.
  v1's four open items, for the record: per-SKU champion overfitting (gone with the
  ensemble), Prophet's shock carry-over (fixed), LightGBM's interval coverage as champion
  (71.5%; the champion is now the ensemble), and Diwali 4 of 6 (now 5 of 6).
- Migration 0005 is on Supabase since 2026-11-09 (Alembic 0005, 20 tables, RLS on all,
  the three forecast tables empty). No forecasts are to be written there.

- **Resolved in phase 4: `/sales/daily` deep pagination.** OFFSET paging re-ran the
  count and the whole GROUP BY for every page. Measured 2026-10-17 on the day-level sku x
  region x channel breakdown (207,981 rows, 21 pages of 10,000): 12.4 s on SQLite and
  about 42 s on the hosted PostgreSQL (3 pages timed, 2.0 s each; 255 s on 2026-10-11).
  Now keyset-paged down the unique index: 0.49 s and 3.3 s for all 21 pages. Week and
  month groupings read `weekly_sales` / `monthly_sales` (36,613 / 9,016 rows): the 4 weekly
  pages take 73 ms on SQLite instead of about 0.78 s each.
- **Gross margin uses today's unit cost for every period.** `products.unit_cost_minor` is
  the only cost the schema keeps, so past margins are costed at today's cost; a cost change
  silently restates history. The margin KPIs say so in their caption. Fix: a dated cost
  history (product, valid_from, unit_cost_minor) and a per-day cost join.
- **The login rate limiter is in-memory, per process** (`app/services/rate_limit.py`). It
  is correct for one uvicorn process. A restart clears every count, and several workers
  would each keep their own, multiplying the effective limit by the worker count. Running
  more than one process needs a shared store keyed by (client IP, email) with atomic
  increments and expiry: Redis, or a database table. Related: the "client IP" is the
  direct peer, so behind a reverse proxy every visitor shares the proxy's IP unless
  uvicorn trusts the forwarded headers (`--proxy-headers --forwarded-allow-ips`).
- Two browser tabs that refresh the same session at the same moment present the same
  refresh token twice, which looks like a replay and signs the user out. The single-flight
  guard only covers one tab. Fix if it bites: a short grace window for a just-used token,
  or cross-tab coordination (BroadcastChannel).
- An anonymous page load shows one 401 in the browser console: the start-up
  `/auth/refresh` call with no cookie. It is expected, not an error.
