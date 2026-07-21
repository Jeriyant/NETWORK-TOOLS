"""Screenshot capture and Telegram launch helpers."""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

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


def copy_text_to_clipboard(text: str, root: Any | None = None) -> bool:
    """Copy plain text to Windows clipboard (Tk → Win32 → PowerShell)."""
    payload = text or ""
    if not payload:
        return False

    # 1) Tkinter clipboard — paling andal saat app Tk masih hidup
    if root is not None:
        try:
            root.clipboard_clear()
            root.clipboard_append(payload)
            root.update_idletasks()
            # Pastikan isi masih ada
            try:
                got = root.clipboard_get()
                if got == payload or (got and len(got) == len(payload)):
                    return True
            except Exception:
                return True  # append sukses, get kadang gagal di beberapa theme
        except Exception:
            pass

    # 2) Win32 CF_UNICODETEXT + retry OpenClipboard
    try:
        import ctypes
        from ctypes import wintypes

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.restype = wintypes.BOOL
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

        data = payload.encode("utf-16-le") + b"\x00\x00"
        opened = False
        for _ in range(20):
            if user32.OpenClipboard(None):
                opened = True
                break
            try:
                import time

                time.sleep(0.05)
            except Exception:
                pass
        if not opened:
            raise OSError("OpenClipboard failed")

        try:
            user32.EmptyClipboard()
            h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
            if not h_global:
                return False
            locked = kernel32.GlobalLock(h_global)
            if not locked:
                kernel32.GlobalFree(h_global)
                return False
            ctypes.memmove(locked, data, len(data))
            kernel32.GlobalUnlock(h_global)
            if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
                kernel32.GlobalFree(h_global)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        pass

    # 3) PowerShell Set-Clipboard (file temp — aman untuk teks panjang)
    return copy_text_powershell(payload)


def copy_text_powershell(text: str) -> bool:
    """Fallback: Set-Clipboard via PowerShell using a UTF-8 temp file."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        tmp = Path(tempfile.gettempdir()) / "network_tools_clipboard.txt"
        tmp.write_text(text or "", encoding="utf-8")
        safe = str(tmp).replace("'", "''")
        ps = (
            f"$t = Get-Content -LiteralPath '{safe}' -Raw -Encoding UTF8; "
            "Set-Clipboard -Value $t"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            creationflags=creation,
            timeout=30,
        )
        return completed.returncode == 0
    except Exception:
        return False


def open_telegram(telegram_exe: str = "", *, background: bool = False) -> bool:
    """Launch Telegram Desktop if installed.

    background=True → buka tanpa mencuri fokus (minimized / no-activate).
    """
    telegram = _find_telegram(telegram_exe)
    if not telegram:
        return False
    try:
        if background and os.name == "nt":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7  # SW_SHOWMINNOACTIVE
            subprocess.Popen([telegram], shell=False, startupinfo=si)
        else:
            subprocess.Popen([telegram], shell=False)
        return True
    except Exception:
        return False


# --- UI automation ala AutoHotkey (Windows) ---

def _telegram_group_name() -> str:
    try:
        from modules.settings import TELEGRAM_GROUP

        return str(TELEGRAM_GROUP or "Monitoring jaringan")
    except Exception:
        return "Monitoring jaringan"


def _find_telegram_hwnd() -> int:
    """Cari HWND jendela utama Telegram Desktop."""
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )

    def _cb(hwnd: int, _lp: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").strip()
        # Telegram Desktop: judul biasanya "Telegram" atau nama chat
        if title.lower() == "telegram" or title.startswith("Telegram"):
            found.append(int(hwnd))
            return False
        # Juga cocokkan class Qt*
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        cname = (cls.value or "").lower()
        if "telegram" in cname and "qt" in cname:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    if found:
        return found[0]

    # Fallback: proses Telegram.exe → EnumWindows lagi longgar
    def _cb2(hwnd: int, _lp: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length < 1:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = (buf.value or "").lower()
        if "telegram" in title:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(_cb2), 0)
    return found[0] if found else 0


def _activate_hwnd(hwnd: int) -> bool:
    if not hwnd:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    try:
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def _send_vk(vk: int, *, ctrl: bool = False, shift: bool = False, alt: bool = False) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_CONTROL, VK_SHIFT, VK_MENU = 0x11, 0x10, 0x12

    if ctrl:
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
    if shift:
        user32.keybd_event(VK_SHIFT, 0, 0, 0)
    if alt:
        user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    if alt:
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    if shift:
        user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)
    if ctrl:
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def _send_text_keys(text: str) -> None:
    """Ketik teks (ASCII/Latin) via VkKeyScanW + keybd_event."""
    import ctypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_SHIFT = 0x10
    for ch in text:
        if ch == "\n":
            _send_vk(0x0D)
            continue
        scanned = user32.VkKeyScanW(ord(ch))
        if scanned == -1 or scanned == 0xFFFF:
            continue
        vk = scanned & 0xFF
        need_shift = bool(scanned & 0x100)
        if need_shift:
            user32.keybd_event(VK_SHIFT, 0, 0, 0)
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        if need_shift:
            user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)


def _click_hwnd_bottom(hwnd: int, *, right: bool = False) -> bool:
    """Klik kiri/kanan di area input pesan (bawah jendela)."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    x = (rect.left + rect.right) // 2
    y = max(rect.top + 80, rect.bottom - 52)
    user32.SetCursorPos(x, y)
    if right:
        down, up = 0x0008, 0x0010  # RIGHTDOWN / RIGHTUP
    else:
        down, up = 0x0002, 0x0004  # LEFTDOWN / LEFTUP
    user32.mouse_event(down, 0, 0, 0, 0)
    user32.mouse_event(up, 0, 0, 0, 0)
    return True


