from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        sa.CheckConstraint("unit_cost_minor >= 0", name="unit_cost_non_negative"),
        sa.CheckConstraint("unit_price_minor >= 0", name="unit_price_non_negative"),
        sa.CheckConstraint("shelf_life_days IS NULL OR shelf_life_days > 0", name="shelf_life_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(sa.String(32), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    category: Mapped[str] = mapped_column(sa.String(60), index=True)
    subcategory: Mapped[str] = mapped_column(sa.String(60))
    unit_cost_minor: Mapped[int] = mapped_column(sa.Integer)
    unit_price_minor: Mapped[int] = mapped_column(sa.Integer)
    unit_of_measure: Mapped[str] = mapped_column(sa.String(16))
    shelf_life_days: Mapped[int | None] = mapped_column(sa.Integer)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)
    launched_on: Mapped[date] = mapped_column(sa.Date)
