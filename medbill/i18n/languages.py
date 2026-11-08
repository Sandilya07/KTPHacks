"""Language metadata and offline checks; model languages are not restricted to the detector's catalog."""
from collections import Counter
from functools import lru_cache
import re
import unicodedata

from langcodes import Language, standardize_tag, tag_is_valid


def normalize_language(value: str) -> str:
    if not isinstance(value, str) or len(value) > 63 or not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value):
        raise ValueError("Invalid language code.")
    language = standardize_tag(value)
    if not tag_is_valid(language):
        raise ValueError("Unknown language code.")
    return language


def primary_language(value: str) -> str:
    return Language.get(normalize_language(value)).language


def language_name(value: str) -> str:
    return Language.get(normalize_language(value)).display_name("en")


def native_language_name(value: str) -> str:
    return Language.get(normalize_language(value)).display_name(primary_language(value))


def chinese_script_tag(text: str, language: str) -> str:
    if primary_language(language) != "zh":
        return language
    import hanzidentifier
    detected = hanzidentifier.identify(text)
    if detected == hanzidentifier.TRADITIONAL:
        return "zh-Hant"
    if detected == hanzidentifier.SIMPLIFIED:
        return "zh-Hans"
    return language


_SCRIPT_RANGES = {"Arab": "\u0600-\u06ff", "Hebr": "\u0590-\u05ff", "Cyrl": "\u0400-\u052f",
                  "Deva": "\u0900-\u097f", "Beng": "\u0980-\u09ff", "Taml": "\u0b80-\u0bff",
                  "Telu": "\u0c00-\u0c7f", "Gujr": "\u0a80-\u0aff", "Guru": "\u0a00-\u0a7f",
                  "Knda": "\u0c80-\u0cff", "Mlym": "\u0d00-\u0d7f", "Sinh": "\u0d80-\u0dff",
                  "Thai": "\u0e00-\u0e7f", "Laoo": "\u0e80-\u0eff", "Khmr": "\u1780-\u17ff",
                  "Mymr": "\u1000-\u109f", "Grek": "\u0370-\u03ff", "Armn": "\u0530-\u058f",
                  "Geor": "\u10a0-\u10ff", "Ethi": "\u1200-\u137f", "Jpan": "\u3040-\u30ff",
                  "Kore": "\uac00-\ud7af", "Hans": "\u3400-\u9fff", "Hant": "\u3400-\u9fff"}


def translation_schema(language: str, source_text: str) -> dict:
    """Constrain long translated fragments to the target script when the scripts differ."""
    script = Language.get(normalize_language(language)).maximize().script
    characters = _SCRIPT_RANGES.get(script)
    if characters and sum(char.isalpha() for char in source_text) >= 15:
        return {"type": "string", "pattern": f"^[{characters}].*$"}
    return {"type": "string"}


def ascii_digits(text: str) -> str:
    return "".join(str(unicodedata.decimal(char)) if char.isdecimal() else char for char in text)


_SCRIPTS = {"ARABIC": "Arab", "HEBREW": "Hebr", "CYRILLIC": "Cyrl", "DEVANAGARI": "Deva",
            "BENGALI": "Beng", "TAMIL": "Taml", "TELUGU": "Telu", "GUJARATI": "Gujr",
            "GURMUKHI": "Guru", "KANNADA": "Knda", "MALAYALAM": "Mlym", "SINHALA": "Sinh",
            "THAI": "Thai", "LAO": "Laoo", "KHMER": "Khmr", "MYANMAR": "Mymr",
            "GREEK": "Grek", "ARMENIAN": "Armn", "GEORGIAN": "Geor", "ETHIOPIC": "Ethi",
            "LATIN": "Latn", "HIRAGANA": "Jpan", "KATAKANA": "Jpan", "HANGUL": "Kore",
            "CJK": "Hani"}


def writing_script(text: str) -> str | None:
    clean = re.sub(r"\[\[[^]]+\]\]", "", text)
    counts = Counter(_SCRIPTS.get(unicodedata.name(char, "").split(" ")[0]) for char in clean if char.isalpha())
    counts.pop(None, None)
    if not counts:
        return None
    if counts["Jpan"]:
        return "Jpan"
    if counts["Kore"]:
        return "Kore"
    return counts.most_common(1)[0][0]


def script_matches(text: str, language: str) -> bool:
    actual = writing_script(text)
    expected = Language.get(normalize_language(language)).maximize().script
    if actual is None:
        return True
    if expected in ("Hans", "Hant", "Hani"):
        return actual == "Hani"
    return actual == expected


@lru_cache(maxsize=1)
def _identifier():
    from langid.langid import LanguageIdentifier, model
    return LanguageIdentifier.from_modelstring(model, norm_probs=True)


def offline_guess(text: str) -> tuple[str, float]:
    clean = re.sub(r"\[\[[^]]+\]\]", " ", text)
    language, confidence = _identifier().classify(clean)
    return normalize_language(language), float(confidence)


@lru_cache(maxsize=1)
def offline_languages() -> frozenset[str]:
    return frozenset(normalize_language(language) for language in _identifier().nb_classes)


def refine_local_detection(text: str, model_language: str) -> str:
    """Use independent script/grammar evidence to correct common small-model confusions."""
    candidate, confidence = offline_guess(text)
    script = writing_script(text)
    # Both use Cyrillic, so script matching alone cannot catch this common local-model confusion.
    if (script == "Cyrl" and candidate == "mn" and confidence >= .99
            and re.search(r"\b(нэхэмжлэх|миний|гэсэн|төлбөр)\b", text.lower())):
        return "mn"
    if candidate == primary_language(model_language):
        if script == "Deva" and any(word in text for word in ("मेरो", "हाम्रो", "के हो")):
            return "ne"
        return model_language
    if script == "Deva" and any(word in text for word in ("मेरो", "हाम्रो", "के हो")):
        return "ne"
    if script == "Deva" and candidate == "mr" and confidence >= .90 and any(word in text for word in ("माझ्या", "म्हणजे", "आहे")):
        return candidate
    if script != "Latn" and not script_matches(text, model_language) and script_matches(text, candidate):
        return candidate
    if {primary_language(model_language), candidate} <= {"ms", "id"} and confidence >= .70:
        return candidate
    return model_language


def wrong_output_language(text: str, target: str) -> bool:
    """Reject obvious wrong-script output and long English echoes; do not whitelist output languages."""
    if not script_matches(text, target):
        return True
    if primary_language(target) == "zh":
        detected = chinese_script_tag(text, target)
        if Language.get(detected).maximize().script != Language.get(target).maximize().script:
            return True
    clean = re.sub(r"\[\[[^]]+\]\]", "", text)
    if sum(char.isalpha() for char in clean) >= 40:
        guessed, confidence = offline_guess(clean)
        expected = primary_language(target)
        if guessed == "en" and expected != "en" and confidence >= .95:
            return True
        if expected in offline_languages() and guessed != expected and confidence >= .99:
            return True
    return False


def repetitive_output(text: str) -> bool:
    clean = re.sub(r"\[\[[^]]+\]\]", "", text)
    words = [word.strip(".,;:!?।،") for word in clean.split()]
    for index in range(len(words) - 3):
        if words[index] and len(set(words[index:index + 4])) == 1:
            return True
    return bool(re.search(r"(.{2,20})\1{3,}", clean))
