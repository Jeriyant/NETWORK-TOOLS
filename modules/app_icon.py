"""Resolve bundled application icon path (EXE + window)."""

from __future__ import annotations

import sys
from pathlib import Path


def app_icon_path() -> Path | None:
    """Return path to assets/app.ico if present (dev or frozen)."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        mei = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        candidates.append(mei / "assets" / "app.ico")
        candidates.append(Path(sys.executable).resolve().parent / "assets" / "app.ico")
    else:
        root = Path(__file__).resolve().parent.parent
        candidates.append(root / "assets" / "app.ico")

    for path in candidates:
        if path.is_file():
            return path
    return None
