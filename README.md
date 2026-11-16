# Лабораторна робота №6. Замикання та декоратори як HOF

**Студентка:** Зьомків А. І., група ФЕП-21
**Варіант:** 6 — «Повторні спроби файлової операції»

## Завдання варіанту
Closure-логер, `@retries` і декоратор статистики. Імітувати тимчасову помилку
читання/запису та успіх після кількох спроб. Реальний I/O у тестах не потрібен —
залежності підміняються.

## Що реалізовано
**`closures.py`** — замикання зі станом (`nonlocal`):
- `make_counter` — лічильник;
- `make_logger(prefix, sink)` — closure-логер з нумерацією записів та історією;
- `make_fault_injector(n, error)` — перші n викликів кидають тимчасову помилку;
- `make_backoff(delay, backoff, jitter, rng)` — політика затримок між спробами.

**`decorators.py`** — параметризовані декоратори з `@functools.wraps`, `ParamSpec`/`TypeVar`
(синтаксис Python 3.12: `def retries[**P, R](...)`):
- `@timed(label, unit, logger, clock)` — час виконання, лог у `finally`;
- `@retries(attempts, exceptions, give_up_on, delay, backoff, jitter, sleep, logger, rng)` —
  повтори з експоненційним backoff; постійні помилки (`give_up_on`) не повторюються;
- `@cached(ttl, time_fn)` — кеш з TTL, `cache_clear()`, `cache_invalidate(pred)`, `cache_info()`;
- `@call_stats(clock)` — статистика: виклики, успіхи, помилки, сумарний час, остання помилка;
  `stats()` / `reset_stats()`.

**`fileops.py`** (варіант 6):
- `Storage` (Protocol), `MemoryStorage` (словник, для тестів), `DiskStorage` (справжні файли);
- `FlakyStorage` — обгортка, що перші N читань/записів падають з `TimeoutError`;
- `make_file_service(storage, ...)` — збирає операції read/write з декораторів:

```
спроба ─► @call_stats (спроби) ─► @retries ─► @timed ─► @call_stats (операції)
```
Тимчасові `OSError` (`TimeoutError`, `PermissionError`, ...) повторюються,
`FileNotFoundError` / `IsADirectoryError` — ні.

**`app.py`** — демонстрація на справжніх файлах у тимчасовому каталозі.

## Тести
`sleep`, `clock`, `logger`, `rng`, `time_fn` і сховище передаються як залежності —
тести не чекають і не чіпають диск. Перевіряється: стан замикань, `__name__`/`__doc__`/
`__wrapped__` після декорування, лог навіть на винятку, кількість спроб і паузи
backoff/jitter, межа TTL, інвалідація кешу, статистика, повтори файлових операцій.

## Запуск
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

pytest -q
python main.py
mypy .
black --check .
ruff check .
```
Потрібен Python 3.12+.