def paste_and_send_to_telegram_group(
    group_name: str = "",
    telegram_exe: str = "",
    *,
    settle_sec: float = 1.2,
) -> tuple[bool, str]:
    """
    Seperti AutoHotkey:
    1. Buka/aktifkan Telegram
    2. Cari grup (Ctrl+K) → Enter
    3. Klik kanan di kotak pesan → Paste (Tempel) / Ctrl+V
    4. Enter untuk kirim
    """
    import time

    if os.name != "nt":
        return False, "Otomasi Telegram hanya di Windows."

    name = (group_name or _telegram_group_name()).strip() or "Monitoring jaringan"
    opened = open_telegram(telegram_exe, background=False)
    if not opened:
        return False, "Telegram Desktop tidak ditemukan."

    time.sleep(max(0.8, settle_sec))
    hwnd = 0
    for _ in range(20):
        hwnd = _find_telegram_hwnd()
        if hwnd:
            break
        time.sleep(0.25)
    if not hwnd:
        return False, "Jendela Telegram tidak ditemukan."

    _activate_hwnd(hwnd)
    time.sleep(0.4)

    VK_RETURN = 0x0D
    VK_ESCAPE = 0x1B
    ord_k = 0x4B
    ord_v = 0x56
    ord_t = 0x54  # Tempel

    _send_vk(VK_ESCAPE)
    time.sleep(0.2)

    # Quick Switcher: Ctrl+K → ketik nama grup → Enter
    _send_vk(ord_k, ctrl=True)
    time.sleep(0.5)
    _send_text_keys(name)
    time.sleep(0.75)
    _send_vk(VK_RETURN)
    time.sleep(1.0)

    _activate_hwnd(hwnd)
    time.sleep(0.3)

    # Fokus kotak pesan
    _click_hwnd_bottom(hwnd, right=False)
    time.sleep(0.25)

    # Klik kanan → Tempel (locale ID); cadangan Ctrl+V
    _click_hwnd_bottom(hwnd, right=True)
    time.sleep(0.4)
    _send_vk(ord_t)
    time.sleep(0.35)
    # Cadangan andal
    _send_vk(VK_ESCAPE)
    time.sleep(0.1)
    _send_vk(ord_v, ctrl=True)
    time.sleep(0.35)

    # Kirim
    _send_vk(VK_RETURN)
    time.sleep(0.25)

    return True, f'Grup "{name}" dibuka; ditempel & dikirim.'


