"""Auto-update via GitHub Releases (onedir ZIP — tanpa Temp\\_MEI)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

GITHUB_REPO = "Jeriyant/NETWORK-TOOLS"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}"
USER_AGENT = "NetworkTools-Updater/1.2"

MIN_ZIP_BYTES = 5 * 1024 * 1024
MIN_EXE_BYTES = 8 * 1024 * 1024

_PYI_ENV_KEYS = (
    "_MEIPASS",
    "_MEIPASS2",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONNOUSERSITE",
)

AssetKind = Literal["zip", "exe"]


@dataclass
class UpdateInfo:
    version: str
    download_url: str
    changelog: str = ""
    mandatory: bool = False
    html_url: str = ""
    size: int | None = None
    kind: AssetKind = "zip"


def parse_version(text: str) -> tuple[int, ...]:
    text = (text or "").strip().lstrip("vV")
    parts = [int(p) for p in re.findall(r"\d+", text)]
    return tuple(parts) if parts else (0,)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def default_install_dir() -> Path:
    """Lokasi instalasi tetap (onedir) di LocalAppData — bukan OneDrive/Desktop."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "NetworkTools"


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


def _pick_release_asset(assets: list[dict]) -> tuple[str | None, int | None, AssetKind | None]:
    """Prefer ZIP onedir; fallback EXE (legacy one-file)."""
    zips: list[tuple[str, int | None]] = []
    exes: list[tuple[str, int | None]] = []
    for asset in assets or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if not url:
            continue
        size_raw = asset.get("size")
        size = int(size_raw) if isinstance(size_raw, int) else None
        lower = name.lower()
        item = (url, size)
        if lower.endswith(".zip") and ("networktools" in lower or "network-tools" in lower):
            zips.append(item)
        elif lower.endswith(".zip"):
            zips.append(item)
        elif lower.endswith(".exe") and ("networktools" in lower or "network-tools" in lower):
            exes.append(item)
        elif lower.endswith(".exe"):
            exes.append(item)
    if zips:
        url, size = zips[0]
        return url, size, "zip"
    if exes:
        url, size = exes[0]
        return url, size, "exe"
    return None, None, None


