from datetime import date

from app.models.enums import EventType
from app.schemas.common import ORMModel


class CalendarEventRead(ORMModel):
    id: int
    date: date
    end_date: date
    name: str
    event_type: EventType
    region_id: int | None
    product_id: int | None
    plant_id: int | None
    impact_note: str | None
