"""Tunable settings. Environment variables override defaults."""
import os
from pathlib import Path

CMS_DIR = Path(__file__).parent / "cms_data"
CMS_FILES_DIR = Path(os.environ.get("CMS_FILES_DIR", CMS_DIR / "files"))
PRICE_OUTLIER_MULTIPLE = float(os.environ.get("PRICE_OUTLIER_MULTIPLE", "5.0"))
# Modifiers that make an NCCI indicator-1 pair potentially legitimate (downgrade finding to "ask").
NCCI_OVERRIDE_MODIFIERS = {"59", "XE", "XS", "XP", "XU", "25", "24", "57", "58", "78", "79", "91",
                           "LT", "RT", "E1", "E2", "E3", "E4", "FA", "F1", "F2", "F3", "F4", "F5",
                           "F6", "F7", "F8", "F9", "TA", "T1", "T2", "T3", "T4", "T5", "T6", "T7",
                           "T8", "T9", "LC", "LD", "LM", "RC", "RI"}
REPEAT_MODIFIERS = {"76", "77"}
