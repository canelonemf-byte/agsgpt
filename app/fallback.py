"""Fallback chain con circuit breaker (closed / open / half-open).

El estado del breaker vive en un backend: en memoria (un proceso) o en SQLite
(compartido entre workers de gunicorn, sin dependencias externas). Cada cambio
se hace en una transacción BEGIN IMMEDIATE, así que no se pierden fallos.
"""
from __future__ import annotations

import json
import logging
import random
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Iterator

from .metrics import CIRCUIT_STATE, CIRCUIT_STATE_CHANGES, RETRY_TOTAL, LLM_CALL_DURATION

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    DEGRADED = "degraded"


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"


@dataclass
class ModelConfig:
    name: str
    provider: str
    call_fn: Callable[..., str]
    max_retries: int = 2
    base_delay: float = 1.0
    timeout: float = 30.0


def _default_state() -> dict:
    return {"state": "closed", "opened_at": 0.0, "successes": 0, "failures": []}


class MemoryBackend:
    """Estado en memoria: válido para un solo proceso (tests, uvicorn sin workers)."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.RLock()

    @contextmanager
    def transaction(self, provider: str) -> Iterator[dict]:
        with self._lock:
            st = json.loads(json.dumps(self._data.get(provider, _default_state())))
            yield st
            self._data[provider] = st


class SQLiteBackend:
    """Estado compartido entre procesos en un fichero SQLite (stdlib)."""

    def __init__(self, path: str, timeout: float = 10.0) -> None:
        self.path = path
        self.timeout = timeout
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("CREATE TABLE IF NOT EXISTS circuit (provider TEXT PRIMARY KEY, data TEXT NOT NULL)")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)

    @contextmanager
    def transaction(self, provider: str) -> Iterator[dict]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT data FROM circuit WHERE provider = ?", (provider,)).fetchone()
            st = json.loads(row[0]) if row else _default_state()
            yield st
            conn.execute(
                "INSERT INTO circuit (provider, data) VALUES (?, ?) "
                "ON CONFLICT(provider) DO UPDATE SET data = excluded.data",
                (provider, json.dumps(st)),
            )
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()


class CircuitBreaker:
    def __init__(self, provider: str, fail_max: int = 5,
                 reset_timeout: float = 30.0, success_threshold: int = 3,
                 backend: MemoryBackend | SQLiteBackend | None = None,
                 failure_window: float = 30.0):
        self.provider = provider
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold
        self.failure_window = failure_window
        self.backend = backend or MemoryBackend()
        with self.backend.transaction(provider) as st:
            current = st["state"]
        CIRCUIT_STATE.labels(provider=provider).set({"closed": 0, "open": 1, "half-open": 2}[current])

    def _maybe_half_open(self, st: dict, events: list) -> None:
        if st["state"] == CircuitState.OPEN.value and time.time() - st["opened_at"] >= self.reset_timeout:
            self._set(st, CircuitState.HALF_OPEN, events)

    def _set(self, st: dict, new: CircuitState, events: list) -> None:
        old = st["state"]
        st["state"] = new.value
        if new == CircuitState.OPEN:
            st["opened_at"] = time.time()
            st["successes"] = 0
        elif new == CircuitState.CLOSED:
            st["failures"] = []
            st["successes"] = 0
        events.append((old, new.value))

    def _emit(self, events: list) -> None:
        for old, new in events:
            CIRCUIT_STATE.labels(provider=self.provider).set({"closed": 0, "open": 1, "half-open": 2}[new])
            CIRCUIT_STATE_CHANGES.labels(provider=self.provider, from_state=old, to_state=new).inc()
            log_fn = logger.critical if new == CircuitState.OPEN.value else logger.info
            log_fn("Circuit [%s] %s → %s", self.provider, old, new)

    @property
    def state(self) -> CircuitState:
        events: list = []
        with self.backend.transaction(self.provider) as st:
            self._maybe_half_open(st, events)
            current = st["state"]
        self._emit(events)
        return CircuitState(current)

    def failure_count(self) -> int:
        with self.backend.transaction(self.provider) as st:
            return len(st["failures"])

    def allow_request(self) -> bool:
        return self.state != CircuitState.OPEN

    def record_success(self):
        events: list = []
        with self.backend.transaction(self.provider) as st:
            self._maybe_half_open(st, events)
            if st["state"] == CircuitState.HALF_OPEN.value:
                st["successes"] += 1
                if st["successes"] >= self.success_threshold:
                    self._set(st, CircuitState.CLOSED, events)
            elif st["state"] == CircuitState.CLOSED.value:
                st["successes"] = 0
        self._emit(events)

    def record_failure(self):
        events: list = []
        with self.backend.transaction(self.provider) as st:
            self._maybe_half_open(st, events)
            now = time.time()
            st["failures"] = [t for t in st["failures"] if now - t < self.failure_window] + [now]
            if st["state"] == CircuitState.HALF_OPEN.value:
                self._set(st, CircuitState.OPEN, events)
            elif st["state"] == CircuitState.CLOSED.value and len(st["failures"]) >= self.fail_max:
                self._set(st, CircuitState.OPEN, events)
        self._emit(events)


class FallbackChain:
    def __init__(self, models: list[ModelConfig], breakers: dict[str, CircuitBreaker]):
        self.models = models
        self.breakers = breakers

    def call(self, messages: list[dict], **kwargs) -> dict[str, Any]:
        if not messages:
            raise ValueError("messages no puede estar vacío")
        last_error: Exception | None = None

        for model in self.models:
            breaker = self.breakers.get(model.provider)
            if breaker and not breaker.allow_request():
                logger.info("Skipping %s (circuit %s open)", model.name, model.provider)
                continue

            tries = 0             # llamadas totales a este modelo
            failed_transient = 0  # fallos transitorios que consumen reintentos
            truncated = False     # el truncado de contexto solo se reintenta una vez

            while True:
                tries += 1
                t0 = time.monotonic()
                try:
                    result = model.call_fn(messages, **{"timeout": model.timeout, **kwargs})
                    LLM_CALL_DURATION.labels(model=model.name, status="ok").observe(
                        time.monotonic() - t0
                    )
                    if breaker:
                        breaker.record_success()
                    return {
                        "content": result,
                        "model": model.name,
                        "is_fallback": model.name != self.models[0].name,
                        "attempts": tries,
                    }
                except Exception as e:
                    err_type = self._classify(e)
                    LLM_CALL_DURATION.labels(model=model.name, status=err_type.value).observe(
                        time.monotonic() - t0
                    )
                    last_error = e

                    if err_type == ErrorType.DEGRADED:
                        # Contexto excedido: no es un fallo del proveedor, no abre el circuito.
                        if truncated:
                            break
                        messages = self._truncate(messages)
                        truncated = True
                        RETRY_TOTAL.labels(model=model.name, error_type=err_type.value).inc()
                        continue

                    if breaker:
                        breaker.record_failure()
                    if err_type == ErrorType.PERMANENT:
                        break

                    failed_transient += 1
                    if failed_transient > model.max_retries:
                        break
                    RETRY_TOTAL.labels(model=model.name, error_type=err_type.value).inc()
                    time.sleep(model.base_delay * (2 ** (failed_transient - 1)) + random.uniform(0, 0.5))

        raise RuntimeError(
            f"All {len(self.models)} models failed. Last: {last_error}"
        ) from last_error

    @staticmethod
    def _classify(e: Exception) -> ErrorType:
        if isinstance(e, (KeyError, ValueError)):
            return ErrorType.PERMANENT  # p. ej. falta OPENAI_API_KEY: reintentar no sirve
        status = getattr(e, "status_code", None) or getattr(e, "status", None)
        msg = str(e).lower()
        if status in (401, 402, 403):
            return ErrorType.PERMANENT
        if status == 429 and any(w in msg for w in ("quota", "spend", "billing")):
            return ErrorType.PERMANENT
        if any(w in msg for w in ("authentication", "invalid_api_key", "api_key")):
            return ErrorType.PERMANENT
        if status in (408, 429, 500, 502, 503, 529):
            return ErrorType.TRANSIENT
        if "context_length" in msg or "maximum context" in msg:
            return ErrorType.DEGRADED
        return ErrorType.TRANSIENT

    @staticmethod
    def _truncate(messages: list[dict]) -> list[dict]:
        if len(messages) <= 2:
            return messages
        rest = messages[1:]
        keep = max(1, int(len(rest) * 0.3))
        return [messages[0]] + rest[-keep:]
