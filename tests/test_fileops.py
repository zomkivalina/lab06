import pytest

from closures import make_logger
from fileops import FileService, FlakyStorage, MemoryStorage, make_file_service


def service(
    storage: FlakyStorage | MemoryStorage, sleeps: list[float], **kw: int
) -> FileService:
    ticks = iter(float(i) for i in range(1000))
    return make_file_service(
        storage,
        sleep=sleeps.append,
        logger=lambda _: None,
        clock=lambda: next(ticks),
        **kw,  # type: ignore[arg-type]
    )


def test_read_succeeds_after_transient_errors() -> None:
    sleeps: list[float] = []
    storage = FlakyStorage(MemoryStorage({"a.txt": "data"}), read_failures=2)
    svc = service(storage, sleeps)
    assert svc.read("a.txt") == "data"
    assert sleeps == [0.05, 0.1]  # дві паузи між трьома спробами
    assert svc.read_attempts.stats().calls == 3
    assert svc.read_attempts.stats().failures == 2
    assert svc.read.stats().calls == 1 and svc.read.stats().successes == 1


def test_write_and_copy_with_failures() -> None:
    sleeps: list[float] = []
    memory = MemoryStorage({"src.txt": "hello"})
    svc = service(FlakyStorage(memory, write_failures=1), sleeps)
    svc.copy("src.txt", "dst.txt")
    assert memory.files == {"src.txt": "hello", "dst.txt": "hello"}
    assert svc.write_attempts.stats().calls == 2


def test_gives_up_when_failures_exceed_attempts() -> None:
    sleeps: list[float] = []
    storage = FlakyStorage(MemoryStorage({"a.txt": "x"}), read_failures=10)
    svc = service(storage, sleeps, attempts=3)
    with pytest.raises(TimeoutError):
        svc.read("a.txt")
    assert svc.read_attempts.stats().calls == 3
    assert svc.read.stats().failures == 1
    assert "TimeoutError" in (svc.read.stats().last_error or "")


def test_missing_file_is_not_retried() -> None:
    sleeps: list[float] = []
    svc = service(MemoryStorage(), sleeps)
    with pytest.raises(FileNotFoundError):
        svc.read("nope.txt")
    assert sleeps == [] and svc.read_attempts.stats().calls == 1


def test_permission_error_is_transient() -> None:
    sleeps: list[float] = []
    storage = FlakyStorage(MemoryStorage(), write_failures=1, error=PermissionError)
    svc = service(storage, sleeps)
    svc.write("out.txt", "ok")
    assert storage.inner.read_text("out.txt") == "ok"


def test_closure_logger_receives_retry_messages() -> None:
    log = make_logger("FILE")
    storage = FlakyStorage(MemoryStorage({"a.txt": "x"}), read_failures=1)
    svc = make_file_service(storage, sleep=lambda _: None, logger=log)
    svc.read("a.txt")
    history = log.history()
    assert history[0].startswith("[FILE #1] read_text: спроба 1/4 — TimeoutError")
    assert history[-1].startswith("[FILE #2] read took")


def test_metadata_preserved_through_all_layers() -> None:
    svc = service(MemoryStorage({"a.txt": "x"}), [])
    assert svc.read.__name__ == "read_text"
    assert svc.read.__wrapped__ is not None
