"""Keep secrets out of everything a command prints, logs or stores.

The FRED key travels in the request URL (FRED accepts it only as `api_key=`), and httpx
puts the URL into its log lines and its exception messages. So the key is masked at
every exit, not just in the fetcher:

- log records (a record factory, plus a formatter on the CLI's handler for tracebacks);
- the httpx and httpcore loggers, which log full request URLs at INFO, are held at WARNING;
- sys.stdout and sys.stderr themselves, line by line: print(), warnings and the
  interpreter's own traceback of an uncaught exception all go through them;
- sys.excepthook and threading.excepthook, which format the traceback and mask it;
- error text stored in the database (`last_error`, `signal_fetches.error`) and the raw
  response cache (`redact` before writing).

What is masked: the FRED key, the JWT secret, every `api_key=...` query value, and from
the database URLs their password, host, and user / Supabase project reference.
"""

import io
import logging
import re
import sys
import threading
import traceback
from collections.abc import Iterable
from urllib.parse import urlsplit

MASK = "***"
_API_KEY = re.compile(r"(api_key=)[^&\s'\"<>]+", re.IGNORECASE)
_PUBLIC_HOSTS = {"localhost", "127.0.0.1", "::1"}
_MIN_SECRET = 4  # never mask a 1-3 character fragment: it would shred ordinary text


class Redactor:
    def __init__(self, secrets: Iterable[str] = ()):
        self.secrets = sorted({s for s in secrets if s and len(s) >= _MIN_SECRET}, key=len, reverse=True)

    def redact(self, text: str) -> str:
        if not text:
            return text
        for secret in self.secrets:
            if secret in text:
                text = text.replace(secret, MASK)
        return _API_KEY.sub(rf"\g<1>{MASK}", text)


def url_secrets(url: str) -> list[str]:
    """The sensitive parts of a database URL: the whole URL, password, host and user."""
    if not url or url.startswith("sqlite"):
        return []
    out = [url]
    try:
        parts = urlsplit(url)
    except ValueError:
        return out
    if parts.password:
        out.append(parts.password)
    if parts.hostname and parts.hostname not in _PUBLIC_HOSTS:
        out.append(parts.hostname)
    if parts.username and "." in parts.username:  # postgres.<project-ref> on Supabase
        out += [parts.username, parts.username.split(".", 1)[1]]
    return out


def secret_values(settings) -> list[str]:
    return [settings.fred_api_key, settings.jwt_secret,
            *url_secrets(settings.database_url), *url_secrets(settings.test_database_url)]


class RedactingStream(io.TextIOBase):
    """A text stream that masks secrets line by line before writing to `inner`.

    Buffered to the end of a line so a secret split across two write() calls (print()
    writes the text and the newline separately) is still masked."""

    def __init__(self, inner, redactor: Redactor):
        self.inner = inner
        self.redactor = redactor
        self._pending = ""

    def write(self, text: str) -> int:
        self._pending += text
        if "\n" in self._pending:
            complete, self._pending = self._pending.rsplit("\n", 1)
            self.inner.write(self.redactor.redact(complete + "\n"))
        return len(text)

    def flush(self) -> None:
        if self._pending:
            self.inner.write(self.redactor.redact(self._pending))
            self._pending = ""
        self.inner.flush()

    def writable(self) -> bool:
        return True

    @property
    def encoding(self):  # type: ignore[override]
        return getattr(self.inner, "encoding", "utf-8")

    def isatty(self) -> bool:
        return self.inner.isatty()

    def fileno(self) -> int:
        return self.inner.fileno()

    def __getattr__(self, name):
        return getattr(self.inner, name)


class RedactingFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor, fmt: str | None = None):
        super().__init__(fmt)
        self.redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        return self.redactor.redact(super().format(record))


class Guard:
    """What install_redaction changed, so a test can put it back."""

    def __init__(self, redactor: Redactor, saved: dict):
        self.redactor = redactor
        self._saved = saved

    def redact(self, text: str) -> str:
        return self.redactor.redact(text)

    def restore(self) -> None:
        for target, name, value in self._saved["attrs"]:
            setattr(target, name, value)
        logging.setLogRecordFactory(self._saved["factory"])
        root = logging.getLogger()
        for handler in self._saved["handlers"]:
            root.removeHandler(handler)


def install_redaction(secrets: Iterable[str], *, streams: bool = True) -> Guard:
    redactor = Redactor(secrets)
    saved: dict = {"attrs": [], "handlers": [], "factory": logging.getLogRecordFactory()}

    base_factory = saved["factory"]

    def factory(*args, **kwargs):
        record = base_factory(*args, **kwargs)
        try:
            message = record.getMessage()
        except Exception:  # a malformed %-format: leave it to the handler to report
            return record
        record.msg, record.args = redactor.redact(message), ()
        return record

    logging.setLogRecordFactory(factory)
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    def excepthook(exc_type, exc, tb):
        sys.stderr.write(redactor.redact("".join(traceback.format_exception(exc_type, exc, tb))))
        sys.stderr.flush()

    def thread_excepthook(args):
        if args.exc_type is SystemExit:
            return
        excepthook(args.exc_type, args.exc_value, args.exc_traceback)

    saved["attrs"] += [(sys, "excepthook", sys.excepthook), (threading, "excepthook", threading.excepthook)]
    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook

    if streams:
        saved["attrs"] += [(sys, "stdout", sys.stdout), (sys, "stderr", sys.stderr)]
        sys.stdout = RedactingStream(sys.stdout, redactor)
        sys.stderr = RedactingStream(sys.stderr, redactor)
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(RedactingFormatter(redactor, "%(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        saved["handlers"].append(handler)
    return Guard(redactor, saved)
