from __future__ import annotations

import collections
import functools
import logging
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def retry(
    times: int = 3,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry the wrapped function up to *times* attempts on any listed exception."""

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            for attempt in range(1, times + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions:
                    if attempt == times:
                        raise
            raise AssertionError("unreachable")  # pragma: no cover

        return wrapper

    return decorator


def rate_limit(
    calls: int,
    period: float,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Allow at most *calls* invocations per *period* seconds (sliding-window)."""

    def decorator(fn: Callable[P, T]) -> Callable[P, T]:
        timestamps: collections.deque[float] = collections.deque()

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            now = time.monotonic()
            while timestamps and timestamps[0] <= now - period:
                timestamps.popleft()
            if len(timestamps) >= calls:
                sleep_for = period - (now - timestamps[0])
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.monotonic()
                while timestamps and timestamps[0] <= now - period:
                    timestamps.popleft()
            timestamps.append(time.monotonic())
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def log_execution(fn: Callable[P, T]) -> Callable[P, T]:
    """Log the function name and elapsed time on every call; re-raise any exception."""

    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        logger.debug("calling %s", fn.__name__)
        start = time.monotonic()
        try:
            result = fn(*args, **kwargs)
            logger.debug("%s finished in %.3fs", fn.__name__, time.monotonic() - start)
            return result
        except Exception:
            logger.debug("%s raised after %.3fs", fn.__name__, time.monotonic() - start)
            raise

    return wrapper
