import pytest

from decorators import cached


def test_cached_ttl_and_invalidate() -> None:
    t = [1000.0]
    hit = {"n": 0}

    @cached(ttl=1.0, time_fn=lambda: t[0])
    def f(x: int) -> int:
        hit["n"] += 1
        return x * 2

    assert f(10) == 20
    assert f(10) == 20
    assert hit["n"] == 1
    t[0] += 2.0  # TTL минув
    assert f(10) == 20
    assert hit["n"] == 2
    assert f.cache_invalidate(lambda a, kw: a == (10,)) == 1
    assert f(10) == 20
    assert hit["n"] == 3


def test_ttl_boundary() -> None:
    t = [0.0]

    @cached(ttl=5.0, time_fn=lambda: t[0])
    def g(x: int) -> int:
        return x

    g(1)
    t[0] = 4.999
    g(1)
    t[0] = 5.0  # рівно ttl — уже протухло
    g(1)
    assert g.cache_info() == {"hits": 1, "misses": 2, "size": 1}


def test_kwargs_in_key_and_clear() -> None:
    @cached()
    def h(a: int, *, scale: int = 1) -> int:
        return a * scale

    h(2, scale=3)
    h(2, scale=3)
    h(2, scale=4)
    assert h.cache_info() == {"hits": 1, "misses": 2, "size": 2}
    assert h.cache_invalidate(lambda a, kw: kw.get("scale") == 4) == 1
    h.cache_clear()
    assert h.cache_info() == {"hits": 0, "misses": 0, "size": 0}


def test_unhashable_args_and_bad_ttl() -> None:
    @cached()
    def total(xs: list[int]) -> int:
        return sum(xs)

    with pytest.raises(TypeError):
        total([1, 2])
    with pytest.raises(ValueError):
        cached(ttl=0)


def test_metadata() -> None:
    @cached()
    def price(product_id: int) -> float:
        """Ціна товару."""
        return 1.0

    assert price.__name__ == "price" and price.__doc__ == "Ціна товару."
    assert price.__wrapped__(1) == 1.0
