"""Замикання: стан у вільних змінних і ін'єкція залежностей."""

from collections.abc import Callable


def make_counter(start: int = 0) -> Callable[[], int]:
    """Лічильник: value — вільна змінна, яку змінює inc через nonlocal."""
    value = start

    def inc() -> int:
        nonlocal value
        value += 1
        return value

    return inc


class MemoryLogger:
    """Callable-логер з історією: зручно передавати в декоратори та в тести."""

    def __init__(self, log: Callable[[str], None], history: Callable[[], list[str]]):
        self._log = log
        self.history = history

    def __call__(self, msg: str) -> None:
        self._log(msg)


def make_logger(prefix: str, sink: Callable[[str], None] | None = None) -> MemoryLogger:
    """Closure-логер: пам'ятає prefix, лічильник записів і власну історію.

    sink — куди ще писати (наприклад, print); за замовчуванням лише в історію.
    """
    lines: list[str] = []
    number = 0

    def log(msg: str) -> None:
        nonlocal number
        number += 1
        line = f"[{prefix} #{number}] {msg}"
        lines.append(line)
        if sink is not None:
            sink(line)

    def history() -> list[str]:
        return list(lines)  # копія: ззовні історію не змінити

    return MemoryLogger(log, history)


def make_fault_injector(
    fail_times: int, error: Callable[[str], Exception]
) -> Callable[[], None]:
    """Імітація тимчасової помилки: перші fail_times викликів кидають виняток,
    далі — тиша. Лічильник збоїв живе в замиканні (nonlocal)."""
    failures_left = fail_times

    def check() -> None:
        nonlocal failures_left
        if failures_left > 0:
            failures_left -= 1
            raise error(f"тимчасова помилка, лишилось збоїв: {failures_left}")

    return check


def make_backoff(
    delay: float, backoff: float, jitter: float, rng: Callable[[], float]
) -> Callable[[int], float]:
    """Політика затримок: delay * backoff^(n-1) + jitter * rng()."""

    def pause(attempt: int) -> float:
        return delay * backoff ** (attempt - 1) + jitter * rng()

    return pause
