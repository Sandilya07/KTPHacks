from i18n.interface import translate_interface
from i18n.translate import Translator
from tests.test_translate import FnLLM
import json
import pytest


def test_large_interface_is_translated_in_bounded_batches():
    def translate(system, user, tool, n):
        values = json.loads(user)
        assert len(values) <= 10
        return {"strings": {key: "FR " + value for key, value in values.items()}}
    model = FnLLM(translate)
    source = {f"label{i}": "Bill {amount}" for i in range(25)}
    result = translate_interface(source, Translator(model), "fr")
    assert set(result) == set(source) and len(model.calls) == 3
    assert all("{amount}" in value for value in result.values())


def test_changed_interface_variable_retries_then_rejects():
    model = FnLLM(lambda s, u, t, n: {"strings": {"total": "Montant {wrong}"}})
    with pytest.raises(ValueError, match="variables"):
        translate_interface({"total": "Total {amount}"}, Translator(model), "fr")
    assert len(model.calls) == 2
