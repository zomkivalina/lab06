"""Демонстрація: справжні файли в тимчасовому каталозі + штучні збої."""

import tempfile
from pathlib import Path

from closures import make_counter, make_logger
from decorators import Stats, cached
from fileops import DiskStorage, FlakyStorage, make_file_service


def show(title: str, s: Stats) -> None:
    print(
        f"  {title:<16} викликів {s.calls}, успіхів {s.successes}, "
        f"помилок {s.failures}, час {s.total_time * 1000:.2f} мс"
    )


def file_demo() -> None:
    print("=== ВАРІАНТ 6: ПОВТОРИ ФАЙЛОВИХ ОПЕРАЦІЙ ===")
    log = make_logger("FILE", sink=print)
    with tempfile.TemporaryDirectory() as tmp:
        disk = DiskStorage(Path(tmp))
        disk.write_text("report.txt", "Звіт за листопад: 42 записи\n")
        storage = FlakyStorage(disk, read_failures=2, write_failures=1)
        svc = make_file_service(storage, delay=0.02, backoff=2.0, logger=log)

        text = svc.read("report.txt")
        print(f"  прочитано: {text.strip()!r}")
        svc.write("backup.txt", text.upper())
        svc.copy("report.txt", "copy.txt")
        try:
            svc.read("missing.txt")
        except FileNotFoundError:
            print("  missing.txt не існує — постійна помилка, без повторів")
        print(f"  файли на диску: {sorted(p.name for p in Path(tmp).iterdir())}")

    print("\nСтатистика (@call_stats):")
    show("read: операції", svc.read.stats())
    show("read: спроби", svc.read_attempts.stats())
    show("write: операції", svc.write.stats())
    show("write: спроби", svc.write_attempts.stats())
    last = (svc.read.stats().last_error or "").split(":")[0]
    print(f"  остання помилка читання: {last}")
    print(f"  записів у closure-логері: {len(log.history())}")


def base_demo() -> None:
    print("\n=== БАЗОВІ ЗАМИКАННЯ ТА @cached ===")
    counter = make_counter(10)
    print(f"make_counter(10): {counter()}, {counter()}, {counter()}")

    now = [0.0]

    @cached(ttl=5.0, time_fn=lambda: now[0])
    def file_size(path: str) -> int:
        """Імітація «дорогого» запиту розміру файлу."""
        return len(path) * 100

    file_size("a.txt")
    file_size("a.txt")
    now[0] = 10.0  # TTL минув
    file_size("a.txt")
    file_size("b.txt")
    print(f"cache_info: {file_size.cache_info()}")
    removed = file_size.cache_invalidate(lambda args, kw: args == ("b.txt",))
    print(
        f"cache_invalidate('b.txt') видалив {removed}, тепер {file_size.cache_info()}"
    )
    print(f"@wraps: __name__={file_size.__name__!r}, __doc__={file_size.__doc__!r}")


def run() -> None:
    file_demo()
    base_demo()


if __name__ == "__main__":
    run()
