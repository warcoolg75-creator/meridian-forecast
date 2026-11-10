from enum import StrEnum


class Channel(StrEnum):
    DISTRIBUTOR = "distributor"
    RETAIL = "retail"
    ECOMMERCE = "ecommerce"
    DIRECT = "direct"
    EXPORT = "export"


class EventType(StrEnum):
    PUBLIC_HOLIDAY = "public_holiday"
    FESTIVAL = "festival"
    PROMOTION = "promotion"
    PLANT_SHUTDOWN = "plant_shutdown"
    TRADE_SHOW = "trade_show"


class RegionLevel(StrEnum):
    COUNTRY = "country"
    STATE = "state"
    CITY = "city"


class UserRole(StrEnum):
    ADMIN = "admin"
    PLANNER = "planner"
    ANALYST = "analyst"
    VIEWER = "viewer"


class SalesSource(StrEnum):
    """Where a daily_sales row came from.

    The rollup only ever rebuilds ORDERS rows; IMPORT rows (CSV uploads) are
    authoritative and win over order-derived data for the same cell.
    """

    ORDERS = "orders"
    IMPORT = "import"


class ForecastRunKind(StrEnum):
    PRODUCTION = "production"  # champions trained on all history: what the app shows
    BACKTEST = "backtest"  # rolling-origin evaluation: metrics, champions, interval widths


class MetricWindow(StrEnum):
    SELECTION = "selection"  # target weeks before the held-out window; champions are picked here
    HELD_OUT = "held_out"  # the last 13 complete weeks; never used to pick anything
    FESTIVE_2025 = "festive_2025"  # selection-window targets in Sep-Nov 2025 (a subset, for the festive view)


class ShockScope(StrEnum):
    INCLUDED = "included"  # every target week
    EXCLUDED = "excluded"  # weeks with a supply shock (ground truth) left out


class SignalFrequency(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class SignalAggregation(StrEnum):
    """How a daily series becomes weekly or monthly: mean (temperature, prices) or sum (rain, views)."""

    MEAN = "mean"
    SUM = "sum"


class SignalRole(StrEnum):
    DEMAND_CONTEXT = "demand_context"  # shown beside sales as context; never a forecasting input
    INPUT_COST = "input_cost"  # what our materials cost: for phase 9 planning, not demand


class FetchMode(StrEnum):
    BACKFILL = "backfill"
    REFRESH = "refresh"


class FetchStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    PARTIAL = "partial"  # some series or windows failed, the rest were stored
    FAILED = "failed"
    NOT_CONFIGURED = "not_configured"  # e.g. FRED without FRED_API_KEY: skipped, not an error
