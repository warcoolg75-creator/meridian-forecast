from datetime import date

from app.schemas.common import ORMModel


class PlantRead(ORMModel):
    id: int
    code: str
    name: str
    city: str
    state: str
    country: str
    latitude: float
    longitude: float
    timezone: str


class ProductionLineRead(ORMModel):
    id: int
    code: str
    name: str
    plant_id: int
    units_per_hour: int
    changeover_minutes: int
    operating_hours_per_day: int
    is_active: bool


class LineCapabilityRead(ORMModel):
    id: int
    production_line_id: int
    product_id: int
    units_per_hour_override: int | None


class InventoryRead(ORMModel):
    id: int
    date: date
    product_id: int
    plant_id: int
    on_hand_units: int
    in_transit_units: int
    safety_stock_units: int


class ProductionRunRead(ORMModel):
    id: int
    date: date
    production_line_id: int
    product_id: int
    planned_units: int
    actual_units: int
    downtime_minutes: int
    scrap_units: int
