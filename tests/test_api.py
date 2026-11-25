from fastapi.testclient import TestClient
import pytest

from app import main
from app.fallback import FallbackChain, ModelConfig


def test_health_ok():
    client = TestClient(main.app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_metrics_exposed():
    client = TestClient(main.app)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "agent_circuit_state" in r.text


def test_chat_empty_messages_returns_422():
    client = TestClient(main.app)
    r = client.post("/chat", json={"messages": []})
    assert r.status_code == 422


def test_chat_success_and_fallback(monkeypatch):
    class FakeAgent:
        def run(self, messages):
            return {
                "content": "hola de vuelta",
                "model": "claude-sonnet",
                "is_fallback": True,
                "attempts": 1,
            }

    monkeypatch.setattr(main, "get_agent", lambda name="default": FakeAgent())
    client = TestClient(main.app)
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["content"] == "hola de vuelta"
    assert body["is_fallback"] is True


def test_chat_all_fail_returns_503(monkeypatch):
    class FailingAgent:
        def run(self, messages):
            raise RuntimeError("All 3 models failed")

    monkeypatch.setattr(main, "get_agent", lambda name="default": FailingAgent())
    client = TestClient(main.app)
    r = client.post("/chat", json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 503


def test_missing_api_key_keyerror_is_permanent_no_retry():
    calls = []

    def missing_key(messages, **kw):
        calls.append(1)
        raise KeyError("OPENAI_API_KEY")

    chain = FallbackChain(
        models=[ModelConfig("gpt-4o", "openai", missing_key, max_retries=3, base_delay=0.0)],
        breakers={},
    )
    with pytest.raises(RuntimeError):
        chain.call([{"role": "user", "content": "hola"}])
    assert len(calls) == 1
