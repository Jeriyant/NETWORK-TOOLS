"""Auto-update via GitHub Releases."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GITHUB_REPO = "Jeriyant/NETWORK-TOOLS"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}"
USER_AGENT = "NetworkTools-Updater/1.0"


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    changelog: str = ""
    mandatory: bool = False
    html_url: str = ""


def parse_version(text: str) -> tuple[int, ...]:
    text = (text or "").strip().lstrip("vV")
    parts = [int(p) for p in re.findall(r"\d+", text)]
    return tuple(parts) if parts else (0,)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def _http_get_json(url: str, timeout: int = 12) -> dict | list | None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json, application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except urllib.error.HTTPError as exc:
        # 404 = belum ada release / file — bukan error fatal
        if exc.code == 404:
            return None
        raise
    except Exception:
        return None


def _pick_exe_asset(assets: list[dict]) -> str | None:
    preferred: list[str] = []
    others: list[str] = []
    for asset in assets or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        lower = name.lower()
        if lower.endswith(".exe"):
            if "networktools" in lower or "network-tools" in lower:
                preferred.append(url)
            else:
                others.append(url)
    if preferred:
        return preferred[0]
    if others:
        return others[0]
    return None


def check_github_release(local_version: str) -> UpdateInfo | None:
    data = _http_get_json(GITHUB_API_LATEST)
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag or not is_newer(tag, local_version):
        return None
    url = _pick_exe_asset(list(data.get("assets") or []))
    if not url:
        # Release ada tapi belum ada asset EXE — arahkan ke halaman release
        url = str(data.get("html_url") or GITHUB_REPO_URL)
    return UpdateInfo(
        version=tag.lstrip("vV"),
        download_url=url,
        changelog=str(data.get("body") or "").strip(),
        mandatory=False,
        html_url=str(data.get("html_url") or GITHUB_REPO_URL),
    )


def check_for_update(local_version: str) -> UpdateInfo | None:
    """Cek versi baru hanya dari GitHub Releases."""
    try:
        return check_github_release(local_version)
    except Exception:
        return None


def download_file(
    url: str,
    dest: Path,
    timeout: int = 180,
    on_progress: Callable[[int, int | None], None] | None = None,
) -> None:
    """Download file. on_progress(bytes_received, total_bytes_or_None)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:
        total: int | None = None
        try:
            length = resp.headers.get("Content-Length")
            if length and str(length).isdigit():
                total = int(length)
        except Exception:
            total = None

        received = 0
        if on_progress:
            try:
                on_progress(0, total)
            except Exception:
                pass

        while True:
            chunk = resp.read(1024 * 64)
            if not chunk:
                break
            out.write(chunk)
            received += len(chunk)
            if on_progress:
                try:
                    on_progress(received, total)
                except Exception:
                    pass


def is_direct_exe_url(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(".exe")


def apply_update_and_restart(downloaded_exe: Path) -> None:
    """Replace running frozen EXE via a short batch script, then exit."""
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-replace hanya tersedia pada build .exe")

    current = Path(sys.executable).resolve()
    bat = Path(tempfile.gettempdir()) / "network_tools_apply_update.bat"
    # Escape for batch
    cur = str(current)
    new = str(downloaded_exe.resolve())
    script = f"""@echo off
setlocal
set "TARGET={cur}"
set "SOURCE={new}"
timeout /t 2 /nobreak >nul
:waitlock
del /F /Q "%TARGET%" >nul 2>&1
if exist "%TARGET%" (
  timeout /t 1 /nobreak >nul
  goto waitlock
)
move /Y "%SOURCE%" "%TARGET%" >nul
start "" "%TARGET%"
del "%~f0" >nul 2>&1
"""
    bat.write_text(script, encoding="utf-8")
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        cwd=str(current.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )


def current_executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()
