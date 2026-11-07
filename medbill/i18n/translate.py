"""4B/4D. Translation through the number-integrity layer.

English text -> placeholders -> model -> verify tokens + glossary -> restore -> back-translate to English
-> compare the multiset of numbers and codes. A mismatch retries once, then the English text is shown with
a notice. Numbers are never trusted to the model."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from llm import LLMClient

from .glossary import Glossary, load_glossary
from .placeholders import protect, restore, same_values, verify_tokens

log = logging.getLogger(__name__)

TRANSLATE_TOOL = {"name": "translate", "description": "Return the translation.",
                  "input_schema": {"type": "object", "required": ["translation"],
                                   "properties": {"translation": {"type": "string"}}}}
ENGLISH_TOOL = {"name": "to_english", "description": "Return the English translation.",
                "input_schema": {"type": "object", "required": ["english"],
                                 "properties": {"english": {"type": "string"}}}}
RULES = (
    "Placeholders such as [[AMT_1]], [[CODE_2]], [[DATE_1]], [[ACCT_1]], [[PCT_1]] and [[LINE_1]] stand for "
    "amounts, codes, dates, account numbers, percentages and line ids. Copy every placeholder EXACTLY as written, "
    "exactly once, never translate, reformat or remove one, and never write any number or digit yourself. "
    "Do not add, remove or soften any fact. Use short, plain sentences."
)


@dataclass
class Translation:
    text: str
    lang: str
    verified: bool
    notice: str = ""
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    glossary_warnings: list[str] = field(default_factory=list)
    source: str = "llm"  # "llm", "cache", "english"


class Translator:
    """`cache` maps language -> {masked English text: masked translation}. It lets demo mode work offline
    and, because it is keyed on the masked text, reuses a human-written translation for any numbers."""

    def __init__(self, llm: LLMClient | None = None, cache: dict[str, dict[str, str]] | None = None,
                 max_retries: int = 1):
        self.llm, self.cache, self.max_retries = llm, cache or {}, max_retries

    # ---- English -> language -----------------------------------------------------------------
    def _fail(self, text: str, lang: str, g: Glossary | None, errors: list[str], attempts: int) -> Translation:
        notice = f"{g.phrases['translation_notice']} (Translation could not be verified; shown in English.)" if g else \
            "Translation could not be verified; shown in English."
        return Translation(text, lang, False, notice, attempts, errors, source="english")

    def translate(self, text: str, lang: str) -> Translation:
        if lang == "en":
            return Translation(text, "en", True, source="english")
        g = load_glossary(lang)
        p = protect(text)
        cached = self.cache.get(lang, {}).get(p.masked)
        if cached is not None and not verify_tokens(p.masked, cached, p.mapping):
            return Translation(restore(cached, p.mapping), lang, True, source="cache",
                               glossary_warnings=g.check(text, cached))
        if self.llm is None:
            return self._fail(text, lang, g, ["no translation model available"], 0)
        errors: list[str] = []
        feedback = ""
        for attempt in range(1, self.max_retries + 2):
            system = f"Translate the user's text from English to {g.name} ({lang}). {RULES}\nGlossary:\n{g.prompt_block(text)}"
            try:
                out = str(self.llm.complete_tool(system, p.masked + feedback, TRANSLATE_TOOL).get("translation", ""))
            except Exception as exc:  # noqa: BLE001 - never crash the app on a model failure
                errors.append(f"model error: {exc}")
                break
            errs = verify_tokens(p.masked, out, p.mapping)
            gloss = g.check(text, out)
            if errs:
                errors += errs
                feedback = "\n\nYour previous translation was rejected: " + "; ".join(errs) + ". Keep placeholders exact."
                continue
            if gloss and attempt <= self.max_retries:
                feedback = "\n\nUse the glossary terms exactly: " + "; ".join(gloss)
                continue
            restored = restore(out, p.mapping)
            back_errs = self._back_check(text, restored, lang, g)
            if back_errs:
                errors += back_errs
                feedback = "\n\nThe back-translation changed numbers or codes. Keep every placeholder exact."
                continue
            return Translation(restored, lang, True, attempts=attempt, errors=errors, glossary_warnings=gloss)
        log.warning("translation to %s failed verification: %s", lang, errors)
        return self._fail(text, lang, g, errors, attempt if "attempt" in dir() else 0)

    def _back_check(self, original: str, restored: str, lang: str, g: Glossary) -> list[str]:
        """Translate back to English with the same placeholder rules and compare numbers and codes."""
        p2 = protect(restored)
        try:
            back = str(self.llm.complete_tool(
                f"Translate the user's {g.name} text into English. {RULES}", p2.masked, ENGLISH_TOOL).get("english", ""))
        except Exception as exc:  # noqa: BLE001
            return [f"back-translation failed: {exc}"]
        errs = verify_tokens(p2.masked, back, p2.mapping)
        if errs:
            return ["back-translation: " + e for e in errs]
        if not same_values(original, restore(back, p2.mapping)):
            return ["back-translation: numbers or codes differ from the original"]
        return []

    def translate_parts(self, parts: list[str], lang: str) -> Translation:
        """Translate sentence by sentence and join. All or nothing: if any sentence cannot be verified the
        whole text is shown in English, so a paragraph is never half in one language."""
        english = " ".join(parts)
        if lang == "en":
            return Translation(english, "en", True, source="english")
        done = [self.translate(p, lang) for p in parts]
        if all(t.verified for t in done):
            text = " ".join(t.text for t in done)
            if same_values(english, text):
                src = "cache" if all(t.source == "cache" for t in done) else "llm"
                return Translation(text, lang, True, attempts=max(t.attempts for t in done), source=src,
                                   glossary_warnings=[w for t in done for w in t.glossary_warnings])
        bad = next((t for t in done if not t.verified), None)
        g = load_glossary(lang)
        return self._fail(english, lang, g, bad.errors if bad else ["numbers differ after joining"], 0)

    # ---- language -> English (questions) ----------------------------------------------------
    def to_english(self, text: str, lang: str) -> str | None:
        if lang == "en":
            return text
        if self.llm is None:
            return None
        p = protect(text)
        try:
            out = str(self.llm.complete_tool(
                f"Translate the user's question into English. {RULES}", p.masked, ENGLISH_TOOL).get("english", ""))
        except Exception as exc:  # noqa: BLE001
            log.warning("question translation failed: %s", exc)
            return None
        if verify_tokens(p.masked, out, p.mapping):
            return None
        return restore(out, p.mapping)
