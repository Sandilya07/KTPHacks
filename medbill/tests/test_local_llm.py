import io
import json
from urllib.error import URLError

import pytest

import llm
from api import service
from api.settings import Settings
from extraction.cached import CachedExtractor
from extraction.textlayer import TextLayerExtractor
from llm import OllamaLLM


def test_local_provider_does_not_require_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(llm.llm_from_env(), OllamaLLM)


def test_local_generation_uses_json_schema_and_no_authorization(monkeypatch):
    def send(request, timeout):
        payload = json.loads(request.data)
        assert request.full_url == "http://127.0.0.1:11434/api/chat"
        assert payload["format"]["required"] == ["language"]
        assert payload["think"] is False and payload["stream"] is False
        assert request.get_header("Authorization") is None
        return io.BytesIO(json.dumps({"message": {"content": '{"language":"es"}'}, "done_reason": "stop"}).encode())
    monkeypatch.setattr(llm, "urlopen", send)
    result = OllamaLLM().complete_tool("Detect", "Hola", {"name": "detect_language", "input_schema": {
        "type": "object", "required": ["language"], "properties": {"language": {"type": "string"}}}})
    assert result == {"language": "es"}


def test_local_connection_failure_is_actionable(monkeypatch):
    def unavailable(*args, **kwargs):
        raise URLError("not listening")
    monkeypatch.setattr(llm, "urlopen", unavailable)
    with pytest.raises(RuntimeError, match="Start Ollama"):
        OllamaLLM().complete_tool("Test", "input", {"name": "test", "input_schema": {"type": "object"}})


def test_local_text_model_does_not_start_hosted_image_extraction():
    extractor, label = service.pick_extractor(None, OllamaLLM(), None, Settings())
    assert isinstance(extractor, TextLayerExtractor) and label == "text-layer"


def test_local_samples_use_cached_extraction_and_deterministic_wording():
    model = OllamaLLM()
    extractor, _ = service.pick_extractor(None, model, "overcharge", Settings())
    assert isinstance(extractor, CachedExtractor)
    assert service.wording_model(model, Settings()) is None


def test_cloud_model_name_is_rejected():
    with pytest.raises(ValueError, match="local Ollama"):
        OllamaLLM(model="some-model:cloud")


def stream_response(parts, *, done=True, reason="stop"):
    events = [{"message": {"content": part}, "done": False} for part in parts]
    if done:
        events.append({"message": {"content": ""}, "done": True, "done_reason": reason})
    return io.BytesIO(("\n".join(json.dumps(event) for event in events) + "\n").encode())


def test_translation_stream_is_assembled_before_returning_structured_json(monkeypatch):
    from i18n.translate import TRANSLATE_TOOL
    expected = {"translation": 'Le mot "test" est ici. नमस्ते'}
    encoded = json.dumps(expected, ensure_ascii=True)
    def send(request, timeout):
        assert json.loads(request.data)["stream"] is True
        # Split inside escape sequences as well as ordinary tokens.
        return stream_response(list(encoded))
    monkeypatch.setattr(llm, "urlopen", send)
    assert OllamaLLM().complete_tool("Translate", "Hello", TRANSLATE_TOOL) == expected


def test_looping_translation_is_cancelled_before_reading_more_tokens(monkeypatch):
    from i18n.translate import TRANSLATE_TOOL
    class LoopResponse(io.BytesIO):
        def __next__(self):
            if self.tell():
                pytest.fail("The connection should close as soon as the invalid loop is detected")
            return super().__next__()
    event = {"message": {"content": '{"translation":"again again again again '}, "done": False}
    response = LoopResponse((json.dumps(event) + "\n").encode())
    monkeypatch.setattr(llm, "urlopen", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="repeated itself"):
        OllamaLLM().complete_tool("Translate", "Hello", TRANSLATE_TOOL)
    assert response.closed


def test_repeated_placeholders_in_separate_values_do_not_cancel_translation(monkeypatch):
    expected = {"segments": {f"s{i}": "Code [[CODE_1]]" for i in range(5)}}
    monkeypatch.setattr(llm, "urlopen", lambda *args, **kwargs: stream_response([json.dumps(expected)]))
    assert OllamaLLM().complete_tool("Translate", "codes", {"name": "translate_spans", "input_schema": {"type": "object"}}) == expected


@pytest.mark.parametrize("done,reason", [(False, "stop"), (True, "length")])
def test_incomplete_or_token_limited_streams_are_never_accepted(monkeypatch, done, reason):
    from i18n.translate import TRANSLATE_TOOL
    monkeypatch.setattr(llm, "urlopen", lambda *args, **kwargs: stream_response(['{"translation":"Bonjour"}'], done=done, reason=reason))
    with pytest.raises(RuntimeError):
        OllamaLLM().complete_tool("Translate", "Hello", TRANSLATE_TOOL)


def test_cancelled_translation_retries_with_feedback_and_normal_validation(monkeypatch):
    from i18n.translate import Translator
    requests = []
    def send(request, timeout):
        payload = json.loads(request.data)
        requests.append(payload)
        if len(requests) == 1:
            return stream_response(['{"segments":{"s0":"again again again again '])
        assert "previous output was rejected" in payload["messages"][0]["content"]
        return stream_response(['{"segments":{"s0":"Revise este cargo."}}'])
    monkeypatch.setattr(llm, "urlopen", send)
    result = Translator(OllamaLLM()).translate("Review this charge.", "es")
    assert result.verified and result.attempts == 2 and result.text == "Revise este cargo."
    assert len(requests) == 2


@pytest.mark.parametrize("question,intent,codes,expected", [
    ("Can you tell me what this lab code is?", "code_meaning", ["80053"], "blood test"),
    ("Who sent this bill?", "provider", [], "Synthetic Family Clinic"),
    ("Go through every item for me", "all_charges", [], "99214"),
])
def test_small_model_interprets_questions_but_python_supplies_facts(question, intent, codes, expected):
    from i18n.qa import QA
    from i18n.translate import Translator
    from tests.helpers import overcharge_case
    class LocalRouter:
        provider = "ollama"
        def complete_tool(self, system, user, tool):
            assert tool["name"] == "understand_bill_question"
            return {"intent": intent, "codes": codes, "term": ""}
    result = QA(Translator(None), LocalRouter()).ask(overcharge_case(), question, "en")
    assert not result.deferred and expected in result.answer and result.citations


def test_small_model_does_not_replace_unknown_code_with_one_from_history():
    from i18n.qa import QA
    from i18n.translate import Translator
    from tests.helpers import overcharge_case
    class LocalRouter:
        provider = "ollama"
        def complete_tool(self, system, user, tool):
            return {"intent": "code_meaning", "codes": ["80053"], "term": ""}
    result = QA(Translator(None), LocalRouter()).ask(overcharge_case(), "What was 99123?", "en")
    assert result.deferred


def test_explicit_billing_code_is_not_lost_to_general_glossary_intent():
    from i18n.qa import QA
    from i18n.translate import Translator
    from tests.helpers import overcharge_case
    class LocalRouter:
        provider = "ollama"
        def complete_tool(self, system, user, tool):
            return {"intent": "what_is_eob", "codes": [], "term": "EOB"}
    result = QA(Translator(None), LocalRouter()).ask(overcharge_case(), "What does code 80053 mean?", "en")
    assert result.kind == "code_meaning" and "blood test" in result.answer and result.citations
