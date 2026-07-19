"""Auto-update via GitHub Releases.

Alur update (sesuai permintaan):
1. Tutup aplikasi
2. Hapus program di lokasi lama
3. Ganti dengan paket baru
4. Jalankan lagi otomatis (via explorer, env bersih)

Build memakai onedir (folder) agar tidak ada extract _MEI/python312.dll.
"""

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

MIN_EXE_BYTES = 5 * 1024 * 1024
MIN_ZIP_BYTES = 5 * 1024 * 1024

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


def _pick_update_asset(assets: list[dict]) -> tuple[str | None, int | None]:
    """Prefer NetworkTools.zip (onedir), fallback ke .exe."""
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
        return zips[0]
    if exes:
        return exes[0]
    return None, None


def check_github_release(local_version: str) -> UpdateInfo | None:
    data = _http_get_json(GITHUB_API_LATEST)
    if not isinstance(data, dict):
        return None
    tag = str(data.get("tag_name") or data.get("name") or "").strip()
    if not tag or not is_newer(tag, local_version):
        return None
    url, size = _pick_update_asset(list(data.get("assets") or []))
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
    header = path.read_bytes()[:2]
    if header != b"MZ":
        raise RuntimeError(
            "File update bukan EXE valid (header rusak). "
            "Unduh manual dari GitHub Releases."
        )


def verify_update_file(path: Path, expected_size: int | None = None) -> None:
    """Validasi paket update (.zip onedir atau .exe)."""
    if not path.is_file():
        raise RuntimeError("File update tidak ditemukan setelah unduhan.")
    size = path.stat().st_size
    if expected_size is not None and size != expected_size:
        raise RuntimeError(
            f"Ukuran file tidak cocok ({size} ≠ {expected_size} byte)."
        )
    suffix = path.suffix.lower()
    if suffix == ".zip":
        if size < MIN_ZIP_BYTES:
            raise RuntimeError(
                f"Paket zip terlalu kecil ({size} byte) — unduhan gagal."
            )
        header = path.read_bytes()[:4]
        if header[:2] != b"PK":
            raise RuntimeError("File update bukan ZIP valid.")
        return
    verify_exe_file(path, expected_size=expected_size)


