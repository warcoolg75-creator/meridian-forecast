"""PostgreSQL is opt-in on the command line, and a default run cannot reach it.

On 2026-10-20 a plain `pytest` took TEST_DATABASE_URL from .env and dropped every table
of the hosted copy of the pinned dataset. Since then only MERIDIAN_PG_TESTS=1 in the
process environment selects PostgreSQL, and a SQLite run refuses any other database
connection and any network access beyond this machine (conftest.py).
"""

import socket

import pytest

from app.config import Settings
from app.db import create_db_engine
from tests.conftest import HAS_PG, postgres_url_for_tests

PG = "postgresql://user:secret@db.example.test:5432/meridian"

sqlite_run_only = pytest.mark.skipif(HAS_PG, reason="the guards are off in a PostgreSQL run")


@pytest.mark.parametrize(
    ("environ", "expected"),
    [
        ({}, ""),  # .env names PostgreSQL, nothing on the command line: SQLite
        ({"MERIDIAN_PG_TESTS": "0"}, ""),
        ({"MERIDIAN_PG_TESTS": "true"}, ""),  # exactly "1", nothing looser
        ({"MERIDIAN_PG_TESTS": ""}, ""),
        ({"TEST_DATABASE_URL": PG}, ""),  # a URL in the environment is not an opt-in either
        ({"MERIDIAN_PG_TESTS": "1"}, PG),
    ],
)
def test_postgres_needs_the_command_line_opt_in(environ, expected):
    assert postgres_url_for_tests(environ, dotenv_url=PG) == expected


def test_opting_in_without_a_postgres_url_stops_the_run():
    with pytest.raises(pytest.UsageError, match="MERIDIAN_PG_TESTS=1 needs TEST_DATABASE_URL"):
        postgres_url_for_tests({"MERIDIAN_PG_TESTS": "1"}, dotenv_url="")


def test_dotenv_cannot_opt_in(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(f"MERIDIAN_PG_TESTS=1\nTEST_DATABASE_URL={PG}\n", encoding="utf-8")
    settings = Settings(_env_file=env_file)
    assert settings.test_database_url == PG  # .env does supply the URL...
    assert not hasattr(settings, "meridian_pg_tests")  # ...but the opt-in is not a setting
    assert postgres_url_for_tests({}, settings.test_database_url) == ""


@sqlite_run_only
def test_a_sqlite_run_refuses_a_postgres_connection():
    # TEST-NET-1 (192.0.2.0/24) is reserved and never routed: nothing real is contacted
    # even if the guard were missing.
    engine = create_db_engine("postgresql://user:secret@192.0.2.1:5432/meridian?connect_timeout=1")
    try:
        with pytest.raises(RuntimeError, match="MERIDIAN_PG_TESTS=1"):
            engine.connect()
    finally:
        engine.dispose()


@sqlite_run_only
def test_a_sqlite_run_refuses_remote_lookups_and_connections():
    with pytest.raises(RuntimeError, match="socket.getaddrinfo"):
        socket.getaddrinfo("db.example.test", 5432)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        with pytest.raises(RuntimeError, match="socket.connect"):
            sock.connect(("192.0.2.1", 5432))
    # This machine stays reachable: the test client's event loop needs loopback sockets.
    assert socket.getaddrinfo("localhost", 0)
