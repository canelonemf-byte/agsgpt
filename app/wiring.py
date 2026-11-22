"""Composición: breakers + chain + agentes."""
from __future__ import annotations

from .agent import Agent
from .fallback import FallbackChain, ModelConfig, CircuitBreaker
from .llm.clients import call_gpt4o, call_gpt4o_mini, call_claude_sonnet

_openai_breaker = CircuitBreaker(provider="openai", fail_max=5, reset_timeout=30)
_anthropic_breaker = CircuitBreaker(provider="anthropic", fail_max=5, reset_timeout=30)

_chain = FallbackChain(
    models=[
        ModelConfig("gpt-4o", "openai", call_gpt4o, max_retries=2, timeout=30),
        ModelConfig("claude-sonnet", "anthropic", call_claude_sonnet, max_retries=2, timeout=30),
        ModelConfig("gpt-4o-mini", "openai", call_gpt4o_mini, max_retries=1, timeout=15),
    ],
    breakers={
        "openai": _openai_breaker,
        "anthropic": _anthropic_breaker,
    },
)


def get_agent(name: str = "default") -> Agent:
    return Agent(_chain, name=name)
