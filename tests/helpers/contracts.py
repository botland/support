from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def contracts_root() -> Path:
    return Path(__file__).resolve().parents[3] / "tests" / "contracts"


def load_contract(name: str) -> Any:
    return json.loads((contracts_root() / name).read_text(encoding="utf-8"))