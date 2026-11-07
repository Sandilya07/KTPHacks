"""4D. Letter translation: the body is translated through the same number-integrity layer and returned
as (English, translation) segments for side-by-side display. The English version is always the one to send."""
from __future__ import annotations

from dataclasses import dataclass

from explain.letter import Letter
from explain.templates import money

from .translate import Translator


@dataclass
class Segment:
    section: str
    english: str
    translated: str
    verified: bool
    notice: str = ""


def english_segment_parts(letter: Letter) -> list[tuple[str, list[str]]]:
    """Each letter section as reusable sentences (see Answer.parts)."""
    segs: list[tuple[str, list[str]]] = [("opening", [letter.opening])]
    for i, r in enumerate(letter.rows, 1):
        segs.append((f"charge {i}", [
            f"{r.date}: code {r.code}, billed {r.billed}, patient owed {r.patient_owed}.",
            f"The EOB says: {r.eob_says}.", f"Reason: {r.reason}", f"Amount in question: {money(r.amount)}."]))
    segs.append(("total", [f"Total amount in question: {money(letter.total)}."]))
    segs += [("citation", [c]) for c in letter.citations]
    segs += [("question", [q]) for q in letter.questions]
    segs += [("request", [r]) for r in letter.requests]
    segs += [("closing", [letter.closing]), ("note", [letter.note])]
    return segs


def english_segments(letter: Letter) -> list[tuple[str, str]]:
    return [(section, " ".join(parts)) for section, parts in english_segment_parts(letter)]


def translate_letter(letter: Letter, translator: Translator, lang: str) -> list[Segment]:
    out = []
    for section, parts in english_segment_parts(letter):
        tr = translator.translate_parts(parts, lang)
        out.append(Segment(section, " ".join(parts), tr.text, tr.verified, tr.notice))
    return out
