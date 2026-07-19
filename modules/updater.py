"""Auto-update via GitHub Releases."""

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
USER_AGENT = "NetworkTools-Updater/1.0"

# EXE build normal ~20MB+; di bawah ini hampir pasti rusak/bukan paket lengkap
MIN_EXE_BYTES = 8 * 1024 * 1024


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
        if lower.endswith(".exe"):
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
    """Cek versi baru hanya dari GitHub Releases."""
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
    """Download file. Returns bytes written. Raises if incomplete/invalid."""
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
    """Pastikan file adalah PE (.exe) yang cukup besar, bukan HTML/error page."""
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
    header = path.read_bytes()[:2]
    if header != b"MZ":
        raise RuntimeError(
            "File update bukan EXE valid (header rusak). "
            "Unduh manual dari GitHub Releases."
        )


def is_direct_exe_url(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(".exe")


def apply_update_and_restart(downloaded_exe: Path) -> None:
    """
    Ganti EXE yang sedang jalan lewat updater PowerShell terpisah.

    PyInstaller onefile punya proses bootloader induk yang baru menghapus
    folder _MEI setelah child (app) keluar. Jika EXE baru dijalankan terlalu
    cepat / sebagai anak dari proses lama, Windows sering gagal extract
    python312.dll. Solusi:
    - Jalankan updater lewat ShellExecute (bukan child tree Python)
    - Tunggu PID app + semua instance EXE hilang
    - Tunggu file EXE bisa di-rename (bootloader selesai)
    - Jeda ekstra, baru swap + Start-Process mandiri
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-replace hanya tersedia pada build .exe")

    current = Path(sys.executable).resolve()
    source = downloaded_exe.resolve()
    workdir = str(current.parent)
    pid = os.getpid()
    # Get-Process -Name memakai nama tanpa ekstensi
    proc_name = current.stem

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

function Fail([string]$msg) {{
  Set-Content -LiteralPath $errLog -Value $msg -Encoding UTF8
  exit 1
}}

if (-not (Test-Path -LiteralPath $source)) {{
  Fail "Source update hilang: $source"
}}

# 1) Tunggu proses app (child) keluar
$tries = 0
while (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {{
  $tries++
  if ($tries -gt 120) {{ Fail "Timeout menunggu PID $oldPid keluar" }}
  Start-Sleep -Milliseconds 500
}}

# 2) Tunggu semua instance (termasuk bootloader induk)
$tries = 0
while (Get-Process -Name $procName -ErrorAction SilentlyContinue) {{
  $tries++
  if ($tries -gt 120) {{ Fail "Timeout menunggu $procName keluar" }}
  Start-Sleep -Milliseconds 500
}}

# 3) Tunggu file EXE bisa di-rename (= handle bootloader / AV lepas)
$old = "$target.old"
$tries = 0
while ($true) {{
  try {{
    if (Test-Path -LiteralPath $old) {{
      Remove-Item -LiteralPath $old -Force -ErrorAction Stop
    }}
    if (Test-Path -LiteralPath $target) {{
      Move-Item -LiteralPath $target -Destination $old -Force -ErrorAction Stop
    }}
    break
  }} catch {{
    $tries++
    if ($tries -gt 90) {{ Fail "Tidak bisa mengunci file lama (masih dipakai)" }}
    Start-Sleep -Milliseconds 500
  }}
}}

# 4) Jeda agar folder _MEI lama selesai dibersihkan bootloader
Start-Sleep -Seconds 4

try {{
  Copy-Item -LiteralPath $source -Destination $target -Force -ErrorAction Stop
}} catch {{
  if (Test-Path -LiteralPath $old) {{
    Move-Item -LiteralPath $old -Destination $target -Force -ErrorAction SilentlyContinue
  }}
  Fail "Copy gagal: $($_.Exception.Message)"
}}

if (-not (Test-Path -LiteralPath $target)) {{
  Fail "Target hilang setelah copy"
}}

$szSrc = (Get-Item -LiteralPath $source).Length
$szDst = (Get-Item -LiteralPath $target).Length
if ($szSrc -ne $szDst) {{
  Remove-Item -LiteralPath $target -Force -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $old) {{
    Move-Item -LiteralPath $old -Destination $target -Force -ErrorAction SilentlyContinue
  }}
  Fail "Ukuran setelah copy tidak cocok ($szDst vs $szSrc)"
}}

# 5) Jeda singkat untuk antivirus scan
Start-Sleep -Seconds 2

# 6) Jalankan EXE baru sebagai proses mandiri
try {{
  Start-Process -FilePath $target -WorkingDirectory $workdir
}} catch {{
  Fail "Gagal menjalankan EXE baru: $($_.Exception.Message)"
}}

Start-Sleep -Seconds 2
Remove-Item -LiteralPath $source -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
    ps1.write_text(script, encoding="utf-8")

    # ShellExecute memutus relationship dengan proses PyInstaller (penting!)
    params = (
        f'-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps1}"'
    )
    try:
        import ctypes

        rc = int(
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "open",
                "powershell.exe",
                params,
                str(current.parent),
                0,  # SW_HIDE
            )
        )
        if rc <= 32:
            raise OSError(f"ShellExecute gagal (kode {rc})")
    except Exception:
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
            cwd=str(current.parent),
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def cleanup_update_leftovers() -> None:
    """Hapus sisa file update (.old / .new) di folder EXE bila ada."""
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
