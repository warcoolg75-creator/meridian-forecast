"""Row-level security is on for every table on PostgreSQL (migration 0002).

Checked against the current models, not 0002's frozen list, so a later migration that
adds a table without enabling RLS fails here. RLS must not be FORCEd: the app connects
as the tables' owner and relies on that exemption (the rest of the suite, running on
PostgreSQL, proves the app still reads and writes). Skipped unless TEST_DATABASE_URL
points at a PostgreSQL database; SQLite has no RLS.
"""

import sqlalchemy as sa

from app.models import Base
from tests.conftest import requires_pg


@requires_pg
def test_every_table_has_rls_enabled_and_not_forced(pg_engine):
    expected = sorted([table.name for table in Base.metadata.sorted_tables] + ["alembic_version"])
    with pg_engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relnamespace = current_schema()::regnamespace AND relkind = 'r' "
                "AND relname = ANY(:names) ORDER BY relname"
            ),
            {"names": expected},
        ).all()
    assert [tuple(row) for row in rows] == [(name, True, False) for name in expected]
