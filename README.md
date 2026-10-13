# Meridian Forecast

Demand forecasting and production planning for manufacturers. A planner sees how each
product is selling and where, gets a demand forecast for the next 1 to 26 weeks with
confidence ranges, is warned before a peak season, and turns it into a production plan.

The project is built in phases. `CLAUDE.md` records the current state, the conventions and
the design rules.

## Quick start

You need Python 3.11+, Node 22.12+ and GNU make. On Windows, run make from PowerShell as
`C:\msys64\usr\bin\make.exe`.

```
make venv    # the virtualenv, with the backend and its dev and ml extras
make seed    # migrate a local SQLite database and load the pinned demo dataset
make dev     # the API on http://127.0.0.1:8000 and the app on http://127.0.0.1:5173
```

Then open http://127.0.0.1:5173 and sign in with one of the demo accounts below.

## Demo credentials (local development only)

> **These accounts exist only because `make seed` creates them, and their password is
> public.** Never run `make seed` against a database anyone else can reach.

| Role    | Email                 | Password             |
| ------- | --------------------- | -------------------- |
| Admin   | admin@meridian.demo   | `meridian-demo-2026` |
| Planner | planner@meridian.demo | `meridian-demo-2026` |
| Analyst | analyst@meridian.demo | `meridian-demo-2026` |
| Viewer  | viewer@meridian.demo  | `meridian-demo-2026` |

In a development build the login page also has "Use demo account" buttons that fill these
in. Production builds (`make build`) leave the buttons and the password out.

## Checks

```
make test    # pytest (with TEST_DATABASE_URL in .env it runs against that PostgreSQL)
make lint    # frontend: design-token checks, ESLint, Prettier
make build   # the frontend production bundle in frontend/dist
```
