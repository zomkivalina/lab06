import pytest

from decorators import call_stats


def test_counts_successes_failures_and_time() -> None:
    ticks = iter([0.0, 0.5, 1.0, 1.25])

    @call_stats(clock=lambda: next(ticks))
    def maybe(ok: bool) -> str:
        """Іноді падає."""
        if not ok:
            raise OSError("disk full")
        return "done"

    assert maybe(True) == "done"
    with pytest.raises(OSError):
        maybe(False)
    s = maybe.stats()
    assert (s.calls, s.successes, s.failures) == (2, 1, 1)
    assert s.total_time == 0.75
    assert s.last_error == "OSError: disk full"
    assert maybe.__name__ == "maybe" and maybe.__doc__ == "Іноді падає."


def test_reset_and_independent_state() -> None:
    @call_stats()
    def a() -> None: ...

    @call_stats()
    def b() -> None: ...

    a()
    a()
    b()
    assert a.stats().calls == 2 and b.stats().calls == 1
    a.reset_stats()
    assert a.stats().calls == 0 and a.stats().last_error is None
