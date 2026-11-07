"""Rule registry. A rule is one file in this package exposing:

    NAME: str
    ORDER: int            # lower runs first; later rules can see earlier findings in case.findings
    def run(case: Case) -> list[Finding]

Adding a rule is adding one file; no other code changes."""
from __future__ import annotations

import importlib
import pkgutil
from types import ModuleType

from ..models import Case, Finding


def load_rules() -> list[ModuleType]:
    mods = []
    for info in pkgutil.iter_modules(__path__):
        m = importlib.import_module(f"{__name__}.{info.name}")
        if hasattr(m, "run") and hasattr(m, "NAME"):
            mods.append(m)
    return sorted(mods, key=lambda m: m.ORDER)


def flagged_line_ids(case: Case) -> set[str]:
    """Bill lines already flagged definite/likely."""
    return {lid for f in case.findings if f.tier != "ask" for lid in f.impact_line_ids}


__all__ = ["Case", "Finding", "flagged_line_ids", "load_rules"]
