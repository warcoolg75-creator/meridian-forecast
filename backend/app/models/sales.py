from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, enum_type
from app.models.enums import Channel, SalesSource


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(16), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    channel: Mapped[Channel] = mapped_column(enum_type(Channel, "channel"))
    region_id: Mapped[int] = mapped_column(sa.ForeignKey("regions.id"), index=True)


class SalesOrder(Base):
    """region_id is the ship-to region, which can differ from the customer's own
    region (an ecommerce marketplace ships everywhere)."""

    __tablename__ = "sales_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_date: Mapped[date] = mapped_column(sa.Date, index=True)
    customer_id: Mapped[int] = mapped_column(sa.ForeignKey("customers.id"), index=True)
    region_id: Mapped[int] = mapped_column(sa.ForeignKey("regions.id"))
    channel: Mapped[Channel] = mapped_column(enum_type(Channel, "channel"))
    currency: Mapped[str] = mapped_column(sa.String(3), default="INR")


class SalesOrderLine(Base):
    __tablename__ = "sales_order_lines"
    __table_args__ = (
        sa.CheckConstraint("quantity > 0", name="quantity_positive"),
        sa.CheckConstraint("unit_price_minor >= 0", name="unit_price_non_negative"),
        sa.CheckConstraint("discount_minor >= 0", name="discount_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sales_order_id: Mapped[int] = mapped_column(sa.ForeignKey("sales_orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(sa.Integer)
    unit_price_minor: Mapped[int] = mapped_column(sa.Integer)
    discount_minor: Mapped[int] = mapped_column(sa.Integer, default=0)
    is_promotional: Mapped[bool] = mapped_column(sa.Boolean, default=False)


class DailySales(Base):
    """Materialised rollup read by the dashboard and the forecaster.

    One row per (date, product, region, channel). The unique index leads with date,
    so it also serves date-range scans across all products; the two composite
    indexes serve per-product and per-region series. Revenue is in INR paise.
    order_count is NULL for imported rows (the CSV has no order count).
    """

    __tablename__ = "daily_sales"
    __table_args__ = (
        sa.UniqueConstraint("date", "product_id", "region_id", "channel", name="uq_daily_sales_cell"),
        sa.Index("ix_daily_sales_product_date", "product_id", "date"),
        sa.Index("ix_daily_sales_region_date", "region_id", "date"),
        sa.CheckConstraint("units >= 0", name="units_non_negative"),
        sa.CheckConstraint("revenue_minor >= 0", name="revenue_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(sa.Date)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id"))
    region_id: Mapped[int] = mapped_column(sa.ForeignKey("regions.id"))
    channel: Mapped[Channel] = mapped_column(enum_type(Channel, "channel"))
    units: Mapped[int] = mapped_column(sa.Integer)
    revenue_minor: Mapped[int] = mapped_column(sa.BigInteger)
    order_count: Mapped[int | None] = mapped_column(sa.Integer)
    source: Mapped[SalesSource] = mapped_column(enum_type(SalesSource, "sales_source"))
