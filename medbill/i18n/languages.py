"""Language codes, names and small script-based sanity checks for model output.

Reconstructed from how translate.py, qa.py, glossary.py and the API use it. Nothing here decides anything
about a bill; these helpers only normalise language tags and catch obviously wrong model output."""
from __future__ import annotations

import re
import unicodedata

# code -> (English name, native name)
LANGUAGES: dict[str, tuple[str, str]] = {
    "en": ("English", "English"), "es": ("Spanish", "Español"), "mn": ("Mongolian", "Монгол"),
    "fr": ("French", "Français"), "de": ("German", "Deutsch"), "it": ("Italian", "Italiano"),
    "pt": ("Portuguese", "Português"), "nl": ("Dutch", "Nederlands"), "pl": ("Polish", "Polski"),
    "ru": ("Russian", "Русский"), "uk": ("Ukrainian", "Українська"), "tr": ("Turkish", "Türkçe"),
    "ar": ("Arabic", "العربية"), "he": ("Hebrew", "עברית"), "fa": ("Persian", "فارسی"),
    "ur": ("Urdu", "اردو"), "hi": ("Hindi", "हिन्दी"), "bn": ("Bengali", "বাংলা"),
    "ta": ("Tamil", "தமிழ்"), "te": ("Telugu", "తెలుగు"), "gu": ("Gujarati", "ગુજરાતી"),
    "pa": ("Punjabi", "ਪੰਜਾਬੀ"), "ne": ("Nepali", "नेपाली"), "zh": ("Chinese", "中文"),
    "ja": ("Japanese", "日本語"), "ko": ("Korean", "한국어"), "vi": ("Vietnamese", "Tiếng Việt"),
    "th": ("Thai", "ไทย"), "id": ("Indonesian", "Bahasa Indonesia"), "ms": ("Malay", "Bahasa Melayu"),
    "tl": ("Tagalog", "Tagalog"), "sw": ("Swahili", "Kiswahili"), "am": ("Amharic", "አማርኛ"),
    "el": ("Greek", "Ελληνικά"), "ro": ("Romanian", "Română"), "cs": ("Czech", "Čeština"),
    "hu": ("Hungarian", "Magyar"), "sv": ("Swedish", "Svenska"), "bg": ("Bulgarian", "Български"),
    "kk": ("Kazakh", "Қазақша"),
}
_ISO3 = {
    "eng": "en", "spa": "es", "mon": "mn", "khk": "mn", "fra": "fr", "fre": "fr", "deu": "de", "ger": "de",
    "ita": "it", "por": "pt", "nld": "nl", "dut": "nl", "pol": "pl", "rus": "ru", "ukr": "uk", "tur": "tr",
    "ara": "ar", "heb": "he", "fas": "fa", "per": "fa", "urd": "ur", "hin": "hi", "ben": "bn", "tam": "ta",
    "tel": "te", "guj": "gu", "pan": "pa", "nep": "ne", "zho": "zh", "chi": "zh", "cmn": "zh", "jpn": "ja",
    "kor": "ko", "vie": "vi", "tha": "th", "ind": "id", "msa": "ms", "may": "ms", "tgl": "tl", "fil": "tl",
    "swa": "sw", "amh": "am", "ell": "el", "gre": "el", "ron": "ro", "rum": "ro", "ces": "cs", "cze": "cs",
    "hun": "hu", "swe": "sv", "bul": "bg", "kaz": "kk",
}
_TAG = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})*$", re.IGNORECASE)

# Unicode script ranges per language family (for wrong-output checks).
_SCRIPTS = {
    "latin": [(0x41, 0x24F), (0x1E00, 0x1EFF)],
    "cyrillic": [(0x400, 0x52F)],
    "arabic": [(0x600, 0x6FF), (0x750, 0x77F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "hebrew": [(0x590, 0x5FF)],
    "devanagari": [(0x900, 0x97F)], "bengali": [(0x980, 0x9FF)], "gurmukhi": [(0xA00, 0xA7F)],
    "gujarati": [(0xA80, 0xAFF)], "tamil": [(0xB80, 0xBFF)], "telugu": [(0xC00, 0xC7F)],
    "thai": [(0xE00, 0xE7F)], "ethiopic": [(0x1200, 0x139F)], "greek": [(0x370, 0x3FF), (0x1F00, 0x1FFF)],
    "hangul": [(0xAC00, 0xD7AF), (0x1100, 0x11FF), (0x3130, 0x318F)],
    "kana": [(0x3040, 0x30FF)],
    "han": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)],
}
_LANG_SCRIPTS = {
    "ru": ["cyrillic"], "uk": ["cyrillic"], "bg": ["cyrillic"], "mn": ["cyrillic"], "kk": ["cyrillic"],
    "ar": ["arabic"], "fa": ["arabic"], "ur": ["arabic"], "he": ["hebrew"], "hi": ["devanagari"],
    "ne": ["devanagari"], "bn": ["bengali"], "pa": ["gurmukhi"], "gu": ["gujarati"], "ta": ["tamil"],
    "te": ["telugu"], "th": ["thai"], "am": ["ethiopic"], "el": ["greek"], "ko": ["hangul", "han"],
    "ja": ["kana", "han"], "zh": ["han"],
}
_SCRIPT_DEFAULT = {"cyrillic": "ru", "arabic": "ar", "hebrew": "he", "devanagari": "hi", "bengali": "bn",
                   "gurmukhi": "pa", "gujarati": "gu", "tamil": "ta", "telugu": "te", "thai": "th",
                   "ethiopic": "am", "greek": "el", "hangul": "ko", "kana": "ja", "han": "zh"}
