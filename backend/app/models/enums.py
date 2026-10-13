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
