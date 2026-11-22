"""Agente que consume la FallbackChain."""
from __future__ import annotations

import logging
from typing import Any

from .fallback import FallbackChain
from .metrics import FALLBACK_USED

logger = logging.getLogger(__name__)


class Agent:
    def __init__(self, chain: FallbackChain, name: str = "default"):
        self.chain = chain
        self.name = name

    def run(self, messages: list[dict], **kwargs) -> dict[str, Any]:
        result = self.chain.call(messages, **kwargs)
        if result["is_fallback"]:
            FALLBACK_USED.labels(model=result["model"]).inc()
            logger.warning("[%s] Fallback → %s", self.name, result["model"])
        return result
