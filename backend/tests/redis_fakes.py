"""Shared helpers for the Redis test doubles.

The rate limiter runs as a Lua script so the window check and the record of
the call happen atomically. The test doubles cannot run Lua, so they emulate
the same sliding window in memory.
"""

from typing import Any


class SlidingWindowCounter:
    """In-memory stand-in for the Redis sliding window script."""

    def __init__(self) -> None:
        self.windows: dict[str, list[int]] = {}

    def apply(
        self,
        key: str,
        now_ms: int,
        window_ms: int,
        limit: int,
        member: str,
    ) -> list[int]:
        entries = [stamp for stamp in self.windows.get(key, []) if stamp > now_ms - window_ms]

        if len(entries) >= limit:
            oldest = min(entries)
            retry_after = max(1, -(-(oldest + window_ms - now_ms) // 1000))
            self.windows[key] = entries
            return [0, retry_after]

        entries.append(now_ms)
        self.windows[key] = entries
        return [1, 0]

    def reset(self) -> None:
        self.windows.clear()


def is_rate_limit_call(number_of_keys: int) -> bool:
    """The rate limiter uses a single Redis key; the click script uses two."""

    return number_of_keys == 1


def rate_limit_arguments(args: tuple[Any, ...]) -> tuple[str, int, int, int, str]:
    key, now_ms, window_ms, limit, member = args
    return str(key), int(now_ms), int(window_ms), int(limit), str(member)
