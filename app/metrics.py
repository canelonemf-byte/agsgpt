"""Métricas Prometheus — definición única."""
from prometheus_client import Counter, Gauge, Histogram

CIRCUIT_STATE = Gauge(
    "agent_circuit_state",
    "Circuit breaker state (0=closed, 1=open, 2=half-open)",
    ["provider"],
)

CIRCUIT_STATE_CHANGES = Counter(
    "agent_circuit_state_changes_total",
    "Circuit breaker state transitions",
    ["provider", "from_state", "to_state"],
)

FALLBACK_USED = Counter(
    "agent_fallback_used_total",
    "Fallback events by model",
    ["model"],
)

RETRY_TOTAL = Counter(
    "agent_retries_total",
    "Retries by model and error type",
    ["model", "error_type"],
)

LLM_CALL_DURATION = Histogram(
    "agent_llm_call_duration_seconds",
    "LLM call duration",
    ["model", "status"],
    buckets=[0.5, 1, 2.5, 5, 10, 20, 30, 60],
)
