"""Small, injectable rate-limit implementations for API boundaries.

The default implementation is intentionally instance-scoped.  Production can
replace it with a shared Redis/Firestore adapter without changing dependencies.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock


class RateLimitExceededError(RuntimeError):
    code = "RATE_LIMITED"
    status_code = 429

    def __init__(self, *, retry_after: int, limit: int, dimension: str) -> None:
        self.retry_after = max(1, retry_after)
        self.limit = limit
        self.dimension = dimension
        super().__init__(f"rate limit exceeded for {dimension}")


RateLimitError = RateLimitExceededError


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    limit: int
    remaining: int
    reset_at: datetime


class InMemoryRateLimiter:
    """Thread-safe sliding-window limiter for local/tests and small deployments."""

    def __init__(
        self,
        *,
        user_limit: int = 30,
        project_limit: int = 300,
        ip_limit: int = 60,
        window_seconds: int = 60,
    ) -> None:
        if min(user_limit, project_limit, ip_limit, window_seconds) <= 0:
            raise ValueError("rate limits and window_seconds must be positive")
        self.user_limit = user_limit
        self.project_limit = project_limit
        self.ip_limit = ip_limit
        self.window_seconds = window_seconds
        self._events: dict[tuple[str, str], deque[float]] = {}
        self._lock = RLock()

    def check(
        self,
        user_id: str | None = None,
        project_id: str | None = None,
        ip_address: str | None = None,
        *,
        cost: int = 1,
        now: datetime | None = None,
    ) -> RateLimitDecision:
        if cost <= 0:
            raise ValueError("rate-limit cost must be positive")
        current = _timestamp(now)
        dimensions = tuple(
            (name, value, limit)
            for name, value, limit in (
                ("user", user_id, self.user_limit),
                ("project", project_id, self.project_limit),
                ("ip", ip_address, self.ip_limit),
            )
            if value
        )
        if not dimensions:
            return RateLimitDecision(
                limit=0,
                remaining=0,
                reset_at=datetime.fromtimestamp(current, tz=UTC),
            )

        with self._lock:
            cutoff = current - self.window_seconds
            prepared: list[tuple[tuple[str, str], deque[float], int]] = []
            for name, value, limit in dimensions:
                key = (name, value)
                events = self._events.setdefault(key, deque())
                while events and events[0] <= cutoff:
                    events.popleft()
                if len(events) + cost > limit:
                    retry_at = events[0] + self.window_seconds if events else current + 1
                    raise RateLimitExceededError(
                        retry_after=max(1, int(retry_at - current + 0.999)),
                        limit=limit,
                        dimension=name,
                    )
                prepared.append((key, events, limit))

            for _key, events, _limit in prepared:
                events.extend([current] * cost)

            primary_limit = prepared[0][2]
            primary_events = prepared[0][1]
            reset_at = datetime.fromtimestamp(
                primary_events[0] + self.window_seconds,
                tz=UTC,
            )
            return RateLimitDecision(
                limit=primary_limit,
                remaining=max(0, primary_limit - len(primary_events)),
                reset_at=reset_at,
            )

    allow = check


SlidingWindowRateLimiter = InMemoryRateLimiter


def _timestamp(value: datetime | None) -> float:
    current = value or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("rate-limit time must be timezone-aware")
    return current.timestamp()


__all__ = [
    "InMemoryRateLimiter",
    "RateLimitDecision",
    "RateLimitError",
    "RateLimitExceededError",
    "SlidingWindowRateLimiter",
]
