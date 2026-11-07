"""Shared LLM client interface. The LLM only (a) extracts, (b) explains, (c) translates; it never
decides whether something is an error. Tests and offline runs use fakes; live runs use Anthropic.

`complete_tool(system, user, tool)` forces a structured answer through tool use and returns the
tool input dict. The model name comes from the MODEL environment variable."""
from __future__ import annotations

import os
from typing import Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"


class LLMClient(Protocol):
    def complete_tool(self, system: str, user: str, tool: dict) -> dict: ...


class AnthropicLLM:
    def __init__(self, client=None, model: str | None = None, max_tokens: int = 2000):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.client, self.max_tokens = client, max_tokens
        self.model = model or os.environ.get("MODEL", DEFAULT_MODEL)

    def complete_tool(self, system: str, user: str, tool: dict) -> dict:
        resp = self.client.messages.create(
            model=self.model, max_tokens=max(self.max_tokens, 12000) if tool["name"] == "translate_interface" else self.max_tokens,
            system=system, tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise RuntimeError("Model did not return the tool call")


def llm_from_env() -> LLMClient | None:
    """A live client when ANTHROPIC_API_KEY is set, otherwise None (callers use deterministic paths)."""
    return AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else None
