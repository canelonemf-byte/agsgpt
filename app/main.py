"""FastAPI app — endpoint /chat + /health + /metrics."""
from __future__ import annotations

import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

from .wiring import get_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="agsgpt", version="1.0.0")

Instrumentator(
    excluded_handlers=["/metrics", "/health"],
    should_instrument_requests_inprogress=True,
).instrument(app).expose(app, endpoint="/metrics")


class ChatRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1)
    agent: str = "default"


class ChatResponse(BaseModel):
    content: str
    model: str
    is_fallback: bool
    attempts: int


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        result = get_agent(req.agent).run(req.messages)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return ChatResponse(**result)
