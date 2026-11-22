import time
import pytest
from app.fallback import (
    FallbackChain, ModelConfig, CircuitBreaker, CircuitState,
)


def ok_fn(messages, **kw):
    return "respuesta ok"


def fail_503(messages, **kw):
    e = Exception("503 Service Unavailable")
    e.status_code = 503
    raise e


def fail_401(messages, **kw):
    e = Exception("401 Unauthorized")
    e.status_code = 401
    raise e


def msgs(n):
    return [{"role": "system", "content": "sys"}] + \
           [{"role": "user", "content": f"m{i}"} for i in range(n)]


def test_primary_succeeds():
    chain = FallbackChain(
        models=[ModelConfig("a", "p1", ok_fn, max_retries=0)], breakers={})
    r = chain.call([{"role": "user", "content": "hola"}])
    assert r["model"] == "a"
    assert r["is_fallback"] is False
    assert r["attempts"] == 1


def test_fallback_to_second():
    chain = FallbackChain(
        models=[
            ModelConfig("bad", "p1", fail_503, max_retries=0),
            ModelConfig("good", "p2", ok_fn, max_retries=0),
        ], breakers={})
    r = chain.call([{"role": "user", "content": "hola"}])
    assert r["model"] == "good"
    assert r["is_fallback"] is True


def test_all_fail_raises():
    chain = FallbackChain(
        models=[ModelConfig("a", "p1", fail_503, max_retries=0)], breakers={})
    with pytest.raises(RuntimeError, match="All 1 models failed"):
        chain.call([{"role": "user", "content": "hola"}])


def test_permanent_no_retry():
    calls = []

    def fn(messages, **kw):
        calls.append(1)
        return fail_401(messages, **kw)

    chain = FallbackChain(
        models=[ModelConfig("a", "p1", fn, max_retries=3)], breakers={})
    with pytest.raises(RuntimeError):
        chain.call([{"role": "user", "content": "hola"}])
    assert len(calls) == 1


def test_transient_uses_max_retries():
    calls = []

    def fn(messages, **kw):
        calls.append(1)
        return fail_503(messages, **kw)

    chain = FallbackChain(
        models=[ModelConfig("a", "p1", fn, max_retries=2, base_delay=0.0)], breakers={})
    with pytest.raises(RuntimeError):
        chain.call([{"role": "user", "content": "hola"}])
    assert len(calls) == 3


def test_degraded_truncates_and_retries_same_model():
    # Con 11 mensajes el truncado deja 4 (sistema + 3), que sí cabe.
    def fn(messages, **kw):
        if len(messages) > 4:
            raise Exception("maximum context length exceeded")
        return "ok truncated"

    chain = FallbackChain(
        models=[ModelConfig("a", "p1", fn, max_retries=0)], breakers={})
    r = chain.call(msgs(10))
    assert r["content"] == "ok truncated"
    assert r["model"] == "a"


def test_degraded_retries_only_once():
    calls = []

    def fn(messages, **kw):
        calls.append(1)
        raise Exception("maximum context length exceeded")

    chain = FallbackChain(
        models=[ModelConfig("a", "p1", fn, max_retries=0)], breakers={})
    with pytest.raises(RuntimeError):
        chain.call(msgs(10))
    assert len(calls) == 2


def test_degraded_does_not_open_circuit():
    def fn(messages, **kw):
        raise Exception("maximum context length exceeded")

    b = CircuitBreaker(provider="p1", fail_max=1, reset_timeout=30)
    chain = FallbackChain(
        models=[ModelConfig("a", "p1", fn, max_retries=0)], breakers={"p1": b})
    with pytest.raises(RuntimeError):
        chain.call(msgs(10))
    assert b.state == CircuitState.CLOSED


def test_timeout_is_passed_to_call_fn():
    seen = {}

    def fn(messages, **kw):
        seen.update(kw)
        return "ok"

    chain = FallbackChain(
        models=[ModelConfig("a", "p1", fn, max_retries=0, timeout=12.5)], breakers={})
    chain.call([{"role": "user", "content": "hola"}])
    assert seen["timeout"] == 12.5


def test_circuit_opens():
    b = CircuitBreaker(provider="t", fail_max=3, reset_timeout=30)
    for _ in range(3):
        b.record_failure()
    assert b.state == CircuitState.OPEN
    assert not b.allow_request()


def test_circuit_recovers():
    b = CircuitBreaker(provider="t", fail_max=2, reset_timeout=0.1, success_threshold=2)
    b.record_failure()
    b.record_failure()
    assert b.state == CircuitState.OPEN
    time.sleep(0.15)
    assert b.state == CircuitState.HALF_OPEN
    b.record_success()
    b.record_success()
    assert b.state == CircuitState.CLOSED


def test_circuit_reopens_on_half_open_failure():
    b = CircuitBreaker(provider="t", fail_max=2, reset_timeout=0.1, success_threshold=3)
    b.record_failure()
    b.record_failure()
    time.sleep(0.15)
    assert b.state == CircuitState.HALF_OPEN
    b.record_failure()
    assert b.state == CircuitState.OPEN
