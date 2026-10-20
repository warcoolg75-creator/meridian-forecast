"""Week / month bucketing that runs inside the database, on both dialects.

PostgreSQL has date_trunc; SQLite has no equivalent, so each bucket is a custom
SQL construct with one compiler per dialect. Both branches must produce the same
date for the same input; tests/test_bucketing_dialects.py asserts that.

    week  -> the Monday on or before the date (ISO-8601 week, Monday start)
    month -> the first day of the date's month

PostgreSQL:  CAST(date_trunc('week', CAST(d AS TIMESTAMP)) AS DATE)
    date_trunc('week', ...) is already ISO (Monday). The explicit cast to TIMESTAMP
    (without time zone) stops PostgreSQL from picking the timestamptz overload,
    which would make the result depend on the session TimeZone.

SQLite:      date(d, '-' || ((CAST(strftime('%w', d) AS INTEGER) + 6) % 7) || ' days')
    strftime('%w') is 0=Sunday..6=Saturday, so (w + 6) % 7 is days since Monday.
    Month uses date(d, 'start of month'). SQLite's date() returns 'YYYY-MM-DD' text,
    which the Date result type parses back into a date.

add_days(d, n) -> the date n days after d (n may be negative). Analytics uses it to
bucket a comparison window into the current window's buckets (same days, shifted).

PostgreSQL:  (d + n)                      date + integer is a date
SQLite:      date(d, '+n days')           n is inlined, so it is part of the cache key

Any other dialect fails loudly at compile time instead of returning wrong buckets.
"""

import calendar
from datetime import date, timedelta
from enum import StrEnum

from sqlalchemy import Date, literal_column
from sqlalchemy.exc import CompileError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.functions import FunctionElement


class Granularity(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class week_start(FunctionElement[date]):
    type = Date()
    inherit_cache = True
    name = "week_start"


class month_start(FunctionElement[date]):
    type = Date()
    inherit_cache = True
    name = "month_start"


class add_days(FunctionElement[date]):
    """`column + n` days. Build it with shift_days(); n travels as literal SQL text so
    that two different shifts never share a cached statement."""

    type = Date()
    inherit_cache = True
    name = "add_days"


def shift_days(column: ColumnElement[date], n: int) -> ColumnElement[date]:
    return column if n == 0 else add_days(column, literal_column(str(int(n))))


def _days(element) -> int:
    return int(list(element.clauses)[1].name)


@compiles(week_start)
@compiles(month_start)
@compiles(add_days)
def _unsupported(element, compiler, **kw):
    raise CompileError(f"{element.name} is not implemented for dialect {compiler.dialect.name!r}")


@compiles(week_start, "postgresql")
def _week_start_pg(element, compiler, **kw):
    arg = compiler.process(element.clauses, **kw)
    return f"CAST(date_trunc('week', CAST({arg} AS TIMESTAMP)) AS DATE)"


@compiles(month_start, "postgresql")
def _month_start_pg(element, compiler, **kw):
    arg = compiler.process(element.clauses, **kw)
    return f"CAST(date_trunc('month', CAST({arg} AS TIMESTAMP)) AS DATE)"


@compiles(add_days, "postgresql")
def _add_days_pg(element, compiler, **kw):
    arg = compiler.process(list(element.clauses)[0], **kw)
    return f"({arg} + {_days(element)})"


@compiles(add_days, "sqlite")
def _add_days_sqlite(element, compiler, **kw):
    arg = compiler.process(list(element.clauses)[0], **kw)
    return f"date({arg}, '{_days(element):+d} days')"


@compiles(week_start, "sqlite")
def _week_start_sqlite(element, compiler, **kw):
    arg = compiler.process(element.clauses, **kw)
    return f"date({arg}, '-' || ((CAST(strftime('%w', {arg}) AS INTEGER) + 6) % 7) || ' days')"


@compiles(month_start, "sqlite")
def _month_start_sqlite(element, compiler, **kw):
    arg = compiler.process(element.clauses, **kw)
    return f"date({arg}, 'start of month')"


def period_start_expr(column: ColumnElement[date], granularity: Granularity) -> ColumnElement[date]:
    if granularity is Granularity.DAY:
        return column
    if granularity is Granularity.WEEK:
        return week_start(column)
    return month_start(column)


def period_start(d: date, granularity: Granularity) -> date:
    """Pure-Python reference for the SQL expressions above."""
    if granularity is Granularity.DAY:
        return d
    if granularity is Granularity.WEEK:
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def period_end(start: date, granularity: Granularity) -> date:
    if granularity is Granularity.DAY:
        return start
    if granularity is Granularity.WEEK:
        return start + timedelta(days=6)
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])
