from app.models.enums import RegionLevel
from app.schemas.common import ORMModel


class RegionRead(ORMModel):
    id: int
    code: str
    name: str
    country: str
    level: RegionLevel
    parent_region_id: int | None
    parent_code: str | None = None
