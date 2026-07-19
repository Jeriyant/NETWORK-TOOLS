"""Auto-update via GitHub Releases — single-file EXE."""

from __future__ import annotations

import json
import os
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
USER_AGENT = "NetworkTools-Updater/1.3"

MIN_EXE_BYTES = 8 * 1024 * 1024

_PYI_ENV_KEYS = (
    "_MEIPASS",
    "_MEIPASS2",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONNOUSERSITE",
)


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    changelog: str = ""
    mandatory: bool = False
    html_url: str = ""
    size: int | None = None


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
        if exc.code == 404:
            return None
        raise
    except Exception:
        return None


def _pick_exe_asset(assets: list[dict]) -> tuple[str | None, int | None]:
    preferred: list[tuple[str, int | None]] = []
    others: list[tuple[str, int | None]] = []
    for asset in assets or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        size_raw = asset.get("size")
        size = int(size_raw) if isinstance(size_raw, int) else None
        lower = name.lower()
        if not lower.endswith(".exe"):
            continue
        item = (url, size)
        if "networktools" in lower or "network-tools" in lower:
            preferred.append(item)
        else:
            others.append(item)
    if preferred:
        return preferred[0]
    if others:
        return others[0]
    return None, None


def check_github_release(local_version: str) -> UpdateInfo | None:
    data = _http_get_json(GITHUB_API_LATEST)
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag or not is_newer(tag, local_version):
        return None
    url, size = _pick_exe_asset(list(data.get("assets") or []))
    if not url:
        url = str(data.get("html_url") or GITHUB_REPO_URL)
    return UpdateInfo(
        version=tag.lstrip("vV"),
        download_url=url,
        changelog=str(data.get("body") or "").strip(),
        mandatory=False,
        html_url=str(data.get("html_url") or GITHUB_REPO_URL),
        size=size,
    )


def check_for_update(local_version: str) -> UpdateInfo | None:
    try:
        return check_github_release(local_version)
    except Exception:
        return None


def download_file(
    url: str,
    dest: Path,
    timeout: int = 300,
    on_progress: Callable[[int, int | None], None] | None = None,
    expected_size: int | None = None,
) -> int:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:
        total: int | None = expected_size
        try:
            length = resp.headers.get("Content-Length")
            if length and str(length).isdigit():
                total = int(length)
        except Exception:
            pass

        received = 0
        if on_progress:
            try:
                on_progress(0, total)
            except Exception:
                pass

        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            received += len(chunk)
            if on_progress:
                try:
                    on_progress(received, total)
                except Exception:
                    pass

        out.flush()

    if total is not None and received != total:
        raise RuntimeError(
            f"Unduhan tidak lengkap ({received} / {total} byte). Coba lagi."
        )
    return received


def verify_exe_file(path: Path, expected_size: int | None = None) -> None:
    if not path.is_file():
        raise RuntimeError("File update tidak ditemukan setelah unduhan.")
    size = path.stat().st_size
    if expected_size is not None and size != expected_size:
        raise RuntimeError(
            f"Ukuran file tidak cocok ({size} ≠ {expected_size} byte)."
        )
    if size < MIN_EXE_BYTES:
        raise RuntimeError(
            f"File update terlalu kecil ({size} byte) — kemungkinan unduhan gagal."
        )
    if path.read_bytes()[:2] != b"MZ":
        raise RuntimeError(
            "File update bukan EXE valid (header rusak). "
            "Unduh manual dari GitHub Releases."
        )


def is_direct_exe_url(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(".exe")


def is_direct_update_url(url: str) -> bool:
    return is_direct_exe_url(url)


def verify_update_file(path: Path, kind: str = "exe", expected_size: int | None = None) -> None:
    verify_exe_file(path, expected_size)


def _clean_environ() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() not in {x.upper() for x in _PYI_ENV_KEYS}
    }
    for key in list(env):
        if key.upper().startswith("_MEI"):
            env.pop(key, None)
    return env


def apply_update_and_restart(downloaded_exe: Path, kind: str | None = None) -> None:
    """
    Ganti single-file EXE di tempat, lalu minta user klik OK untuk membuka.

    Tidak auto-start langsung dari process tree lama (itu pemicu crash
    Failed to load Python DLL / _MEI). Setelah app tutup:
    1) tunggu proses + file unlock
    2) ganti EXE
    3) bersihkan folder runtime LocalAppData lama
    4) MessageBox → Start-Process dengan env bersih
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-replace hanya tersedia pada build .exe")

    current = Path(sys.executable).resolve()
    source = downloaded_exe.resolve()
    workdir = str(current.parent)
    pid = os.getpid()
    proc_name = current.stem
    runtime_dir = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        / "NetworkTools"
        / "runtime"
    )

    ps1 = Path(tempfile.gettempdir()) / f"network_tools_apply_update_{pid}.ps1"
    err_log = Path(tempfile.gettempdir()) / "network_tools_update_error.txt"

    def _ps_single(s: str) -> str:
        return s.replace("'", "''")

    script = f"""$ErrorActionPreference = 'Continue'
