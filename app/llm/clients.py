"""Llamadas a LLM. Lazy init: no falla si no hay API key hasta la primera llamada."""
from __future__ import annotations
import os


def call_gpt4o(messages: list[dict], **kwargs) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        timeout=kwargs.get("timeout", 30),
    )
    return resp.choices[0].message.content


def call_gpt4o_mini(messages: list[dict], **kwargs) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        timeout=kwargs.get("timeout", 15),
    )
    return resp.choices[0].message.content


def call_claude_sonnet(messages: list[dict], **kwargs) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system = next((m["content"] for m in messages if m["role"] == "system"), None)
    msgs = [m for m in messages if m["role"] != "system"]
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=msgs,
        timeout=kwargs.get("timeout", 30),
    )
    return resp.content[0].text
