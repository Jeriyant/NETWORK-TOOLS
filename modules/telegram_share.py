"""Screenshot capture and Telegram launch helpers."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageGrab


def capture_window_region(left: int, top: int, width: int, height: int) -> Path:
    """Capture a screen region and save as PNG in temp folder."""
    bbox = (left, top, left + width, top + height)
    image = ImageGrab.grab(bbox=bbox, all_screens=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = Path(tempfile.gettempdir()) / f"network_tools_{stamp}.png"
    image.save(out, "PNG")
    return out


def _find_telegram(configured: str = "") -> str | None:
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))

    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    for base in (local, appdata, program_files, program_files_x86):
        if not base:
            continue
        candidates.extend(
            [
                Path(base) / "Telegram Desktop" / "Telegram.exe",
                Path(base) / "Telegram" / "Telegram.exe",
            ]
        )

    which = shutil.which("Telegram.exe")
    if which:
        candidates.append(Path(which))

    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def copy_image_to_clipboard(path: Path) -> bool:
    """Copy PNG as CF_DIB bitmap so Ctrl+V pastes the image in Telegram."""
    try:
        import ctypes

        image = Image.open(path).convert("RGB")
        with io.BytesIO() as buf:
            image.save(buf, "BMP")
            bmp_data = buf.getvalue()[14:]  # strip BITMAPFILEHEADER → CF_DIB

        CF_DIB = 8
        GMEM_MOVEABLE = 0x0002

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.EmptyClipboard.restype = ctypes.c_int
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.restype = ctypes.c_int

        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(bmp_data))
        if not h_global:
            return False
        ptr = kernel32.GlobalLock(h_global)
        if not ptr:
            kernel32.GlobalFree(h_global)
            return False
        ctypes.memmove(ptr, bmp_data, len(bmp_data))
        kernel32.GlobalUnlock(h_global)

        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(h_global)
            return False
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_DIB, h_global):
                kernel32.GlobalFree(h_global)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


def copy_image_powershell(path: Path) -> bool:
    """Fallback: System.Windows.Forms clipboard image."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Escape single quotes for PowerShell single-quoted string
    safe = str(path).replace("'", "''")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$img = [System.Drawing.Image]::FromFile('{safe}'); "
        "[System.Windows.Forms.Clipboard]::SetImage($img); "
        "$img.Dispose();"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            creationflags=creation,
        )
        return completed.returncode == 0
    except Exception:
        return False


def copy_text_to_clipboard(text: str) -> bool:
    """Copy plain text (AnyDesk ID, etc.) to Windows clipboard."""
    try:
        import ctypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32

        data = (text or "").encode("utf-16-le") + b"\x00\x00"
        h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not h_global:
            return False
        locked = kernel32.GlobalLock(h_global)
        if not locked:
            kernel32.GlobalFree(h_global)
            return False
        ctypes.memmove(locked, data, len(data))
        kernel32.GlobalUnlock(h_global)

        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(h_global)
            return False
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
                kernel32.GlobalFree(h_global)
                return False
            # Ownership transferred to clipboard on success
            h_global = None
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


def open_telegram(telegram_exe: str = "") -> bool:
    """Launch Telegram Desktop if installed."""
    telegram = _find_telegram(telegram_exe)
    if not telegram:
        return False
    try:
        subprocess.Popen([telegram], shell=False)
        return True
    except Exception:
        return False


def send_via_telegram(
    screenshot: Path,
    telegram_exe: str = "",
) -> tuple[bool, list[str]]:
    """Copy screenshot, open Telegram. Returns (ok, instruction_lines)."""
    tips: list[str] = []

    copied = copy_image_to_clipboard(screenshot)
    if not copied:
        copied = copy_image_powershell(screenshot)

    if copied:
        tips.append("Gambar sudah di clipboard.")
    else:
        tips.append(f"Clipboard gagal. File tersimpan: {screenshot}")

    telegram = _find_telegram(telegram_exe)
    if telegram:
        subprocess.Popen([telegram], shell=False)
        tips.append("Buka chat Telegram, lalu tempel dengan Ctrl+V atau Paste.")
    else:
        subprocess.Popen(["explorer", "/select,", str(screenshot)])
        tips.append(
            "Telegram tidak ditemukan. Folder screenshot dibuka."
        )

    return copied, tips


def send_text_via_telegram(
    text: str,
    telegram_exe: str = "",
) -> tuple[bool, list[str]]:
    """Copy plain text to clipboard and open Telegram."""
    tips: list[str] = []
    copied = copy_text_to_clipboard(text or "")
    if copied:
        tips.append("Teks daftar sudah di clipboard.")
    else:
        tips.append("Gagal menyalin teks ke clipboard.")

    telegram = _find_telegram(telegram_exe)
    if telegram:
        subprocess.Popen([telegram], shell=False)
        tips.append("Buka chat Telegram, lalu tempel dengan Ctrl+V atau Paste.")
    else:
        tips.append("Telegram tidak ditemukan. Teks tetap di clipboard (jika berhasil).")

    return copied, tips
