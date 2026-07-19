"""Persist theme & language preferences."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _prefs_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    folder = base / "NetworkTools"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "prefs.json"


def load_prefs() -> dict[str, Any]:
    path = _prefs_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_prefs(**kwargs: Any) -> None:
    path = _prefs_path()
    data = load_prefs()
    data.update({k: v for k, v in kwargs.items() if v is not None})
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
