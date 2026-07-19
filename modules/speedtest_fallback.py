"""Open Speedtest in Microsoft Edge app-window mode (no pythonnet)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _find_edge() -> str | None:
    candidates = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Microsoft\Edge\Application\msedge.exe",
    ]
    which = shutil.which("msedge.exe")
    if which:
        candidates.insert(0, which)
    for path in candidates:
        if path and Path(path).is_file():
            return path
    return None


def open_speedtest_edge_app(url: str) -> tuple[bool, str]:
    """
    Open URL in Edge --app= window (looks like in-app browser, no scrollbar chrome).
    Returns (ok, message).
    """
    edge = _find_edge()
    if not edge:
        return False, "Microsoft Edge tidak ditemukan di komputer ini."
    try:
        subprocess.Popen(
            [
                edge,
                f"--app={url}",
                "--new-window",
                "--window-size=1100,750",
            ],
            shell=False,
        )
        return True, "Speedtest dibuka di jendela Edge (mode aplikasi)."
    except Exception as exc:
        return False, str(exc)
