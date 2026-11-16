from collections.abc import Callable

import pytest

from closures import make_backoff, make_counter, make_fault_injector, make_logger


def test_counter_keeps_state_and_is_independent() -> None:
    a, b = make_counter(), make_counter(10)
    assert [a(), a(), a()] == [1, 2, 3]
    assert b() == 11  # окремий стан у кожного замикання
    assert a.__closure__ is not None  # value — вільна змінна


def test_logger_prefix_numbering_and_history_copy() -> None:
    sink: list[str] = []
    log = make_logger("FILE", sink=sink.append)
    log("one")
    log("two")
    assert log.history() == ["[FILE #1] one", "[FILE #2] two"]
    assert sink == log.history()
    log.history().clear()  # повертається копія
    assert len(log.history()) == 2


def test_fault_injector_fails_exactly_n_times() -> None:
    check = make_fault_injector(2, TimeoutError)
    for _ in range(2):
        with pytest.raises(TimeoutError):
            check()
    check()
    check()  # далі — без помилок


def test_backoff_policy() -> None:
    pause = make_backoff(0.1, 2.0, 0.5, rng=lambda: 0.2)
    assert [round(pause(n), 3) for n in (1, 2, 3)] == [0.2, 0.3, 0.5]


def test_loop_variable_trap() -> None:
    wrong: list[Callable[[], int]] = [lambda: i for i in range(3)]  # noqa: B023

    def make(i: int) -> Callable[[], int]:  # локальна фабрика фіксує значення
        return lambda: i

    right = [make(i) for i in range(3)]
    assert [f() for f in wrong] == [2, 2, 2]
    assert [f() for f in right] == [0, 1, 2]
