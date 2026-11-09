"""No migration may use a PostgreSQL reserved word as a bare identifier in raw SQL.

Alembic's autogenerate renders CHECK constraints as text, compiled for the dialect it ran
on (SQLite here), so a column named after a reserved word comes out bare. SQLite accepts
`window IN (...)`; PostgreSQL rejects it as a syntax error. Migration 0005 shipped that
way and first failed on Supabase (2026-11-09), because every local run is SQLite.
These checks need no database.
"""

import ast
import re
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql.base import RESERVED_WORDS

from app.models import Base

VERSIONS = Path(__file__).resolve().parent.parent / "alembic" / "versions"
RESERVED_COLUMNS = sorted({c.name for t in Base.metadata.tables.values() for c in t.columns
                           if c.name.lower() in RESERVED_WORDS})


def _raw_sql_strings(path: Path) -> list[str]:
    """The SQL text of every CheckConstraint and op.execute call in a migration."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and node.args:
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name in ("CheckConstraint", "execute") and isinstance(node.args[0], ast.Constant) \
                    and isinstance(node.args[0].value, str):
                out.append(node.args[0].value)
    return out


def test_the_models_have_a_reserved_word_column_to_guard():
    assert "window" in RESERVED_COLUMNS  # backtest_metrics.window: the case this file exists for


@pytest.mark.parametrize("path", sorted(VERSIONS.glob("*.py")), ids=lambda p: p.name[:4])
def test_reserved_words_are_quoted_in_raw_sql(path):
    for sql in _raw_sql_strings(path):
        unquoted = re.sub(r'"[^"]*"|\'[^\']*\'', "", sql)  # drop quoted identifiers and literals
        for column in RESERVED_COLUMNS:
            assert not re.search(rf"\b{column}\b", unquoted, re.IGNORECASE), f"bare {column!r} in: {sql}"


def test_the_models_compile_to_valid_postgresql_identifiers():
    """create_all (the PostgreSQL test fixture) builds Enum CHECKs as expressions, which the
    dialect quotes: check that stays true."""
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(sa.schema.CreateTable(table).compile(dialect=dialect))
        for column in RESERVED_COLUMNS:
            assert not re.search(rf"CHECK \({column}\b", ddl), f"{table.name}: bare {column} in a CHECK"
