"""One polite HTTP client per source: pacing, retries with backoff, a raw-response cache.

- Pacing: at least `min_interval_seconds` between the end of one request and the start of
  the next, one request at a time (GDELT asks for one every 5 seconds and enforces it
  with blocks of hours; it gets 60, catalog.json).
- Retries: timeouts, connection errors, 429 and 5xx, with exponential backoff and jitter,
  honouring Retry-After. A 429 waits `cooldown_429_seconds`, doubling. Other 4xx fail at once.
- Errors: FetchError, whose message is redacted and which never chains the httpx
  exception (its message holds the full URL, key and all).
- Cache: every successful body, redacted, under <cache>/<source>/<day>/<hash>.json, the
  hash taken from the URL without its key; index.jsonl lists url, status and time.
"""

import hashlib
import json
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from app.signals.catalog import HttpPolicy
from app.signals.redact import Redactor


class FetchError(Exception):
    """A request that failed for good. The message is already redacted."""


@dataclass
class Response:
    status: int
    text: str
    url: str  # redacted

    def json(self) -> Any:
        # GDELT titles sometimes carry raw control characters: strict=False accepts them.
        return json.loads(self.text, strict=False)


class RawCache:
    def __init__(self, root: Path):
        self.root = root

    def write(self, source: str, url: str, status: int, body: str, when: datetime) -> Path:
        day = self.root / source / when.strftime("%Y-%m-%d")
        day.mkdir(parents=True, exist_ok=True)
        path = day / f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.json"
        path.write_text(body, encoding="utf-8")
        with (day / "index.jsonl").open("a", encoding="utf-8") as index:
            index.write(json.dumps({"url": url, "status": status, "at": when.isoformat(), "file": path.name}) + "\n")
        return day


class SignalHttp:
    def __init__(self, source: str, policy: HttpPolicy, redactor: Redactor, *, user_agent: str,
                 transport: httpx.BaseTransport | None = None, cache: RawCache | None = None,
                 sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                 seed: int = 0, on_retry: Callable[[str], None] = lambda _msg: None):
        self.source = source
        self.policy = policy
        self.redactor = redactor
        self.cache = cache
        self.sleep = sleep
        self.clock = clock
        self.on_retry = on_retry
        self.requests = 0
        self.cache_dirs: set[Path] = set()
        self._rng = random.Random(seed)
        self._last_end: float | None = None
        self._client = httpx.Client(transport=transport, timeout=policy.timeout_seconds,
                                    headers={"User-Agent": user_agent, "Accept": "application/json"},
                                    follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SignalHttp":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _pace(self) -> None:
        if self._last_end is not None:
            wait = self.policy.min_interval_seconds - (self.clock() - self._last_end)
            if wait > 0:
                self.sleep(wait)

    def _wait_before(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                return min(float(retry_after), self.policy.max_wait_seconds)
            if response.status_code == 429:
                return min(self.policy.cooldown_429_seconds * 2 ** (attempt - 1), self.policy.max_wait_seconds)
        base = min(self.policy.backoff_seconds * 2 ** (attempt - 1), self.policy.max_wait_seconds)
        return base + self._rng.uniform(0, base / 4)

    def get(self, url: str, params: dict[str, Any] | None = None) -> Response:
        request_url = str(httpx.URL(url, params=params or {}))
        safe_url = self.redactor.redact(request_url)
        problem = ""
        for attempt in range(1, self.policy.max_attempts + 1):
            self._pace()
            response: httpx.Response | None = None
            try:
                response = self._client.get(request_url)
            except httpx.TransportError as exc:
                problem = f"{type(exc).__name__}"
            finally:
                self._last_end = self.clock()
                self.requests += 1
            if response is not None:
                status = response.status_code
                if status < 400:
                    body = self.redactor.redact(response.text)
                    if self.cache is not None:
                        self.cache_dirs.add(self.cache.write(self.source, safe_url, status, body,
                                                             datetime.now(UTC)))
                    return Response(status, body, safe_url)
                snippet = " ".join(self.redactor.redact(response.text[:160]).split())
                problem = f"HTTP {status}" + (f": {snippet}" if snippet else "")
                if status != 429 and status < 500:
                    raise FetchError(f"{problem} from {safe_url}")
            if attempt < self.policy.max_attempts:
                wait = self._wait_before(attempt, response)
                self.on_retry(f"  {self.source}: {problem.split(':')[0]}, retrying in {wait:.0f}s "
                              f"(attempt {attempt + 1} of {self.policy.max_attempts})")
                self.sleep(wait)
        raise FetchError(f"{problem} from {safe_url}, after {self.policy.max_attempts} attempts")
