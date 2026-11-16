"""Параметризовані декоратори: timed, retries, cached, call_stats.

Усі зовнішні залежності (годинник, sleep, логер, генератор випадкових чисел)
передаються як Callable, тому в тестах їх легко підмінити фейками.
"""

import functools
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, cast

from closures import make_backoff

type Logger = Callable[[str], None]
type Decorator[**P, R] = Callable[[Callable[P, R]], Callable[P, R]]

UNITS = {"s": 1.0, "ms": 1_000.0, "us": 1_000_000.0}


def _silent(_: str) -> None:
    """Логер за замовчуванням: нічого не виводить."""


# ---------- @timed ----------


def timed[**P, R](
    label: str | None = None,
    *,
    unit: str = "ms",
    logger: Logger = _silent,
    clock: Callable[[], float] = time.perf_counter,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Логує час виконання; запис робиться у finally — навіть якщо був виняток."""
    if unit not in UNITS:
        raise ValueError(f"unit має бути одним із {sorted(UNITS)}")
    scale = UNITS[unit]

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name = label or func.__name__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = clock()
            ok = False
            try:
                result = func(*args, **kwargs)
                ok = True
                return result
            finally:
                elapsed = (clock() - start) * scale
                status = "" if ok else " (з винятком)"
                logger(f"{name} took {elapsed:.3f} {unit}{status}")

        return wrapper

    return decorator


# ---------- @retries ----------


def retries[**P, R](
    attempts: int = 3,
    *,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    give_up_on: tuple[type[BaseException], ...] = (),
    delay: float = 0.1,
    backoff: float = 2.0,
    jitter: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    logger: Logger = _silent,
    rng: Callable[[], float] = random.random,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Повтори з експоненційним backoff.

    Повторюються лише винятки з exceptions, крім give_up_on (постійні помилки,
    напр. FileNotFoundError). Після останньої спроби виняток пробрасується далі.
    """
    if attempts < 1:
        raise ValueError("attempts має бути >= 1")
    if delay < 0 or jitter < 0 or backoff < 1:
        raise ValueError("delay, jitter >= 0 і backoff >= 1")
    pause = make_backoff(delay, backoff, jitter, rng)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if isinstance(exc, give_up_on):
                        logger(f"{func.__name__}: {type(exc).__name__} — не повторюю")
                        raise
                    if attempt == attempts:
                        logger(
                            f"{func.__name__}: спроба {attempt}/{attempts} — "
                            f"{type(exc).__name__}, здаюся"
                        )
                        raise
                    wait = pause(attempt)
                    logger(
                        f"{func.__name__}: спроба {attempt}/{attempts} — "
                        f"{type(exc).__name__}: {exc}; чекаю {wait:.3f} с"
                    )
                    sleep(wait)
            raise AssertionError("недосяжно")  # для mypy: цикл завжди повертає/кидає

        return wrapper

    return decorator


# ---------- @cached ----------

type Key = tuple[tuple[Any, ...], tuple[tuple[str, Any], ...]]


class CachedFunction[**P, R](Protocol):
    __name__: str
    __wrapped__: Callable[P, R]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def cache_clear(self) -> None: ...
    def cache_invalidate(
        self, predicate: Callable[[tuple[Any, ...], dict[str, Any]], bool]
    ) -> int: ...
    def cache_info(self) -> dict[str, int]: ...


def cached[**P, R](
    ttl: float | None = None, *, time_fn: Callable[[], float] = time.monotonic
) -> Callable[[Callable[P, R]], CachedFunction[P, R]]:
    """Кеш результатів з TTL. Ключ — (args, відсортовані kwargs), усе хешоване."""
    if ttl is not None and ttl <= 0:
        raise ValueError("ttl має бути > 0 або None")

    def decorator(func: Callable[P, R]) -> CachedFunction[P, R]:
        store: dict[Key, tuple[float, R]] = {}
        hits = misses = 0

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            nonlocal hits, misses
            key: Key = (tuple(args), tuple(sorted(kwargs.items())))
            try:
                hash(key)
            except TypeError:
                raise TypeError("cached: усі аргументи мають бути хешованими") from None
            now = time_fn()
            if key in store:
                saved_at, value = store[key]
                if ttl is None or now - saved_at < ttl:
                    hits += 1
                    return value
                del store[key]  # «протухло»
            misses += 1
            value = func(*args, **kwargs)
            store[key] = (now, value)
            return value

        def cache_clear() -> None:
            nonlocal hits, misses
            store.clear()
            hits = misses = 0

        def cache_invalidate(
            predicate: Callable[[tuple[Any, ...], dict[str, Any]], bool],
        ) -> int:
            doomed = [k for k in store if predicate(k[0], dict(k[1]))]
            for k in doomed:
                del store[k]
            return len(doomed)

        def cache_info() -> dict[str, int]:
            return {"hits": hits, "misses": misses, "size": len(store)}

        w = cast(Any, wrapper)
        w.cache_clear = cache_clear
        w.cache_invalidate = cache_invalidate
        w.cache_info = cache_info
        return cast(CachedFunction[P, R], wrapper)

    return decorator


# ---------- @call_stats (варіант 6) ----------


@dataclass(frozen=True, slots=True)
class Stats:
    calls: int
    successes: int
    failures: int
    total_time: float
    last_error: str | None


class StatsFunction[**P, R](Protocol):
    __name__: str
    __wrapped__: Callable[P, R]

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R: ...
    def stats(self) -> Stats: ...
    def reset_stats(self) -> None: ...


def call_stats[**P, R](
    *, clock: Callable[[], float] = time.perf_counter
) -> Callable[[Callable[P, R]], StatsFunction[P, R]]:
    """Статистика викликів: скільки разів, скільки успіхів/помилок, сумарний час."""

    def decorator(func: Callable[P, R]) -> StatsFunction[P, R]:
        calls = successes = failures = 0
        total = 0.0
        last_error: str | None = None

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            nonlocal calls, successes, failures, total, last_error
            calls += 1
            start = clock()
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                failures += 1
                last_error = f"{type(exc).__name__}: {exc}"
                raise
            else:
                successes += 1
                return result
            finally:
                total += clock() - start

        def stats() -> Stats:
            return Stats(calls, successes, failures, round(total, 6), last_error)

        def reset_stats() -> None:
            nonlocal calls, successes, failures, total, last_error
            calls = successes = failures = 0
            total = 0.0
            last_error = None

        w = cast(Any, wrapper)
        w.stats = stats
        w.reset_stats = reset_stats
        return cast(StatsFunction[P, R], wrapper)

    return decorator
