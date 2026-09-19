"""Basic login throttling (techspec §8): N failures for a key → cooldown.

In-memory on purpose: v1 runs as a single process on one machine (techspec §12). The key is
`email|client_ip`, so one attacker cannot lock out a user from elsewhere, and a shared office
IP does not lock everyone out at once.
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class _Entry:
    failures: int = 0
    blocked_until: float = 0.0
    window_start: float = field(default_factory=time.monotonic)


class LoginThrottle:
    def __init__(self, max_failures: int = 5, cooldown_s: float = 300.0, window_s: float = 900.0):
        self.max_failures = max_failures
        self.cooldown_s = cooldown_s
        self.window_s = window_s
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str, now: float | None = None) -> int:
        """Seconds the caller must still wait, 0 when allowed."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            e = self._entries.get(key)
            if e is None:
                return 0
            if e.blocked_until > now:
                return max(1, int(e.blocked_until - now + 0.999))
            if now - e.window_start > self.window_s:
                del self._entries[key]
            return 0

    def record_failure(self, key: str, now: float | None = None) -> int:
        """Register a failed attempt; returns the cooldown just imposed (0 if none)."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            e = self._entries.get(key)
            if e is None or now - e.window_start > self.window_s:
                e = _Entry(window_start=now)
                self._entries[key] = e
            e.failures += 1
            if e.failures >= self.max_failures:
                e.blocked_until = now + self.cooldown_s
                e.failures = 0
                e.window_start = now
                return int(self.cooldown_s)
            return 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
