from types import SimpleNamespace

from extraction.llm import AnthropicExtractor
from llm import AnthropicLLM, tool_call_options


class FakeClient:
    def __init__(self):
        self.messages = self
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        assert kwargs["tool_choice"] == {"type": "auto"}
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input={"ok": True})])


def test_default_model_uses_supported_tool_request():
    client = FakeClient()
    llm = AnthropicLLM(client=client, model="claude-sonnet-5-5")
    assert llm.complete_tool("Test", "input", {"name": "test", "input_schema": {"type": "object"}}) == {"ok": True}
    assert client.request["thinking"] == {"type": "between_tools"}
    assert "calling the test tool" in client.request["system"]


def test_extraction_uses_supported_tool_request():
    client = FakeClient()
    assert AnthropicExtractor(client=client, model="claude-sonnet-5-5")._call("bill", []) == {"ok": True}


def test_older_models_retain_forced_tool_choice():
    assert tool_call_options("claude-sonnet-4-6", "test") == {"tool_choice": {"type": "tool", "name": "test"}}