$target = '{_ps_single(str(current))}'
$source = '{_ps_single(str(source))}'
$workdir = '{_ps_single(workdir)}'
$errLog = '{_ps_single(str(err_log))}'
$oldPid = {pid}
$procName = '{_ps_single(proc_name)}'
$runtimeDir = '{_ps_single(str(runtime_dir))}'

function Fail([string]$msg) {{
  Set-Content -LiteralPath $errLog -Value $msg -Encoding UTF8
  exit 1
}}

foreach ($k in @('_MEIPASS','_MEIPASS2','PYTHONHOME','PYTHONPATH','PYTHONNOUSERSITE')) {{
  Remove-Item "Env:$k" -ErrorAction SilentlyContinue
}}
Get-ChildItem Env: | Where-Object {{ $_.Name -like '_MEI*' }} | ForEach-Object {{
  Remove-Item "Env:$($_.Name)" -ErrorAction SilentlyContinue
}}

if (-not (Test-Path -LiteralPath $source)) {{ Fail "Source update hilang: $source" }}

$tries = 0
while (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {{
  $tries++; if ($tries -gt 120) {{ Fail "Timeout menunggu PID $oldPid" }}
  Start-Sleep -Milliseconds 500
}}

$tries = 0
while (Get-Process -Name $procName -ErrorAction SilentlyContinue) {{
  $tries++; if ($tries -gt 120) {{ Fail "Timeout menunggu $procName" }}
  Start-Sleep -Milliseconds 500
}}

$old = "$target.old"
$tries = 0
while ($true) {{
  try {{
    if (Test-Path -LiteralPath $old) {{ Remove-Item -LiteralPath $old -Force -ErrorAction Stop }}
    if (Test-Path -LiteralPath $target) {{
      Move-Item -LiteralPath $target -Destination $old -Force -ErrorAction Stop
    }}
    break
  }} catch {{
    $tries++; if ($tries -gt 90) {{ Fail "Tidak bisa mengunci file lama" }}
    Start-Sleep -Milliseconds 500
  }}
}}

Start-Sleep -Seconds 2

try {{
  Copy-Item -LiteralPath $source -Destination $target -Force -ErrorAction Stop
}} catch {{
  if (Test-Path -LiteralPath $old) {{
    Move-Item -LiteralPath $old -Destination $target -Force -ErrorAction SilentlyContinue
  }}
  Fail "Copy gagal: $($_.Exception.Message)"
}}

$szSrc = (Get-Item -LiteralPath $source).Length
$szDst = (Get-Item -LiteralPath $target).Length
if ($szSrc -ne $szDst) {{
  Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $old) {{ Move-Item -LiteralPath $old -Destination $target -Force -ErrorAction SilentlyContinue }}
  Fail "Ukuran setelah copy tidak cocok ($szDst vs $szSrc)"
}}

# Bersihkan sisa extract runtime versi lama
if (Test-Path -LiteralPath $runtimeDir) {{
  Remove-Item -LiteralPath $runtimeDir -Recurse -Force -ErrorAction SilentlyContinue
}}

Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue

# Dialog di proses terpisah — pastikan tidak mewarisi _MEIPASS, lalu buka EXE
Add-Type -AssemblyName System.Windows.Forms | Out-Null
[System.Windows.Forms.MessageBox]::Show(
  "Update Network Tools selesai.`r`n`r`nKlik OK untuk membuka aplikasi.",
  "Network Tools",
  [System.Windows.Forms.MessageBoxButtons]::OK,
  [System.Windows.Forms.MessageBoxIcon]::Information
) | Out-Null

foreach ($k in @('_MEIPASS','_MEIPASS2','PYTHONHOME','PYTHONPATH','PYTHONNOUSERSITE')) {{
  Remove-Item "Env:$k" -ErrorAction SilentlyContinue
}}

Start-Process -FilePath $target -WorkingDirectory $workdir
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
    ps1.write_text(script, encoding="utf-8")

    flags = 0
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    flags |= 0x01000000  # CREATE_BREAKAWAY_FROM_JOB

    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            str(ps1),
        ],
        cwd=workdir,
        env=_clean_environ(),
        creationflags=flags,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def cleanup_update_leftovers() -> None:
    if not getattr(sys, "frozen", False):
        return
    current = Path(sys.executable).resolve()
    for suffix in (".old", ".new"):
        leftover = current.with_name(current.name + suffix)
        try:
            if leftover.is_file():
                leftover.unlink(missing_ok=True)
        except Exception:
            pass


def current_executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()
