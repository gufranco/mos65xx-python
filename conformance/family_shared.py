from __future__ import annotations

import tempfile
from pathlib import Path

from conformance.family_member import ROOT

RECORD = ROOT / "conformance" / "hardware.json"


def a_folder_holding(name: str, text: str) -> Path:
    where = Path(tempfile.mkdtemp())
    (where / name).write_text(text)
    return where