def check_github_release(local_version: str) -> UpdateInfo | None:
    data = _http_get_json(GITHUB_API_LATEST)
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag or not is_newer(tag, local_version):
        return None
    url, size, kind = _pick_release_asset(list(data.get("assets") or []))
    if not url or not kind:
        return UpdateInfo(
            version=tag.lstrip("vV"),
            download_url=str(data.get("html_url") or GITHUB_REPO_URL),
            changelog=str(data.get("body") or "").strip(),
            html_url=str(data.get("html_url") or GITHUB_REPO_URL),
            kind="zip",
        )
    return UpdateInfo(
        version=tag.lstrip("vV"),
        download_url=url,
        changelog=str(data.get("body") or "").strip(),
        mandatory=False,
        html_url=str(data.get("html_url") or GITHUB_REPO_URL),
        size=size,
        kind=kind,
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


def verify_update_file(
    path: Path,
    kind: AssetKind,
    expected_size: int | None = None,
) -> None:
    if not path.is_file():
        raise RuntimeError("File update tidak ditemukan setelah unduhan.")
    size = path.stat().st_size
    if expected_size is not None and size != expected_size:
        raise RuntimeError(
            f"Ukuran file tidak cocok ({size} ≠ {expected_size} byte)."
        )
    if kind == "zip":
        if size < MIN_ZIP_BYTES:
            raise RuntimeError(
                f"File ZIP terlalu kecil ({size} byte) — unduhan gagal."
            )
        if not zipfile.is_zipfile(path):
            raise RuntimeError("File update bukan ZIP valid.")
        return

    if size < MIN_EXE_BYTES:
        raise RuntimeError(
            f"File update terlalu kecil ({size} byte) — kemungkinan unduhan gagal."
        )
    if path.read_bytes()[:2] != b"MZ":
        raise RuntimeError(
            "File update bukan EXE valid. Unduh manual dari GitHub Releases."
        )


def is_direct_update_url(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(".zip") or path.endswith(".exe")


# Backward-compatible alias
def is_direct_exe_url(url: str) -> bool:
    return is_direct_update_url(url)


def verify_exe_file(path: Path, expected_size: int | None = None) -> None:
    verify_update_file(path, "exe", expected_size)


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


def _find_app_root(extracted: Path) -> Path:
    """Cari folder yang berisi NetworkTools.exe + _internal."""
    direct = extracted / "NetworkTools.exe"
    if direct.is_file() and (extracted / "_internal").is_dir():
        return extracted
    nested = extracted / "NetworkTools"
    if (nested / "NetworkTools.exe").is_file() and (nested / "_internal").is_dir():
        return nested
    for exe in extracted.rglob("NetworkTools.exe"):
        if (exe.parent / "_internal").is_dir():
            return exe.parent
    # Legacy: exe tanpa _internal (onefile di dalam zip — jarang)
    for exe in extracted.rglob("NetworkTools.exe"):
        return exe.parent
    raise RuntimeError("NetworkTools.exe tidak ditemukan di paket update.")


def apply_update_and_restart(downloaded: Path, kind: AssetKind | None = None) -> None:
    """
    Pasang update ke %LOCALAPPDATA%\\NetworkTools (onedir) lalu restart.

    Onedir tidak mengekstrak ke Temp\\_MEI, jadi crash python312.dll saat
    update one-file tidak terjadi lagi.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-update hanya tersedia pada build rilis.")

    path = downloaded.resolve()
    if kind is None:
        kind = "zip" if path.suffix.lower() == ".zip" else "exe"

    install = default_install_dir()
    pid = os.getpid()
    proc_name = Path(sys.executable).stem
    task_name = f"NetworkToolsRestart_{pid}"
    ps1 = Path(tempfile.gettempdir()) / f"network_tools_apply_update_{pid}.ps1"
    err_log = Path(tempfile.gettempdir()) / "network_tools_update_error.txt"
    stage = Path(tempfile.gettempdir()) / f"network_tools_stage_{pid}"

    # Siapkan isi stage (folder siap-copy yang berisi NetworkTools.exe)
    if stage.exists():
        shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)

    if kind == "zip":
        extract_to = stage / "extract"
        extract_to.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(extract_to)
        app_root = _find_app_root(extract_to)
        # Salin isi app_root ke stage/app
        app_stage = stage / "app"
        shutil.copytree(app_root, app_stage)
    else:
        # Legacy one-file: tetap simpan sebagai NetworkTools.exe di stage/app
        # (bukan solusi ideal; rilis baru memakai ZIP onedir)
        app_stage = stage / "app"
        app_stage.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, app_stage / "NetworkTools.exe")

    new_exe = app_stage / "NetworkTools.exe"
    if not new_exe.is_file():
        raise RuntimeError("Paket update tidak berisi NetworkTools.exe.")

    def _ps_single(s: str) -> str:
        return s.replace("'", "''")

    script = f"""$ErrorActionPreference = 'Continue'
$sourceApp = '{_ps_single(str(app_stage))}'
$installDir = '{_ps_single(str(install))}'
$targetExe = '{_ps_single(str(install / "NetworkTools.exe"))}'
$errLog = '{_ps_single(str(err_log))}'
$oldPid = {pid}
$procName = '{_ps_single(proc_name)}'
$taskName = '{_ps_single(task_name)}'
$stageRoot = '{_ps_single(str(stage))}'
$pkg = '{_ps_single(str(path))}'

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

if (-not (Test-Path -LiteralPath $sourceApp)) {{ Fail "Stage update hilang" }}

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

Start-Sleep -Seconds 3

# Pasang ke LocalAppData\\NetworkTools (onedir — tanpa _MEI)
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
try {{
  # Hapus _internal lama agar tidak campur versi
  $oldInternal = Join-Path $installDir '_internal'
  if (Test-Path -LiteralPath $oldInternal) {{
    Remove-Item -LiteralPath $oldInternal -Recurse -Force -ErrorAction Stop
  }}
  Copy-Item -Path (Join-Path $sourceApp '*') -Destination $installDir -Recurse -Force -ErrorAction Stop
}} catch {{
  Fail "Gagal memasang update: $($_.Exception.Message)"
}}

if (-not (Test-Path -LiteralPath $targetExe)) {{
  Fail "NetworkTools.exe tidak ada setelah pasang"
}}

Start-Sleep -Seconds 2

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
$arg = '/c timeout /t 3 /nobreak >nul & set "_MEIPASS=" & set "_MEIPASS2=" & set "PYTHONHOME=" & set "PYTHONPATH=" & start "" /D "' + $installDir + '" "' + $targetExe + '"'
try {{
  $action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $arg
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
  Register-ScheduledTask -TaskName $taskName -Action $action -Principal $principal -Settings $settings -Force | Out-Null
  Start-ScheduledTask -TaskName $taskName
}} catch {{
  try {{
    Start-Process -FilePath 'cmd.exe' -ArgumentList $arg -WindowStyle Hidden
  }} catch {{
    Fail "Gagal menjalankan aplikasi baru: $($_.Exception.Message)"
  }}
}}

Start-Sleep -Seconds 2
Remove-Item -LiteralPath $pkg -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $stageRoot -Recurse -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 12
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
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
        cwd=str(install),
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
