from datetime import date

from pydantic import BaseModel

from app.models.enums import Channel, SalesSource
from app.schemas.common import ORMModel


class CustomerRead(ORMModel):
    id: int
    code: str
    name: str
    channel: Channel
    region_id: int


class SalesOrderRead(ORMModel):
    id: int
    order_date: date
    customer_id: int
    region_id: int
    channel: Channel
    currency: str


class SalesOrderLineRead(ORMModel):
    id: int
    sales_order_id: int
    product_id: int
    quantity: int
    unit_price_minor: int
    discount_minor: int
    is_promotional: bool


class DailySalesRead(ORMModel):
    id: int
    date: date
    product_id: int
    region_id: int
    channel: Channel
    units: int
    revenue_minor: int
    order_count: int | None
    source: SalesSource


class SalesPeriod(BaseModel):
    """One bucket of /sales/daily.

    sku / region_code / channel are only set when that dimension is in group_by.
    is_partial is true when the bucket is cut short by date_from/date_to or by the
    edges of the available history (e.g. the current, unfinished week).
    order_count sums per-product order counts, so an order containing two products
    counts twice; it is null when every contributing row was CSV-imported.
    """

    period_start: date
    period_end: date
    days_covered: int
    is_partial: bool
    sku: str | None = None
    region_code: str | None = None
    channel: Channel | None = None
    units: int
    revenue_minor: int
    order_count: int | None
