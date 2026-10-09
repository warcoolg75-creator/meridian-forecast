from datetime import date

from app.schemas.common import ORMModel


class ProductRead(ORMModel):
    id: int
    sku: str
    name: str
    category: str
    subcategory: str
    unit_cost_minor: int
    unit_price_minor: int
    unit_of_measure: str
    shelf_life_days: int | None
    is_active: bool
    launched_on: date
