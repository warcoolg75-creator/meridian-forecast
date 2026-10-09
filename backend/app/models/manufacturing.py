from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(16), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    city: Mapped[str] = mapped_column(sa.String(80))
    state: Mapped[str] = mapped_column(sa.String(80))
    country: Mapped[str] = mapped_column(sa.String(2))
    latitude: Mapped[float] = mapped_column(sa.Float)
    longitude: Mapped[float] = mapped_column(sa.Float)
    timezone: Mapped[str] = mapped_column(sa.String(64))


class ProductionLine(Base):
    __tablename__ = "production_lines"
    __table_args__ = (
        sa.CheckConstraint("units_per_hour > 0", name="units_per_hour_positive"),
        sa.CheckConstraint("changeover_minutes >= 0", name="changeover_non_negative"),
        sa.CheckConstraint(
            "operating_hours_per_day > 0 AND operating_hours_per_day <= 24", name="operating_hours_range"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(16), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    plant_id: Mapped[int] = mapped_column(sa.ForeignKey("plants.id"), index=True)
    units_per_hour: Mapped[int] = mapped_column(sa.Integer)
    changeover_minutes: Mapped[int] = mapped_column(sa.Integer)
    operating_hours_per_day: Mapped[int] = mapped_column(sa.Integer)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)


class LineCapability(Base):
    """A line can make several products, each at its own rate.

    units_per_hour_override is NULL when the product runs at the line's base rate.
    """

    __tablename__ = "line_capabilities"
    __table_args__ = (
        sa.UniqueConstraint("production_line_id", "product_id"),
        sa.CheckConstraint(
            "units_per_hour_override IS NULL OR units_per_hour_override > 0", name="override_positive"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    production_line_id: Mapped[int] = mapped_column(sa.ForeignKey("production_lines.id"))
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id"), index=True)
    units_per_hour_override: Mapped[int | None] = mapped_column(sa.Integer)


class Inventory(Base):
    __tablename__ = "inventory"
    __table_args__ = (
        sa.UniqueConstraint("date", "product_id", "plant_id"),
        sa.Index("ix_inventory_product_date", "product_id", "date"),
        sa.CheckConstraint(
            "on_hand_units >= 0 AND in_transit_units >= 0 AND safety_stock_units >= 0",
            name="units_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(sa.Date)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id"))
    plant_id: Mapped[int] = mapped_column(sa.ForeignKey("plants.id"))
    on_hand_units: Mapped[int] = mapped_column(sa.Integer)
    in_transit_units: Mapped[int] = mapped_column(sa.Integer)
    safety_stock_units: Mapped[int] = mapped_column(sa.Integer)


class ProductionRun(Base):
    __tablename__ = "production_runs"
    __table_args__ = (
        sa.Index("ix_production_runs_line_date", "production_line_id", "date"),
        sa.Index("ix_production_runs_product_date", "product_id", "date"),
        sa.CheckConstraint(
            "planned_units >= 0 AND actual_units >= 0 AND scrap_units >= 0 AND downtime_minutes >= 0",
            name="values_non_negative",
        ),
        sa.CheckConstraint("scrap_units <= actual_units", name="scrap_within_actual"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(sa.Date)
    production_line_id: Mapped[int] = mapped_column(sa.ForeignKey("production_lines.id"))
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id"))
    planned_units: Mapped[int] = mapped_column(sa.Integer)
    actual_units: Mapped[int] = mapped_column(sa.Integer)
    downtime_minutes: Mapped[int] = mapped_column(sa.Integer)
    scrap_units: Mapped[int] = mapped_column(sa.Integer)
