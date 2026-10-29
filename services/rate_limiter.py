"""RateLimiter: allow at most N actions per key in a rolling time window."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from exceptions import RateLimited


class RateLimiter:
    """Counts recent actions per key (e.g. per user) and refuses once the limit is reached.

    Uses a rolling window: an action counts for `per_seconds` after it happened.
    Safe to use from several Flask requests at once (a lock guards the counts).
    """

    def __init__(self, max_calls: int, per_seconds: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        """clock returns the current time in seconds; tests pass a fake one."""
        if max_calls < 1 or per_seconds <= 0:
            raise ValueError("A rate limit needs at least 1 call and a positive time window.")
        self._max_calls: int = max_calls
        self._per_seconds: float = per_seconds
        self._clock: Callable[[], float] = clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def max_calls(self) -> int:
        """How many actions are allowed in one window."""
        return self._max_calls

    def check(self, key: str, what: str = "requests") -> None:
        """Record one action for this key, or raise RateLimited if the limit is reached.

        what: the action in words for the message, e.g. "questions".
        """
        with self._lock:
            now = self._clock()
            calls = self._calls[key]
            while calls and now - calls[0] >= self._per_seconds:
                calls.popleft()  # older than the window: no longer counts
            if len(calls) >= self._max_calls:
                wait = max(1, round(self._per_seconds - (now - calls[0])))
                raise RateLimited(
                    f"That's {self._max_calls} {what} in the last {self._per_seconds:g} seconds.",
                    next_step=f"Please wait {wait} seconds and try again.",
                )
            calls.append(now)