def send_via_telegram(
    screenshot: Path,
    telegram_exe: str = "",
) -> tuple[bool, list[str]]:
    """Copy screenshot, buka Telegram → grup Monitoring jaringan → paste & kirim."""
    tips: list[str] = []

    copied = copy_image_to_clipboard(screenshot)
    if not copied:
        copied = copy_image_powershell(screenshot)

    if copied:
        tips.append("Gambar sudah di clipboard.")
    else:
        tips.append(f"Clipboard gagal. File tersimpan: {screenshot}")
        return copied, tips

    ok, msg = paste_and_send_to_telegram_group(telegram_exe=telegram_exe)
    tips.append(msg if ok else f"Otomasi gagal: {msg}. Tempel manual (Ctrl+V).")
    if not ok:
        open_telegram(telegram_exe)
    return copied, tips


def send_text_via_telegram(
    text: str,
    telegram_exe: str = "",
    root: Any | None = None,
) -> tuple[bool, list[str]]:
    """Copy plain text, buka grup Telegram, paste & kirim otomatis."""
    tips: list[str] = []
    copied = copy_text_to_clipboard(text or "", root=root)
    if copied:
        tips.append("Teks sudah di clipboard.")
    else:
        tips.append("Gagal menyalin teks ke clipboard.")
        return copied, tips

    ok, msg = paste_and_send_to_telegram_group(telegram_exe=telegram_exe)
    tips.append(msg if ok else f"Otomasi gagal: {msg}. Tempel manual (Ctrl+V).")
    if not ok:
        open_telegram(telegram_exe)
    return copied, tips


def _desktop_or_docs() -> Path:
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        return desktop
    docs = Path.home() / "Documents"
    if docs.is_dir():
        return docs
    return Path(tempfile.gettempdir())


def write_apps_list_file(text: str, filename: str = "Daftar_Aplikasi.txt") -> Path:
    """Tulis daftar aplikasi ke file .txt (Desktop bila ada)."""
    dest = _desktop_or_docs() / filename
    dest.write_text(text or "", encoding="utf-8")
    return dest


def copy_file_to_clipboard(path: Path) -> bool:
    """Salin file ke clipboard sebagai file drop (Ctrl+V menempel file, bukan teks)."""
    path = Path(path).resolve()
    if not path.is_file():
        return False

    # PowerShell Set-Clipboard -Path → CF_HDROP (bisa paste ke Telegram)
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    safe = str(path).replace("'", "''")
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"Set-Clipboard -Path '{safe}'",
            ],
            capture_output=True,
            text=True,
            creationflags=creation,
            timeout=20,
        )
        if completed.returncode == 0:
            return True
    except Exception:
        pass

    # Fallback: System.Windows.Forms FileDropList
    try:
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            f"$c = New-Object System.Collections.Specialized.StringCollection; "
            f"$c.Add('{safe}') | Out-Null; "
            "[System.Windows.Forms.Clipboard]::SetFileDropList($c)"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            creationflags=creation,
            timeout=20,
        )
        return completed.returncode == 0
    except Exception:
        return False


def send_apps_file_via_telegram(
    text: str,
    telegram_exe: str = "",
    filename: str = "Daftar_Aplikasi.txt",
) -> tuple[bool, list[str], Path | None]:
    """
    Buat Daftar_Aplikasi.txt, salin FILE ke clipboard, buka Telegram.
    Paste di chat akan mengirim file (bukan teks biasa).
    """
    tips: list[str] = []
    try:
        path = write_apps_list_file(text, filename=filename)
    except Exception as exc:
        tips.append(f"Gagal membuat file: {exc}")
        return False, tips, None

    copied = copy_file_to_clipboard(path)
    if copied:
        tips.append(f"File dibuat: {path}")
        tips.append("File sudah di clipboard (bukan teks).")
    else:
        tips.append(f"File dibuat: {path}")
        tips.append("Gagal menyalin file ke clipboard — tempel manual dari folder.")
        try:
            subprocess.Popen(["explorer", "/select,", str(path)])
        except Exception:
            pass

    telegram = _find_telegram(telegram_exe)
    if telegram and copied:
        ok, msg = paste_and_send_to_telegram_group(telegram_exe=telegram_exe)
        tips.append(msg if ok else f"Otomasi gagal: {msg}. Tempel file manual (Ctrl+V).")
    elif telegram:
        subprocess.Popen([telegram], shell=False)
        tips.append("Buka chat Telegram, lalu tempel (Ctrl+V) untuk kirim file.")
    elif not copied:
        tips.append("Telegram tidak ditemukan.")
    else:
        tips.append("Telegram tidak ditemukan. File tetap di clipboard.")

    return copied, tips, path
