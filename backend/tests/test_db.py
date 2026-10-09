"""Database URL handling."""

import pytest

from app.db import normalize_url


@pytest.mark.parametrize(("given", "expected"), [
    ("postgres://u:p@h/db?sslmode=require", "postgresql+psycopg://u:p@h/db?sslmode=require"),
    ("postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
    ("postgresql+psycopg://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("sqlite:///C:/x y/meridian.db", "sqlite:///C:/x y/meridian.db"),
])
def test_hosted_postgres_urls_use_psycopg3(given, expected):
    assert normalize_url(given) == expected
