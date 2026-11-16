import pytest

from decorators import retries


def test_success_on_third_attempt_without_real_sleep() -> None:
    calls = {"n": 0}
    sleeps: list[float] = []

    @retries(attempts=3, delay=0.1, backoff=2.0, sleep=sleeps.append)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("boom")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
    assert sleeps == [0.1, 0.2]  # експоненційний backoff


def test_jitter_is_deterministic_with_fake_rng() -> None:
    sleeps: list[float] = []

    @retries(
        attempts=3,
        delay=1.0,
        backoff=3.0,
        jitter=0.5,
        rng=lambda: 0.5,
        sleep=sleeps.append,
    )
    def always_fails() -> None:
        raise OSError("x")

    with pytest.raises(OSError):
        always_fails()
    assert sleeps == [1.25, 3.25]  # 1*3^0 + 0.25, 1*3^1 + 0.25


def test_gives_up_after_last_attempt_and_logs() -> None:
    logs: list[str] = []

    @retries(attempts=2, delay=0, sleep=lambda _: None, logger=logs.append)
    def broken() -> None:
        raise PermissionError("locked")

    with pytest.raises(PermissionError):
        broken()
    assert len(logs) == 2 and "здаюся" in logs[-1]


def test_not_listed_and_give_up_exceptions_are_not_retried() -> None:
    calls = {"n": 0}

    @retries(
        attempts=5,
        exceptions=(OSError,),
        give_up_on=(FileNotFoundError,),
        delay=0,
        sleep=lambda _: None,
    )
    def missing() -> None:
        calls["n"] += 1
        raise FileNotFoundError("a.txt")

    with pytest.raises(FileNotFoundError):
        missing()

    @retries(attempts=5, exceptions=(OSError,), delay=0, sleep=lambda _: None)
    def bad_value() -> None:
        calls["n"] += 1
        raise ValueError("not an I/O error")

    with pytest.raises(ValueError):
        bad_value()
    assert calls["n"] == 2  # по одному виклику, без повторів


@pytest.mark.parametrize(
    "kwargs", [{"attempts": 0}, {"delay": -1}, {"backoff": 0.5}, {"jitter": -0.1}]
)
def test_bad_parameters(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        retries(**kwargs)  # type: ignore[arg-type]


def test_single_attempt_and_metadata() -> None:
    @retries(attempts=1, sleep=lambda _: None)
    def read_config() -> str:
        """Читає конфіг."""
        return "cfg"

    assert read_config() == "cfg"
    assert read_config.__name__ == "read_config"
    assert read_config.__doc__ == "Читає конфіг."
