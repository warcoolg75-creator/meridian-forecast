"""The signals catalog (catalog.json): sources, series, news topics and the mapping.

The catalog is data. This module validates it, expands the weather block into one series
per city and variable (plus a forecast companion each), expands mapping patterns
(`weather.tmax.*`), and syncs the result into signal_sources, signal_series and
signal_mappings idempotently: rows already equal to the catalog are left untouched.
"""

import fnmatch
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SignalMapping, SignalSeries, SignalSource
from app.models.base import utcnow

CATALOG_PATH = Path(__file__).with_name("catalog.json")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HttpPolicy(_Strict):
    min_interval_seconds: float
    max_attempts: int
    backoff_seconds: float
    cooldown_429_seconds: float
    max_wait_seconds: float
    timeout_seconds: float


class SourceDef(_Strict):
    code: str
    name: str
    homepage: str
    licence: str
    attribution: str
    terms_url: str
    requires_key: bool
    http: HttpPolicy


class WeatherVariable(_Strict):
    variable: str
    key: str
    label: str
    description: str
    unit: str
    aggregation: Literal["mean", "sum"]
    group_key: str
    stale_after_days: int


class City(_Strict):
    region: str
    name: str
    latitude: float
    longitude: float


class WeatherDef(_Strict):
    source: str
    archive_url: str
    forecast_url: str
    timezone: str
    revision_days: int
    forecast_days: int
    variables: list[WeatherVariable]
    cities: list[City]


class EndpointDef(_Strict):
    source: str
    url: str
    revision_days: int


class SeriesDef(_Strict):
    key: str
    source: str
    external_id: str
    label: str
    description: str
    unit: str
    geography: str
    geography_name: str
    frequency: Literal["daily", "weekly", "monthly"]
    aggregation: Literal["mean", "sum"]
    role: Literal["demand_context", "input_cost"]
    group_key: str
    stale_after_days: int
    citation: str | None = None
    is_forecast: bool = False
    companion_key: str | None = None
    params: dict = {}


class NewsTopic(_Strict):
    category: str
    query: str
    note: str | None = None  # why the query reads as it does


class NewsDef(_Strict):
    source: str
    url: str
    source_country: str
    max_records: int
    stale_after_days: int
    topics: list[NewsTopic]
    window_months: int = 1  # backfill window; a full one is split in half until it fits
    backfill_days: int = 90  # the default backfill reaches this far back (from the 1st of that month)


class MappingDef(_Strict):
    series: list[str]
    reason: str
    category: str | None = None
    skus: list[str] | None = None

    @model_validator(mode="after")
    def _one_scope(self) -> "MappingDef":
        if (self.category is None) == (self.skus is None):
            raise ValueError("a mapping names either a category or skus")
        return self


class CatalogFile(_Strict):
    version: int
    about: str
    sources: list[SourceDef]
    weather: WeatherDef
    fred: EndpointDef
    wikimedia: EndpointDef
    series: list[SeriesDef]
    news: NewsDef
    mappings: list[MappingDef]


@dataclass(frozen=True)
class MappingRow:
    series_key: str
    category: str | None
    sku: str | None
    role: str
    reason: str
    sort_order: int


@dataclass
class Catalog:
    file: CatalogFile
    sources: dict[str, SourceDef]
    series: dict[str, SeriesDef] = field(default_factory=dict)
    mappings: list[MappingRow] = field(default_factory=list)

    def series_of(self, source: str) -> list[SeriesDef]:
        return [s for s in self.series.values() if s.source == source]


def weather_series(weather: WeatherDef) -> list[SeriesDef]:
    """Observed and forecast series for every city and variable. The forecast companion
    holds only the latest 16-day forecast; it is never mixed into the observed series."""
    out = []
    for city in weather.cities:
        for var in weather.variables:
            common = dict(source=weather.source, unit=var.unit, geography=city.region, geography_name=city.name,
                          frequency="daily", aggregation=var.aggregation, role="demand_context",
                          group_key=var.group_key, stale_after_days=var.stale_after_days,
                          params={"latitude": city.latitude, "longitude": city.longitude, "variable": var.variable})
            observed = f"weather.{var.key}.{city.region}"
            out.append(SeriesDef(key=observed, external_id=f"{var.variable}@{city.latitude},{city.longitude}",
                                 label=f"{var.label}, {city.name}",
                                 description=f"{var.description.format(city=city.name)} (ERA5 reanalysis; the "
                                             "latest days are model analysis, revised once ERA5 arrives)",
                                 **common))
            out.append(SeriesDef(key=f"weather.{var.key}_forecast.{city.region}", is_forecast=True,
                                 companion_key=observed,
                                 external_id=f"{var.variable}@{city.latitude},{city.longitude}:forecast",
                                 label=f"{var.label} forecast, {city.name}",
                                 description=f"{var.description.format(city=city.name)}: the latest "
                                             f"{weather.forecast_days}-day forecast",
                                 **common))
    return out


