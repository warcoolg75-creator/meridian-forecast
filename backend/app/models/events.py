from datetime import date

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, enum_type
from app.models.enums import EventType


class CalendarEvent(Base):
    """A dated event that can move demand or capacity.

    Spans date..end_date inclusive (single-day events have end_date == date).
    region_id scopes regional festivals; product_id links a promotion to its SKU;
    plant_id links a plant_shutdown to its plant. All three are NULL when not relevant.
    """

    __tablename__ = "calendar_events"
    __table_args__ = (
        sa.Index("ix_calendar_events_date_end_date", "date", "end_date"),
        sa.CheckConstraint("end_date >= date", name="end_not_before_start"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(sa.Date)
    end_date: Mapped[date] = mapped_column(sa.Date)
    name: Mapped[str] = mapped_column(sa.String(160))
    event_type: Mapped[EventType] = mapped_column(enum_type(EventType, "event_type"))
    region_id: Mapped[int | None] = mapped_column(sa.ForeignKey("regions.id"))
    product_id: Mapped[int | None] = mapped_column(sa.ForeignKey("products.id"), index=True)
    plant_id: Mapped[int | None] = mapped_column(sa.ForeignKey("plants.id"))
    impact_note: Mapped[str | None] = mapped_column(sa.Text)
