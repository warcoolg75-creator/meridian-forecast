"""The FRED key never reaches stdout, stderr, a log, the database or the cache.

FRED takes its key only in the URL, and httpx writes the URL into its log lines and its
exception messages. The subprocess tests run the real CLI (as make does) with a planted
fake key, FRED's recorded answer to a bad key, and httpx's own raise_for_status, so the
exception that escapes carries the full URL, key included. They assert the key appears in
neither output stream, whether the error is isolated, re-raised by --fail-fast, or
uncaught at the top of the interpreter. The child process refuses network access too.
"""

import io
import logging
import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

from app.config import BACKEND_DIR, Settings
from app.signals.redact import MASK, RedactingStream, Redactor, install_redaction, secret_values, url_secrets
from tests.signals_fixture import FAKE_FRED_KEY, FIXTURES

PG_URL = "postgresql+psycopg://postgres.abcdefghijklmnop:s3cretPassw0rd@pooler.db.example.test:5432/postgres"


def test_redactor_masks_the_key_any_api_key_and_database_url_parts():
    settings = Settings(_env_file=None, fred_api_key=FAKE_FRED_KEY, database_url=PG_URL, jwt_secret="jwt-secret-x")
    redactor = Redactor(secret_values(settings))
    text = (f"GET https://api.stlouisfed.org/fred/series/observations?series_id=X&api_key={FAKE_FRED_KEY}&a=1 "
            f"other api_key=zzzz9999 | {PG_URL} | host pooler.db.example.test | jwt-secret-x")
    masked = redactor.redact(text)
    for secret in (FAKE_FRED_KEY, "zzzz9999", "s3cretPassw0rd", "abcdefghijklmnop", "pooler.db.example.test",
                   "jwt-secret-x"):
        assert secret not in masked
    assert "api_key=***&a=1" in masked and "series_id=X" in masked
    assert url_secrets("sqlite:///x.db") == []
    assert Redactor(["ab"]).redact("abc") == "abc"  # fragments under 4 characters are never masked


def test_the_stream_masks_a_key_split_across_writes():
    out = io.StringIO()
    stream = RedactingStream(out, Redactor([FAKE_FRED_KEY]))
    print("url ...api_key=", end="", file=stream)
    print(FAKE_FRED_KEY[:10], end="", file=stream)
    print(FAKE_FRED_KEY[10:], file=stream)
    stream.write("tail " + FAKE_FRED_KEY)
    stream.flush()
    assert FAKE_FRED_KEY not in out.getvalue() and FAKE_FRED_KEY[:10] not in out.getvalue()
    assert out.getvalue().count(MASK) == 2


def test_log_records_and_httpx_logging_are_masked():
    guard = install_redaction([FAKE_FRED_KEY], streams=False)
    try:
        captured = io.StringIO()
        handler = logging.StreamHandler(captured)
        logger = logging.getLogger("meridian.test.redaction")
        logger.addHandler(handler)
        logger.warning("fetching %s", f"https://x.test/?api_key={FAKE_FRED_KEY}")
        logger.removeHandler(handler)
        assert FAKE_FRED_KEY not in captured.getvalue() and "api_key=***" in captured.getvalue()
        assert logging.getLogger("httpx").level == logging.WARNING  # its INFO lines carry full URLs
    finally:
        guard.restore()


# --------------------------------------------------------------------------- subprocesses

CHILD = textwrap.dedent("""
    import socket, sys

    def refuse(event, args):  # this process may not reach any other machine either
        host = args[0] if event == "socket.getaddrinfo" else (
            args[1][0] if event == "socket.connect" and isinstance(args[1], tuple) else None)
        if host not in (None, "", "localhost", "::1") and not str(host).startswith("127."):
            raise RuntimeError(f"network access in a test child process: {event}")

    sys.addaudithook(refuse)

    import httpx
    real_get = httpx.Client.get

    def get_and_raise(self, url, **kwargs):  # what code calling raise_for_status() would do
        response = real_get(self, url, **kwargs)
        response.raise_for_status()  # HTTPStatusError: "Client error '400 ...' for url '...api_key=...'"
        return response

    httpx.Client.get = get_and_raise

    from app.cli import main
    code = main(sys.argv[1:])
    if __import__("os").environ.get("RAISE_AT_TOP") == "1":
        request = httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations?api_key="
                                + __import__("os").environ["FRED_API_KEY"])
        raise httpx.HTTPStatusError("Client error '400 Bad Request' for url '" + str(request.url) + "'",
                                    request=request, response=httpx.Response(400, request=request))
    raise SystemExit(code)
""")


def _run_cli(tmp_path: Path, *args: str, raise_at_top: bool = False) -> tuple[subprocess.CompletedProcess, Path]:
    script = tmp_path / "child.py"
    script.write_text(CHILD, encoding="utf-8")
    db = tmp_path / "child.db"
    env = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "MERIDIAN_PG_TESTS")}
    env.update(FRED_API_KEY=FAKE_FRED_KEY, DATABASE_URL=f"sqlite:///{db.as_posix()}",
               SIGNALS_REPLAY_DIR=str(FIXTURES / "fred-error"), SIGNALS_CACHE_DIR=str(tmp_path / "cache"),
               RAISE_AT_TOP="1" if raise_at_top else "0", PYTHONIOENCODING="utf-8")
    result = subprocess.run([sys.executable, str(script), *args], cwd=BACKEND_DIR, env=env, capture_output=True,
                            text=True, encoding="utf-8", timeout=120)
    return result, db


def _assert_masked(result: subprocess.CompletedProcess) -> None:
    for name, text in (("stdout", result.stdout), ("stderr", result.stderr)):
        assert FAKE_FRED_KEY not in text, f"the planted key leaked into {name}"
        assert FAKE_FRED_KEY[:12] not in text, f"part of the planted key leaked into {name}"


def test_an_isolated_fred_error_is_masked_in_output_and_database(tmp_path):
    result, db = _run_cli(tmp_path, "signals-refresh", "--source", "fred")
    _assert_masked(result)
    assert result.returncode == 1, result.stderr
    assert "fred: failed" in result.stdout and "HTTPStatusError" in result.stdout
    assert "api_key=***" in result.stdout  # the URL was there, masked
    with sqlite3.connect(db) as connection:
        stored = [r[0] or "" for r in connection.execute(
            "SELECT last_error FROM signal_sources UNION ALL SELECT last_error FROM signal_series "
            "UNION ALL SELECT error FROM signal_fetches")]
    assert any("api_key=***" in s for s in stored)
    assert not any(FAKE_FRED_KEY in s for s in stored)
    cache = [p.read_text(encoding="utf-8") for p in (tmp_path / "cache").rglob("*") if p.is_file()]
    assert not any(FAKE_FRED_KEY in c for c in cache)


def test_a_fail_fast_traceback_printed_by_the_cli_is_masked(tmp_path):
    result, _db = _run_cli(tmp_path, "signals-refresh", "--source", "fred", "--fail-fast")
    _assert_masked(result)
    assert result.returncode == 1
    assert "Traceback (most recent call last)" in result.stderr and "HTTPStatusError" in result.stderr
    assert "api_key=***" in result.stderr


def test_an_uncaught_exception_at_the_top_of_the_interpreter_is_masked(tmp_path):
    result, _db = _run_cli(tmp_path, "signals-status", raise_at_top=True)
    _assert_masked(result)
    assert result.returncode == 1
    assert "Traceback (most recent call last)" in result.stderr and "httpx.HTTPStatusError" in result.stderr
    assert "api_key=***" in result.stderr
