"""Failed sign-ins per (client IP, email) in a sliding window.

In-memory and per process: fine for one uvicorn process, wrong behind several workers
or after a restart (see Known issues in CLAUDE.md).
"""

import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class LoginRateLimiter:
    def __init__(self, max_failures: int = 5, window_seconds: float = 15 * 60,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.clock = clock
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: tuple[str, str], now: float) -> deque[float]:
        failures = self._failures[key]
        while failures and failures[0] <= now - self.window_seconds:
            failures.popleft()
        return failures

    def retry_after(self, key: tuple[str, str]) -> int | None:
        """Seconds until another attempt is allowed, or None if one is allowed now."""
        with self._lock:
            now = self.clock()
            failures = self._prune(key, now)
            if len(failures) < self.max_failures:
                return None
            return max(1, math.ceil(failures[0] + self.window_seconds - now))

    def record_failure(self, key: tuple[str, str]) -> None:
        with self._lock:
            now = self.clock()
            self._prune(key, now).append(now)

    def reset(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._failures.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginRateLimiter()