def is_direct_update_url(url: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(".exe") or path.endswith(".zip")


def is_direct_exe_url(url: str) -> bool:
    """Kompatibilitas lama — true untuk exe atau zip langsung."""
    return is_direct_update_url(url)


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


def apply_update_and_restart(downloaded: Path) -> None:
    """
    Tutup app → hapus program lama di lokasinya → pasang yang baru → jalankan lagi.

    Restart memakai explorer.exe agar tidak mewarisi env _MEIPASS.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-replace hanya tersedia pada build .exe")

    current = Path(sys.executable).resolve()
    workdir = current.parent
    source = downloaded.resolve()
    pid = os.getpid()
    proc_name = current.stem
    is_zip = source.suffix.lower() == ".zip"

    bat = Path(tempfile.gettempdir()) / f"network_tools_apply_update_{pid}.bat"
    err_log = Path(tempfile.gettempdir()) / "network_tools_update_error.txt"
    stage = Path(tempfile.gettempdir()) / f"network_tools_stage_{pid}"

    target = str(current)
    source_s = str(source)
    workdir_s = str(workdir)
    err_s = str(err_log)
    stage_s = str(stage)
    proc = f"{proc_name}.exe"

    def _fill(template: str) -> str:
        return (
            template.replace("__TARGET__", target)
            .replace("__SOURCE__", source_s)
            .replace("__WORKDIR__", workdir_s)
            .replace("__STAGE__", stage_s)
            .replace("__ERRLOG__", err_s)
            .replace("__PROC__", proc)
        )

    if is_zip:
        body = _fill(
            r"""@echo off
setlocal EnableExtensions
set "TARGET=__TARGET__"
set "SOURCE=__SOURCE__"
set "WORKDIR=__WORKDIR__"
set "STAGE=__STAGE__"
set "ERRLOG=__ERRLOG__"
set "PROC=__PROC__"

rem Bersihkan env PyInstaller
set "_MEIPASS="
set "_MEIPASS2="
set "PYTHONHOME="
set "PYTHONPATH="

:wait
tasklist /FI "IMAGENAME eq %PROC%" 2>nul | find /I "%PROC%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)

timeout /t 3 /nobreak >nul

if not exist "%SOURCE%" (
  echo Source hilang> "%ERRLOG%"
  exit /b 1
)

rem Hapus program lama di lokasi
del /F /Q "%TARGET%" >nul 2>&1
if exist "%WORKDIR%\_internal" rd /s /q "%WORKDIR%\_internal" >nul 2>&1
del /F /Q "%TARGET%.old" >nul 2>&1

rem Extract zip
if exist "%STAGE%" rd /s /q "%STAGE%" >nul 2>&1
mkdir "%STAGE%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%SOURCE%' -DestinationPath '%STAGE%' -Force"
if errorlevel 1 (
  echo Expand gagal> "%ERRLOG%"
  exit /b 2
)

rem Jika zip berisi folder NetworkTools\, angkat isinya
set "SRCROOT="
if exist "%STAGE%\NetworkTools\NetworkTools.exe" set "SRCROOT=%STAGE%\NetworkTools"
if not defined SRCROOT if exist "%STAGE%\NetworkTools.exe" set "SRCROOT=%STAGE%"
if not defined SRCROOT (
  echo Struktur zip tidak dikenali> "%ERRLOG%"
  exit /b 3
)

xcopy /E /Y /I /Q "%SRCROOT%\*" "%WORKDIR%\" >nul
if not exist "%TARGET%" (
  echo Copy gagal, EXE tidak ada> "%ERRLOG%"
  exit /b 4
)

timeout /t 2 /nobreak >nul

rem Jalankan lewat explorer (env bersih, di luar process tree)
explorer.exe "%TARGET%"

timeout /t 2 /nobreak >nul
rd /s /q "%STAGE%" >nul 2>&1
del /F /Q "%SOURCE%" >nul 2>&1
del "%~f0" >nul 2>&1
"""
        )
    else:
        body = _fill(
            r"""@echo off
setlocal EnableExtensions
set "TARGET=__TARGET__"
set "SOURCE=__SOURCE__"
set "WORKDIR=__WORKDIR__"
set "ERRLOG=__ERRLOG__"
set "PROC=__PROC__"

set "_MEIPASS="
set "_MEIPASS2="
set "PYTHONHOME="
set "PYTHONPATH="

:wait
tasklist /FI "IMAGENAME eq %PROC%" 2>nul | find /I "%PROC%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)

timeout /t 3 /nobreak >nul

if not exist "%SOURCE%" (
  echo Source hilang> "%ERRLOG%"
  exit /b 1
)

rem Hapus program lama
del /F /Q "%TARGET%" >nul 2>&1
if exist "%TARGET%" (
  timeout /t 2 /nobreak >nul
  del /F /Q "%TARGET%" >nul 2>&1
)
if exist "%TARGET%" (
  echo Gagal menghapus EXE lama> "%ERRLOG%"
  exit /b 2
)

copy /Y "%SOURCE%" "%TARGET%" >nul
if not exist "%TARGET%" (
  echo Copy gagal> "%ERRLOG%"
  exit /b 3
)

timeout /t 2 /nobreak >nul

explorer.exe "%TARGET%"

timeout /t 2 /nobreak >nul
del /F /Q "%SOURCE%" >nul 2>&1
del "%~f0" >nul 2>&1
"""
        )

    bat.write_text(body, encoding="utf-8")

    clean_env = _clean_environ()
    flags = 0
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    flags |= 0x01000000  # CREATE_BREAKAWAY_FROM_JOB

    # start /min agar jendela cmd tidak mengganggu; env bersih
    subprocess.Popen(
        ["cmd.exe", "/c", "start", "", "/min", str(bat)],
        cwd=str(workdir),
        env=clean_env,
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
