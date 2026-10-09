import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, enum_type
from app.models.enums import RegionLevel


class Region(Base):
    """Self-referencing hierarchy: country > state > city.

    Sales are recorded against cities; state and country views roll up the tree.
    """

    __tablename__ = "regions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(16), unique=True)
    name: Mapped[str] = mapped_column(sa.String(80))
    country: Mapped[str] = mapped_column(sa.String(2))
    level: Mapped[RegionLevel] = mapped_column(enum_type(RegionLevel, "region_level"))
    parent_region_id: Mapped[int | None] = mapped_column(sa.ForeignKey("regions.id"), index=True)
