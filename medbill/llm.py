"""Shared LLM client interface. The LLM only (a) extracts, (b) explains, (c) translates; it never
decides whether something is an error. Tests and offline runs use fakes; live runs use Anthropic.

`complete_tool(system, user, tool)` forces a structured answer through tool use and returns the
tool input dict. The model name comes from the MODEL environment variable."""
from __future__ import annotations

import os
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Protocol

DEFAULT_MODEL = "claude-sonnet-5-5"


def tool_call_options(model: str, tool_name: str) -> dict:
    if model == "claude-sonnet-5-5":
        # Sonnet 5.5 rejects forced tool choice; avoid spending the small response budget on up-front thinking.
        return {"tool_choice": {"type": "auto"}, "thinking": {"type": "between_tools"},
                "output_config": {"effort": "medium"}}
    return {"tool_choice": {"type": "tool", "name": tool_name}}


class LLMClient(Protocol):
    def complete_tool(self, system: str, user: str, tool: dict) -> dict: ...


class AnthropicLLM:
    provider = "anthropic"
    def __init__(self, client=None, model: str | None = None, max_tokens: int = 2000):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
        self.client, self.max_tokens = client, max_tokens
        self.model = model or os.environ.get("MODEL", DEFAULT_MODEL)

    def complete_tool(self, system: str, user: str, tool: dict) -> dict:
        resp = self.client.messages.create(
            model=self.model, max_tokens=max(self.max_tokens, 12000) if tool["name"] == "translate_interface" else self.max_tokens,
            system=system + f"\nReturn the result by calling the {tool['name']} tool. Do not answer in plain text.",
            tools=[tool], **tool_call_options(self.model, tool["name"]),
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                return dict(block.input)
        raise RuntimeError("Model did not return the tool call")


class OllamaLLM:
    """Local structured JSON generation using the same interface as the hosted client."""

    provider = "ollama"

    def __init__(self, model: str | None = None, base_url: str | None = None, timeout: float = 180):
        self.model = model or os.environ.get("OLLAMA_MODEL", "qwen3:4b")
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.timeout = timeout
        if self.model.endswith(":cloud"):
            raise ValueError("Select a downloaded local Ollama model, not a cloud model.")

    def complete_tool(self, system: str, user: str, tool: dict) -> dict:
        budgets = {"detect_language": 64, "understand_bill_question": 160, "translate_interface": 1536,
                   "translate_spans": 1024, "to_english": 1024, "translate": 1024}
        watch_translation = tool["name"] in ("translate_spans", "translate")
        payload = {
            "model": self.model, "stream": watch_translation, "think": False, "keep_alive": "15m",
            "format": tool["input_schema"],
            "messages": [
                {"role": "system", "content": system + "\nReturn a JSON object only, matching this schema: "
                 + json.dumps(tool["input_schema"])},
                {"role": "user", "content": user},
            ],
            "options": {"temperature": 0, "repeat_penalty": 1.1, "num_ctx": 8192,
                        "num_predict": budgets.get(tool["name"], 1024)},
        }
        request = Request(self.base_url + "/api/chat", data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = self._read_translation(response) if watch_translation else json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError("Local AI is unavailable. Start Ollama and run: ollama pull " + self.model) from exc
        if result.get("done_reason") == "length":
            raise RuntimeError("The local model response was cut short. Try a shorter question.")
        content = json.loads(result.get("message", {}).get("content", ""))
        if not isinstance(content, dict):
            raise ValueError("Local model did not return a JSON object.")
        return content

    @staticmethod
    def _read_translation(response) -> dict:
        """Cancel a translation as soon as it enters a loop the validator would reject anyway.

        Streaming stays internal: callers receive only a complete JSON result for normal validation.
        """
        from i18n.languages import repetitive_output

        content = ""
        for line in response:
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("error"):
                raise RuntimeError("Local translation failed.")
            content += event.get("message", {}).get("content", "")
            # Inspect individual JSON strings, including the currently unfinished value.
            # Keys and repeated placeholders in separate values must not trigger the loop guard.
            for match in re.finditer(r'"((?:\\.|[^"\\])*)(?:"|$)', content):
                try:
                    value = json.loads('"' + match[1] + '"')
                except json.JSONDecodeError:
                    continue  # a token may end in the middle of an escape sequence
                if repetitive_output(value):
                    raise RuntimeError("Local translation repeated itself; retrying with corrective feedback.")
            if event.get("done"):
                event["message"] = {"content": content}
                return event
        raise RuntimeError("Local translation ended before it was complete.")


def llm_from_env() -> LLMClient | None:
    """Select local Ollama or the hosted provider. Ollama never requires an API key."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").strip().lower()
    if provider == "ollama":
        return OllamaLLM()
    if provider != "anthropic":
        raise ValueError("LLM_PROVIDER must be ollama or anthropic.")
    return AnthropicLLM() if os.environ.get("ANTHROPIC_API_KEY") else None
