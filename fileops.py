"""Варіант 6: повторні спроби файлових операцій зі статистикою.

Сховище — залежність (Protocol), тому в тестах замість диска використовується
словник у пам'яті, а збої імітуються замиканням make_fault_injector.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from closures import make_fault_injector
from decorators import Decorator, Logger, StatsFunction, call_stats, retries, timed


class Storage(Protocol):
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, text: str) -> None: ...


class MemoryStorage:
    """Файли в пам'яті: без реального I/O."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files = dict(files or {})

    def read_text(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def write_text(self, path: str, text: str) -> None:
        self.files[path] = text


class DiskStorage:
    """Справжні файли в каталозі root (використовується лише в app.py)."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def read_text(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8")

    def write_text(self, path: str, text: str) -> None:
        (self.root / path).write_text(text, encoding="utf-8")


class FlakyStorage:
    """Обгортка, що перші N читань/записів завершуються тимчасовою помилкою."""

    def __init__(
        self,
        inner: Storage,
        *,
        read_failures: int = 0,
        write_failures: int = 0,
        error: Callable[[str], Exception] = TimeoutError,
    ) -> None:
        self.inner = inner
        self._read_fault = make_fault_injector(read_failures, error)
        self._write_fault = make_fault_injector(write_failures, error)

    def read_text(self, path: str) -> str:
        self._read_fault()
        return self.inner.read_text(path)

    def write_text(self, path: str, text: str) -> None:
        self._write_fault()
        self.inner.write_text(path, text)


@dataclass(frozen=True)
class FileService:
    read: StatsFunction[[str], str]  # логічні операції (з повторами)
    write: StatsFunction[[str, str], None]
    read_attempts: StatsFunction[[str], str]  # кожна окрема спроба
    write_attempts: StatsFunction[[str, str], None]

    def copy(self, src: str, dst: str) -> None:
        self.write(dst, self.read(src))


TRANSIENT = (TimeoutError, PermissionError, BlockingIOError, InterruptedError)


def make_file_service(
    storage: Storage,
    *,
    attempts: int = 4,
    delay: float = 0.05,
    backoff: float = 2.0,
    jitter: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
    logger: Logger = print,
    clock: Callable[[], float] = time.perf_counter,
    rng: Callable[[], float] = lambda: 0.0,
) -> FileService:
    """Фабрика: збирає операції з декораторів (знизу вгору):
    спроба → @call_stats(спроби) → @retries → @timed → @call_stats(операції)."""

    def protect[**P, R](
        op: Callable[P, R], name: str
    ) -> tuple[StatsFunction[P, R], StatsFunction[P, R]]:
        # анотації потрібні mypy, щоб зв'язати P і R фабрик декораторів
        count_attempts: Callable[[Callable[P, R]], StatsFunction[P, R]]
        count_attempts = call_stats(clock=clock)
        retry: Decorator[P, R] = retries(
            attempts,
            exceptions=(OSError,),
            give_up_on=(FileNotFoundError, IsADirectoryError),
            delay=delay,
            backoff=backoff,
            jitter=jitter,
            sleep=sleep,
            logger=logger,
            rng=rng,
        )
        timer: Decorator[P, R] = timed(name, unit="ms", logger=logger, clock=clock)
        count_ops: Callable[[Callable[P, R]], StatsFunction[P, R]]
        count_ops = call_stats(clock=clock)

        attempts_stats: StatsFunction[P, R] = count_attempts(op)
        operation = count_ops(timer(retry(attempts_stats)))
        return operation, attempts_stats

    read, read_attempts = protect(storage.read_text, "read")
    write, write_attempts = protect(storage.write_text, "write")
    return FileService(read, write, read_attempts, write_attempts)
