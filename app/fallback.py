"""Fallback chain con circuit breaker (closed / open / half-open)."""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

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


class CircuitBreaker:
    def __init__(self, provider: str, fail_max: int = 5,
                 reset_timeout: float = 30.0, success_threshold: int = 3):
        self.provider = provider
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold
        self._failures: list[float] = []
        self._successes: int = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float | None = None
        CIRCUIT_STATE.labels(provider=provider).set(0)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.time() - (self._opened_at or 0) >= self.reset_timeout:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    def allow_request(self) -> bool:
        return self.state != CircuitState.OPEN

    def record_success(self):
        prev = self.state
        if prev == CircuitState.HALF_OPEN:
            self._successes += 1
            if self._successes >= self.success_threshold:
                self._transition(CircuitState.CLOSED)
        elif prev == CircuitState.CLOSED:
            self._successes = 0

    def record_failure(self):
        prev = self.state
        now = time.time()
        self._failures = [t for t in self._failures if now - t < 30]
        self._failures.append(now)
        if prev == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif len(self._failures) >= self.fail_max:
            self._transition(CircuitState.OPEN)

    def _transition(self, new: CircuitState):
        old = self._state
        self._state = new
        if new == CircuitState.OPEN:
            self._opened_at = time.time()
            self._successes = 0
        elif new == CircuitState.CLOSED:
            self._failures.clear()
            self._successes = 0
        CIRCUIT_STATE.labels(provider=self.provider).set(
            {"closed": 0, "open": 1, "half-open": 2}[new.value]
        )
        CIRCUIT_STATE_CHANGES.labels(
            provider=self.provider, from_state=old.value, to_state=new.value
        ).inc()
        log_fn = logger.critical if new == CircuitState.OPEN else logger.info
        log_fn("Circuit [%s] %s → %s", self.provider, old.value, new.value)


class FallbackChain:
    def __init__(self, models: list[ModelConfig], breakers: dict[str, CircuitBreaker]):
        self.models = models
        self.breakers = breakers

    def call(self, messages: list[dict], **kwargs) -> dict[str, Any]:
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
        status = getattr(e, "status_code", None) or getattr(e, "status", None)
        msg = str(e).lower()
        if status in (401, 402, 403):
            return ErrorType.PERMANENT
        if status == 429 and any(w in msg for w in ("quota", "spend", "billing")):
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