_TOKEN = re.compile(r"\[\[[A-Z]+_\d+\]\]|\{[A-Za-z_]+\}")
_TRAD = set("體國學臺灣開關門車東馬這個們說話請問題費險據錢們點邊還護帳單")
_SIMP = set("体国学台湾开关门车东马这个们说话请问题费险据钱点边还护账单")


def normalize_language(lang: str) -> str:
    """Canonical BCP-47-like tag ('fra' -> 'fr', 'zh-hant-tw' -> 'zh-Hant-TW'). Raises ValueError if malformed."""
    tag = str(lang or "").strip().replace("_", "-")
    if not _TAG.match(tag):
        raise ValueError(f"Unsupported language code: {lang!r}")
    parts = tag.split("-")
    base = parts[0].lower()
    base = _ISO3.get(base, base)
    if len(base) == 3:
        raise ValueError(f"Unsupported language code: {lang!r}")
    out = [base]
    for sub in parts[1:]:
        if len(sub) == 4 and sub.isalpha():
            out.append(sub.title())
        elif (len(sub) == 2 and sub.isalpha()) or (len(sub) == 3 and sub.isdigit()):
            out.append(sub.upper())
        else:
            out.append(sub.lower())
    return "-".join(out)


def primary_language(lang: str) -> str:
    return normalize_language(lang).split("-")[0]


def language_name(lang: str) -> str:
    code = normalize_language(lang)
    if code.startswith("zh"):
        if "Hant" in code or code.endswith(("-TW", "-HK", "-MO")):
            return "Traditional Chinese"
        if "Hans" in code:
            return "Simplified Chinese"
    return LANGUAGES.get(code.split("-")[0], (code, code))[0]


def native_language_name(lang: str) -> str:
    code = normalize_language(lang)
    return LANGUAGES.get(code.split("-")[0], (code, code))[1]


def ascii_digits(text: str) -> str:
    """Convert any Unicode decimal digits (Arabic-Indic, Devanagari, full-width...) to 0-9."""
    return "".join(str(unicodedata.digit(c)) if c.isdigit() and unicodedata.decimal(c, None) is not None else c
                   for c in text)


def _letters(text: str) -> list[str]:
    return [c for c in _TOKEN.sub(" ", text) if c.isalpha()]


def _script_of(char: str) -> str | None:
    code = ord(char)
    for name, ranges in _SCRIPTS.items():
        if any(lo <= code <= hi for lo, hi in ranges):
            return name
    return None


def _dominant_script(text: str) -> tuple[str | None, float]:
    letters = _letters(text)
    if not letters:
        return None, 0.0
    counts: dict[str, int] = {}
    for c in letters:
        s = _script_of(c)
        if s:
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return None, 0.0
    if "kana" in counts:  # Japanese mixes kana with han
        counts["kana"] += counts.pop("han", 0)
    best = max(counts, key=counts.get)
    return best, counts[best] / len(letters)


def refine_local_detection(text: str, lang: str) -> str:
    """Small local models sometimes mislabel a script. Keep their answer unless the script clearly contradicts it."""
    try:
        code = primary_language(lang)
    except ValueError:
        code = ""
    script, share = _dominant_script(text)
    if script is None or share < 0.6:
        return lang if code else "en"
    expected = _LANG_SCRIPTS.get(code, ["latin"])
    if script in expected:
        return lang
    if script == "latin":
        return lang if code in LANGUAGES and code not in _LANG_SCRIPTS else "en"
    return _SCRIPT_DEFAULT.get(script, lang)


def chinese_script_tag(text: str, lang: str) -> str:
    """Tag Chinese as zh-Hans or zh-Hant from the characters used, unless the model already said which."""
    try:
        code = normalize_language(lang)
    except ValueError:
        return lang
    if code.split("-")[0] != "zh" or len(code.split("-")) > 1:
        return code
    trad, simp = sum(c in _TRAD for c in text), sum(c in _SIMP for c in text)
    return "zh-Hant" if trad > simp else "zh-Hans"


def repetitive_output(text: str) -> bool:
    """Detect degenerate loops ('the the the...', a phrase repeated over and over, long character runs)."""
    if not text:
        return False
    if re.search(r"(.)\1{19,}", text):
        return True
    words = re.findall(r"\w+", text.lower())
    if len(words) >= 8:
        if re.search(r"\b(\w+)(?:\s+\1\b){5,}", " ".join(words)):
            return True
        for size in (2, 3, 4):
            grams: dict[tuple, int] = {}
            for i in range(len(words) - size + 1):
                gram = tuple(words[i:i + size])
                grams[gram] = grams.get(gram, 0) + 1
            if grams and max(grams.values()) >= 4 and max(grams.values()) * size >= len(words) * 0.6:
                return True
    return False


def wrong_output_language(text: str, lang: str) -> bool:
    """True when the text's script clearly cannot be the requested language (e.g. English returned for Mongolian)."""
    try:
        code = primary_language(lang)
    except ValueError:
        return False
    letters = _letters(text)
    if len(letters) < 4:
        return False
    expected = set(_LANG_SCRIPTS.get(code, ["latin"]))
    matching = sum(_script_of(c) in expected for c in letters)
    if code in _LANG_SCRIPTS:
        return matching / len(letters) < 0.5
    # Latin-script languages: a few foreign letters are fine, a mostly non-Latin answer is not.
    return matching / len(letters) < 0.7


def translation_schema(target: str, value: str) -> dict:
    """JSON schema for one translated fragment (bounded so a small model cannot ramble)."""
    return {"type": "string", "minLength": 1, "maxLength": max(60, len(value) * 5)}