def build_catalog(data: dict) -> Catalog:
    file = CatalogFile.model_validate(data)
    sources = {s.code: s for s in file.sources}
    catalog = Catalog(file=file, sources=sources)
    for s in [*weather_series(file.weather), *file.series]:
        if s.key in catalog.series:
            raise ValueError(f"duplicate series key {s.key}")
        if s.source not in sources:
            raise ValueError(f"series {s.key}: unknown source {s.source}")
        catalog.series[s.key] = s
    for block in (file.weather, file.fred, file.wikimedia, file.news):
        if block.source not in sources:
            raise ValueError(f"unknown source {block.source}")

    observed = [k for k, s in catalog.series.items() if not s.is_forecast]
    seen: set[tuple] = set()
    for order, mapping in enumerate(file.mappings):
        keys: list[str] = []
        for pattern in mapping.series:
            matched = fnmatch.filter(observed, pattern)
            if not matched:
                raise ValueError(f"mapping pattern {pattern!r} matches no series")
            keys.extend(k for k in matched if k not in keys)
        scopes = [(mapping.category, None)] if mapping.category else [(None, sku) for sku in mapping.skus or []]
        for category, sku in scopes:
            for key in keys:
                if (key, category, sku) in seen:
                    raise ValueError(f"series {key} mapped twice to {category or sku}")
                seen.add((key, category, sku))
                catalog.mappings.append(MappingRow(key, category, sku, catalog.series[key].role,
                                                   mapping.reason, order))
    return catalog


@lru_cache
def load_catalog(path: Path = CATALOG_PATH) -> Catalog:
    return build_catalog(json.loads(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- sync

_SOURCE_FIELDS = ("name", "homepage", "licence", "attribution", "terms_url", "requires_key")
_SERIES_FIELDS = ("label", "description", "unit", "geography", "geography_name", "frequency", "aggregation",
                  "role", "group_key", "is_forecast", "companion_key", "external_id", "params", "citation",
                  "stale_after_days")


@dataclass
class SyncResult:
    changed: int = 0

    def touch(self, n: int = 1) -> None:
        self.changed += n


def _assign(row, values: dict, result: SyncResult) -> None:
    dirty = False
    for name, value in values.items():
        current = getattr(row, name)
        if hasattr(current, "value"):  # a StrEnum column
            current = current.value
        if current != value:
            setattr(row, name, value)
            dirty = True
    if dirty:
        row.updated_at = utcnow()
        result.touch()


def sync_catalog(session: Session, catalog: Catalog) -> SyncResult:
    """Make the catalog tables match the catalog. Series that left the catalog keep their
    rows (and observations) but lose their mappings, so nothing fetched is ever deleted."""
    result = SyncResult()
    sources = {s.code: s for s in session.scalars(select(SignalSource))}
    for code, src in catalog.sources.items():
        values = {f: getattr(src, f) for f in _SOURCE_FIELDS}
        if code not in sources:
            sources[code] = SignalSource(code=code, **values)
            session.add(sources[code])
            result.touch()
        else:
            _assign(sources[code], values, result)
    session.flush()

    series = {s.key: s for s in session.scalars(select(SignalSeries))}
    for key, spec in catalog.series.items():
        values = {f: getattr(spec, f) for f in _SERIES_FIELDS}
        source_id = sources[spec.source].id
        if key not in series:
            series[key] = SignalSeries(key=key, source_id=source_id, **values)
            session.add(series[key])
            result.touch()
        else:
            _assign(series[key], {**values, "source_id": source_id}, result)
    session.flush()

    wanted = {(m.series_key, m.category, m.sku): m for m in catalog.mappings}
    by_id = {s.id: k for k, s in series.items()}
    for row in session.scalars(select(SignalMapping)):
        ident = (by_id.get(row.series_id), row.category, row.sku)
        spec = wanted.pop(ident, None)
        if spec is None:
            session.delete(row)
            result.touch()
            continue
        dirty = False
        for name, value in (("role", spec.role), ("reason", spec.reason), ("sort_order", spec.sort_order)):
            current = getattr(row, name)
            if (current.value if hasattr(current, "value") else current) != value:
                setattr(row, name, value)
                dirty = True
        if dirty:
            result.touch()
    for (key, category, sku), spec in wanted.items():
        session.add(SignalMapping(series_id=series[key].id, category=category, sku=sku, role=spec.role,
                                  reason=spec.reason, sort_order=spec.sort_order))
        result.touch()
    session.flush()
    return result
