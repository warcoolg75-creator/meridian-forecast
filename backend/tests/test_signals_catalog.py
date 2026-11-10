"""The signals catalog: valid, mapped to real products and categories, synced idempotently."""

import copy
import json
from datetime import date

import pytest
from sqlalchemy import func, select

from app.models import SIGNAL_TABLES, SignalMapping, SignalSeries, SignalSource
from app.seed.catalog import CATEGORIES, PRODUCTS
from app.seed.generate import wipe_all
from app.seed.ground_truth import DEFAULT_END_DATE, window_for
from app.signals.catalog import CATALOG_PATH, build_catalog, load_catalog, sync_catalog
from app.signals.pipeline import BACKFILL_START


@pytest.fixture(scope="module")
def raw() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_backfill_starts_on_the_first_day_of_the_pinned_sales_history():
    assert BACKFILL_START == window_for(DEFAULT_END_DATE, 3)[0] == date(2023, 10, 9)


def test_the_catalog_covers_every_city_category_and_sku():
    catalog = load_catalog()
    cities = {c.region for c in catalog.file.weather.cities}
    assert len(cities) == 9
    # 9 cities x 2 variables, each with a forecast companion, plus FRED and Wikipedia series.
    assert sum(1 for s in catalog.series.values() if s.source == "open_meteo") == 36
    assert {c for c in (m.category for m in catalog.mappings) if c} == set(CATEGORIES)
    assert {m.sku for m in catalog.mappings if m.sku} == {p.sku for p in PRODUCTS}
    assert {t.category for t in catalog.file.news.topics} == set(CATEGORIES)
    for category in CATEGORIES:
        roles = {m.role for m in catalog.mappings if m.category == category}
        assert "input_cost" in roles, category
    for spec in catalog.series.values():
        if spec.is_forecast:
            assert catalog.series[spec.companion_key].is_forecast is False
        assert spec.stale_after_days > 0


def test_input_costs_and_attention_proxies_say_what_they_are():
    catalog = load_catalog()
    for key, spec in catalog.series.items():
        if key.startswith("fred."):
            assert spec.role == "input_cost" and spec.citation, key
        if key.startswith("wiki."):
            assert "worldwide" in spec.description and spec.geography == "WORLD", key
    for m in catalog.mappings:
        if m.series_key.startswith("wiki.") and m.role == "demand_context" and m.category:
            assert "not Indian search" in m.reason, m


def test_signal_series_never_use_weekly_only_or_unknown_sources():
    catalog = load_catalog()
    assert {s.source for s in catalog.series.values()} == {"open_meteo", "fred", "wikimedia"}
    assert set(catalog.sources) == {"open_meteo", "fred", "wikimedia", "gdelt"}
    assert catalog.sources["fred"].requires_key and not catalog.sources["gdelt"].requires_key
    assert "not endorsed or certified by the Federal Reserve Bank of St. Louis" in catalog.sources["fred"].attribution


def test_a_pattern_that_matches_nothing_is_an_error(raw):
    data = copy.deepcopy(raw)
    data["mappings"].append({"category": "Cooling", "series": ["weather.snow.*"], "reason": "x"})
    with pytest.raises(ValueError, match="matches no series"):
        build_catalog(data)


def test_a_series_mapped_twice_to_the_same_place_is_an_error(raw):
    data = copy.deepcopy(raw)
    data["mappings"].append({"category": "Cooling", "series": ["fred.DEXINUS"], "reason": "again"})
    with pytest.raises(ValueError, match="mapped twice"):
        build_catalog(data)


def test_a_mapping_names_a_category_or_skus_not_both(raw):
    data = copy.deepcopy(raw)
    data["mappings"].append({"category": "Cooling", "skus": ["COL-ACL-70"], "series": ["fred.DEXINUS"],
                             "reason": "x"})
    with pytest.raises(ValueError, match="either a category or skus"):
        build_catalog(data)


def test_sync_is_idempotent_and_keeps_series_that_left_the_catalog(db, raw):
    catalog = load_catalog()
    first = sync_catalog(db, catalog)
    db.commit()
    assert first.changed > 0
    assert db.scalar(select(func.count()).select_from(SignalSeries)) == len(catalog.series)
    assert db.scalar(select(func.count()).select_from(SignalMapping)) == len(catalog.mappings)
    assert sync_catalog(db, catalog).changed == 0

    data = copy.deepcopy(raw)
    data["series"] = [s for s in data["series"] if s["key"] != "wiki.Namkeen"]
    data["mappings"] = [m for m in data["mappings"] if m["series"] != ["wiki.Namkeen", "wiki.Diwali"]]
    smaller = build_catalog(data)
    assert sync_catalog(db, smaller).changed > 0
    db.commit()
    namkeen = db.scalars(select(SignalSeries).where(SignalSeries.key == "wiki.Namkeen")).one()
    assert db.scalar(select(func.count()).select_from(SignalMapping)
                     .where(SignalMapping.series_id == namkeen.id)) == 0


def test_the_seed_wipe_keeps_signal_tables(db):
    sync_catalog(db, load_catalog())
    db.commit()
    wipe_all(db, keep=SIGNAL_TABLES)
    db.commit()
    assert db.scalar(select(func.count()).select_from(SignalSource)) == 4
    wipe_all(db)
    db.commit()
    assert db.scalar(select(func.count()).select_from(SignalSource)) == 0
