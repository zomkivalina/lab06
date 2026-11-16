import pytest

from decorators import timed


def test_timed_uses_clock_and_logger() -> None:
    ticks = iter([0.0, 0.012345])
    logs: list[str] = []

    @timed("work", unit="ms", logger=logs.append, clock=lambda: next(ticks))
    def work(x: int) -> int:
        """Квадрат числа."""
        return x * x

    assert work(5) == 25
    assert logs == ["work took 12.345 ms"]


def test_timed_logs_even_on_exception() -> None:
    ticks = iter([1.0, 1.5])
    logs: list[str] = []

    @timed(unit="s", logger=logs.append, clock=lambda: next(ticks))
    def boom() -> None:
        raise OSError("disk")

    with pytest.raises(OSError):
        boom()
    assert logs == ["boom took 0.500 s (з винятком)"]


def test_wraps_preserves_metadata() -> None:
    def square(x: int) -> int:
        """Квадрат числа."""
        return x * x

    wrapped = timed()(square)
    assert wrapped.__name__ == "square"
    assert wrapped.__doc__ == "Квадрат числа."
    assert wrapped.__wrapped__ is square  # type: ignore[attr-defined]


def test_bad_unit() -> None:
    with pytest.raises(ValueError):
        timed(unit="hours")
