import enum

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def enum_type(enum_cls: type[enum.Enum], name: str) -> sa.Enum:
    """Enum stored as VARCHAR + CHECK constraint (not a native PG enum).

    Same DDL on PostgreSQL and SQLite, and adding a value later is a constraint
    change rather than an ALTER TYPE. Values (lower-case) are stored, not names.
    """
    return sa.Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],
    )
