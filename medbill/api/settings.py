from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


@dataclass
class Settings:
    demo_mode: bool = field(default_factory=lambda: _flag("DEMO_MODE"))
    ttl_seconds: int = field(default_factory=lambda: int(os.environ.get("CASE_TTL_SECONDS", "7200")))
    max_upload_bytes: int = 15 * 1024 * 1024
    samples_dir: Path = ROOT / "data" / "samples"
