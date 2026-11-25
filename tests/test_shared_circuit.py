"""Estado del circuit breaker compartido entre procesos (simula workers de gunicorn)."""
import multiprocessing as mp

from app.fallback import CircuitBreaker, CircuitState, SQLiteBackend


def _worker_failures(path, n):
    b = CircuitBreaker("p", fail_max=10_000, backend=SQLiteBackend(path))
    for _ in range(n):
        b.record_failure()


def _worker_one_failure(path):
    CircuitBreaker("openai", fail_max=4, backend=SQLiteBackend(path)).record_failure()


def test_no_lost_updates_across_4_workers(tmp_path):
    path = str(tmp_path / "c.sqlite3")
    SQLiteBackend(path)
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_worker_failures, args=(path, 25)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    assert CircuitBreaker("p", fail_max=10_000, backend=SQLiteBackend(path)).failure_count() == 100


def test_circuit_opened_by_other_workers_is_seen(tmp_path):
    path = str(tmp_path / "c.sqlite3")
    observer = CircuitBreaker("openai", fail_max=4, reset_timeout=30, backend=SQLiteBackend(path))
    assert observer.allow_request()
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=_worker_one_failure, args=(path,)) for _ in range(4)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    assert observer.state == CircuitState.OPEN
    assert not observer.allow_request()


def test_half_open_recovery_shared(tmp_path):
    path = str(tmp_path / "c.sqlite3")
    a = CircuitBreaker("x", fail_max=1, reset_timeout=0.0, success_threshold=2, backend=SQLiteBackend(path))
    b = CircuitBreaker("x", fail_max=1, reset_timeout=0.0, success_threshold=2, backend=SQLiteBackend(path))
    a.record_failure()
    assert b.state == CircuitState.HALF_OPEN
    a.record_success()
    b.record_success()
    assert a.state == CircuitState.CLOSED
