# Meridian Forecast developer tasks. Run from the repository root.
#
# Windows: GNU make is not on PATH by default; MSYS2 ships one at C:\msys64\usr\bin\make.exe.
# Every target is a thin wrapper, so `cd backend && python -m app.cli seed` works without make.
#
# The virtualenv lives OUTSIDE the repo by default. This folder's path is long enough that
# Prophet (phase 5) cannot be installed into a venv inside it while Windows long paths are
# disabled (MAX_PATH = 260). Override with `make VENV=...` once long paths are enabled.

ifeq ($(OS),Windows_NT)
VENV ?= $(USERPROFILE)/.virtualenvs/meridian
PYTHON := $(VENV)/Scripts/python.exe
BOOTSTRAP_PYTHON ?= python
else
VENV ?= $(HOME)/.virtualenvs/meridian
PYTHON := $(VENV)/bin/python
BOOTSTRAP_PYTHON ?= python3
endif

# The pinned dataset: backend/app/seed/ground_truth.json in git was generated from these
# and later phases score models against it. Override only to regenerate on purpose, e.g.
# `make seed END_DATE=2026-12-31`, and then commit the new ground_truth.json.
# Must match DEFAULT_SEED / DEFAULT_END_DATE in backend/app/seed/ground_truth.py (a test checks).
SEED ?= 42
END_DATE ?= 2026-10-08
SEED_ARGS ?=
ROLLUP_ARGS ?=
PYTEST_ARGS ?=

.PHONY: venv migrate seed rollup test run dev web build lint hooks

venv:  ## create the virtualenv and install the backend with dev and ml extras
	"$(BOOTSTRAP_PYTHON)" -m venv "$(VENV)"
	"$(PYTHON)" -m pip install --upgrade pip
	cd backend && "$(PYTHON)" -m pip install -e ".[dev,ml]"

migrate:  ## apply Alembic migrations to DATABASE_URL (SQLite file by default)
	cd backend && "$(PYTHON)" -m alembic upgrade head

seed:  ## wipe and regenerate the pinned dataset (same bytes every run, every day)
	cd backend && "$(PYTHON)" -m app.cli seed --seed $(SEED) --end-date $(END_DATE) $(SEED_ARGS)

rollup:  ## rebuild daily_sales from order lines; e.g. make rollup ROLLUP_ARGS="--date-from 2026-01-01"
	cd backend && "$(PYTHON)" -m app.cli rollup $(ROLLUP_ARGS)

test:  ## run pytest; set TEST_DATABASE_URL to a disposable PostgreSQL DB to include PG tests
	cd backend && "$(PYTHON)" -m pytest $(PYTEST_ARGS)

run:  ## start the API on http://127.0.0.1:8000 (docs at /docs)
	cd backend && "$(PYTHON)" -m uvicorn app.main:app --reload

# ---- Frontend (frontend/, Node >= 22.12). `npm ci` reruns whenever the lockfile changes.

FRONTEND_DEPS := frontend/node_modules/.package-lock.json
PRE_COMMIT_VERSION ?= 4.6.2

ifeq ($(OS),Windows_NT)
# Run from PowerShell, make's shell inherits the Windows PATH, which lacks MSYS's /usr/bin.
# npm's launcher is a bash script (#!/usr/bin/env bash), so it needs bash from there.
FRONTEND_PATH := /usr/bin:$(PATH)
else
FRONTEND_PATH := $(PATH)
endif
$(FRONTEND_DEPS) dev web build lint: export PATH := $(FRONTEND_PATH)

$(FRONTEND_DEPS): frontend/package.json frontend/package-lock.json
	cd frontend && npm ci
	touch $(FRONTEND_DEPS)

dev: $(FRONTEND_DEPS)  ## the API (:8000) and Vite (http://127.0.0.1:5173) together
	$(MAKE) -j2 run web

web: $(FRONTEND_DEPS)  ## Vite dev server only; it proxies /api to the API on :8000
	cd frontend && npm run dev

build: $(FRONTEND_DEPS)  ## token checks, ESLint and type check, then the bundle in frontend/dist
	cd frontend && npm run build

lint: $(FRONTEND_DEPS)  ## frontend: token checks, ESLint (incl. Tailwind token rules), Prettier
	cd frontend && npm run lint

hooks:  ## install pre-commit into the venv and enable the git hooks (.pre-commit-config.yaml)
	"$(PYTHON)" -m pip install "pre-commit==$(PRE_COMMIT_VERSION)"
	"$(PYTHON)" -m pre_commit install
