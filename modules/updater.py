"""Auto-update via GitHub Releases — single-file EXE."""

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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

GITHUB_REPO = "Jeriyant/NETWORK-TOOLS"
GITHUB_API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_REPO_URL = f"https://github.com/{GITHUB_REPO}"
USER_AGENT = "NetworkTools-Updater/1.4"

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
        mandatory=True,
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
    Pasang update cepat: hanya ganti file EXE lalu jalankan ulang.

    1. Salin ke ``NetworkTools.exe.new`` selagi app masih jalan.
    2. Setelah PID keluar: rename exe→.old, .new→exe, hapus .old.
    3. Start ulang ``NetworkTools.exe`` otomatis.
    """
    if not getattr(sys, "frozen", False):
        raise RuntimeError("Auto-replace hanya tersedia pada build .exe")

    current = Path(sys.executable).resolve()
    source = downloaded_exe.resolve()
    workdir = current.parent
    staged = current.with_name(current.name + ".new")  # NetworkTools.exe.new
    pid = os.getpid()
    err_log = Path(tempfile.gettempdir()) / "network_tools_update_error.txt"
    ok_log = Path(tempfile.gettempdir()) / "network_tools_update_ok.txt"

    try:
        if staged.is_file():
            staged.unlink(missing_ok=True)
    except Exception:
        pass
    try:
        shutil.copy2(source, staged)
    except Exception as exc:
        raise RuntimeError(f"Gagal menyiapkan file update (.new): {exc}") from exc

    if not staged.is_file() or staged.stat().st_size != source.stat().st_size:
        raise RuntimeError("File .new tidak valid setelah disalin.")

    verify_exe_file(staged)

    bat = Path(tempfile.gettempdir()) / f"network_tools_apply_update_{pid}.cmd"
    vbs = Path(tempfile.gettempdir()) / f"network_tools_apply_update_{pid}.vbs"
    # Hanya ganti EXE secepat mungkin (tanpa jeda panjang / tanpa hapus runtime).
    script = f"""@echo off
setlocal EnableExtensions
set "TARGET={current}"
set "STAGED={staged}"
set "ERRLOG={err_log}"
set "OKLOG={ok_log}"
set "OLDPID={pid}"
set "TEMPSRC={source}"

del /F /Q "%ERRLOG%" >nul 2>&1
del /F /Q "%OKLOG%" >nul 2>&1

set /a TRIES=0
:waitpid
tasklist /FI "PID eq %OLDPID%" 2>nul | findstr /R /C:" %OLDPID% " >nul
if errorlevel 1 goto swap
set /a TRIES+=1
if %TRIES% GEQ 200 (
  echo Timeout menunggu PID %OLDPID% keluar.> "%ERRLOG%"
  exit /b 1
)
goto waitpid

:swap
if not exist "%STAGED%" (
  echo File staged hilang: %STAGED%> "%ERRLOG%"
  exit /b 2
)

set /a TRIES=0
:trymove
if exist "%TARGET%.old" del /F /Q "%TARGET%.old" >nul 2>&1
if not exist "%TARGET%" goto do_rename
move /Y "%TARGET%" "%TARGET%.old" >nul 2>&1
if exist "%TARGET%.old" if not exist "%TARGET%" goto do_rename
set /a TRIES+=1
if %TRIES% GEQ 100 (
  echo Tidak bisa me-rename EXE lama.> "%ERRLOG%"
  exit /b 3
)
goto trymove

:do_rename
move /Y "%STAGED%" "%TARGET%" >nul 2>&1
if not exist "%TARGET%" (
  if exist "%TARGET%.old" move /Y "%TARGET%.old" "%TARGET%" >nul 2>&1
  echo Gagal rename .new ke EXE.> "%ERRLOG%"
  exit /b 4
)

del /F /Q "%TEMPSRC%" >nul 2>&1
del /F /Q "%TARGET%.old" >nul 2>&1
echo OK> "%OKLOG%"

rem Tunggu 5 detik agar handle file lepas, lalu jalankan ulang app
timeout /t 5 /nobreak >nul 2>&1
start "" "%TARGET%"

del /F /Q "{vbs}" >nul 2>&1
del /F /Q "%~f0" >nul 2>&1
"""
    bat.write_text(script, encoding="utf-8")

    # VBS Run ..., 0 = jendela tersembunyi (mencegah spam CMD dari child process)
    bat_path = str(bat)
    vbs.write_text(
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.Run "cmd.exe /d /c ""{bat_path}""", 0, False\r\n',
        encoding="ascii",
        errors="replace",
    )

    no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    flags = no_window
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    flags |= 0x01000000  # CREATE_BREAKAWAY_FROM_JOB

    launched = False
    try:
        subprocess.Popen(
            ["wscript.exe", "//B", "//Nologo", str(vbs)],
            cwd=str(workdir),
            env=_clean_environ(),
            creationflags=flags,
            close_fds=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        launched = True
    except Exception:
        launched = False

    if not launched:
        try:
            import ctypes

            rc = int(
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "open",
                    "wscript.exe",
                    f'//B //Nologo "{vbs}"',
                    str(workdir),
                    0,  # SW_HIDE
                )
            )
            launched = rc > 32
        except Exception:
            launched = False

    if not launched:
        # Cadangan terakhir: cmd tersembunyi langsung
        try:
            subprocess.Popen(
                ["cmd.exe", "/d", "/c", str(bat)],
                cwd=str(workdir),
                env=_clean_environ(),
                creationflags=flags,
                close_fds=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            launched = True
        except Exception:
            launched = False

    if not launched:
        raise RuntimeError("Gagal menjalankan skrip update.")


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

    # Bersihkan folder _MEI* yang rusak (tanpa python312.dll) — jangan sentuh _MEIPASS aktif
    try:
        runtime = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            / "NetworkTools"
            / "runtime"
        )
        if not runtime.is_dir():
            return
        active = ""
        try:
            active = str(Path(getattr(sys, "_MEIPASS", "")).resolve()).lower()
        except Exception:
            active = ""
        for child in runtime.iterdir():
            if not child.is_dir() or not child.name.startswith("_MEI"):
                continue
            try:
                if active and str(child.resolve()).lower() == active:
                    continue
            except Exception:
                pass
            dll = child / "python312.dll"
            # Folder kosong / rusak (DLL hilang) → aman dihapus
            if not dll.is_file():
                try:
                    shutil.rmtree(child, ignore_errors=True)
                except Exception:
                    pass
    except Exception:
        pass


def current_executable_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return Path(__file__).resolve()
