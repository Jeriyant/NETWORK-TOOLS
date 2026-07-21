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


# --- UI automation: deep link t.me → Telegram Desktop → Ctrl+V → Send ---

def _telegram_group_url() -> str:
    try:
        from modules.settings import TELEGRAM_GROUP_URL

        return str(TELEGRAM_GROUP_URL or "https://t.me/cusjnetmonitor").strip()
    except Exception:
        return "https://t.me/cusjnetmonitor"


def _telegram_group_name() -> str:
    try:
        from modules.settings import TELEGRAM_GROUP

        return str(TELEGRAM_GROUP or "Monitoring jaringan")
    except Exception:
        return "Monitoring jaringan"


def _tg_protocol_url(https_url: str) -> str:
    """https://t.me/name → tg://resolve?domain=name (paksa buka Desktop)."""
    raw = (https_url or "").strip().rstrip("/")
    if raw.lower().startswith("tg://"):
        return raw
    marker = "t.me/"
    idx = raw.lower().find(marker)
    if idx < 0:
        return raw
    path = raw[idx + len(marker) :].split("?")[0].strip("/")
    if not path:
        return raw
    if path.startswith("+"):
        return f"tg://join?invite={path[1:]}"
    if path.lower().startswith("joinchat/"):
        return f"tg://join?invite={path.split('/', 1)[1]}"
    domain = path.split("/")[0]
    return f"tg://resolve?domain={domain}"


def _telegram_pids() -> list[int]:
    """PID proses Telegram.exe yang sedang jalan."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    pids: list[int] = []
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Telegram.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=15,
        )
        for line in (completed.stdout or "").splitlines():
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == "telegram.exe":
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
    except Exception:
        pass
    return pids


def _find_telegram_hwnd() -> int:
    """Cari HWND milik proses Telegram.exe (judul bisa nama chat, bukan 'Telegram')."""
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    pids = set(_telegram_pids())
    if not pids:
        return 0

    found: list[int] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, wintypes.HWND, wintypes.LPARAM
    )
    get_pid = wintypes.DWORD()

    def _cb(hwnd: int, _lp: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        if w < 200 or h < 200:
            return True
        get_pid.value = 0
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(get_pid))
        if int(get_pid.value) in pids:
            found.append(int(hwnd))
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(_cb), 0)
    return found[0] if found else 0


def _window_title(hwnd: int) -> str:
    if not hwnd or os.name != "nt":
        return ""
    import ctypes

    user32 = ctypes.windll.user32
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return (buf.value or "").strip()


def _is_group_already_open(hwnd: int, group_name: str) -> bool:
    """True jika judul jendela Telegram sudah menampilkan nama grup (chat aktif)."""
    title = _window_title(hwnd).lower()
    name = (group_name or "").strip().lower()
    if not title or not name:
        return False
    # Juga cocokkan slug dari URL (cusjnetmonitor) bila judul memakai itu
    return name in title


def _activate_hwnd(hwnd: int) -> bool:
    """Paksa foreground (AttachThreadInput — SetForegroundWindow sering gagal dari Tk)."""
    if not hwnd:
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    SW_RESTORE = 9
    try:
        try:
            user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:
            pass
        fg = user32.GetForegroundWindow()
        pid_fg = wintypes.DWORD()
        pid_tg = wintypes.DWORD()
        tid_fg = user32.GetWindowThreadProcessId(fg, ctypes.byref(pid_fg))
        tid_tg = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_tg))
        tid_cur = kernel32.GetCurrentThreadId()
        attached = False
        if tid_fg and tid_fg != tid_cur:
            attached = bool(user32.AttachThreadInput(tid_cur, tid_fg, True))
        if tid_tg and tid_tg != tid_cur and tid_tg != tid_fg:
            user32.AttachThreadInput(tid_cur, tid_tg, True)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetActiveWindow(hwnd)
        if attached:
            user32.AttachThreadInput(tid_cur, tid_fg, False)
        if tid_tg and tid_tg != tid_cur and tid_tg != tid_fg:
            user32.AttachThreadInput(tid_cur, tid_tg, False)
        return True
    except Exception:
        try:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False


def _release_our_focus(root: Any | None) -> None:
    """Lepas Always-on-Top / fokus Network Tools agar Telegram bisa dikontrol."""
    if root is None:
        return
    try:
        root.attributes("-topmost", False)
    except Exception:
        pass
    try:
        root.lower()
    except Exception:
        pass
    try:
        root.update_idletasks()
    except Exception:
        pass


def _click_point(x: int, y: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP


def _click_compose_area(hwnd: int) -> bool:
    """Klik kotak pesan (bawah tengah) agar fokus input sebelum paste."""
    if not hwnd or os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w < 100 or h < 100:
        return False
    # Beberapa titik: input biasanya kiri tombol Send
    points = (
        (rect.left + int(w * 0.55), rect.bottom - 48),
        (rect.left + int(w * 0.45), rect.bottom - 42),
        (rect.left + int(w * 0.65), rect.bottom - 55),
    )
    for x, y in points:
        _click_point(x, y)
        return True
    return False


def _click_telegram_send_button(hwnd: int) -> bool:
    """Klik area tombol Send (pojok kanan-bawah jendela Telegram)."""
    if not hwnd or os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    points = (
        (rect.right - 44, rect.bottom - 46),
        (rect.right - 60, rect.bottom - 52),
        (rect.right - 36, rect.bottom - 40),
        (rect.right - 50, rect.bottom - 70),  # media preview Send
    )
    for x, y in points:
        if x <= rect.left or y <= rect.top:
            continue
        _click_point(x, y)
        return True
    return False


def _key_chord(*vk_codes: int) -> None:
    """Tekan kombinasi tombol via keybd_event (lebih andal dari VBS SendKeys)."""
    import ctypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    for vk in vk_codes:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vk_codes):
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _send_ctrl_v() -> None:
    VK_CONTROL = 0x11
    VK_V = 0x56
    _key_chord(VK_CONTROL, VK_V)


def _send_enter_key() -> None:
    VK_RETURN = 0x0D
    _key_chord(VK_RETURN)


def open_telegram_group_link(
    url: str = "",
    telegram_exe: str = "",
) -> bool:
    """Buka chat grup via deep link; reuse instance yang sudah jalan (ShellExecute)."""
    https_url = (url or _telegram_group_url()).strip() or "https://t.me/cusjnetmonitor"
    tg_url = _tg_protocol_url(https_url)
    telegram = _find_telegram(telegram_exe)

    # 1) ShellExecute tg:// — pakai instance Telegram yang sudah terbuka
    if os.name == "nt":
        import ctypes

        for link in (tg_url, https_url):
            try:
                rc = int(ctypes.windll.shell32.ShellExecuteW(None, "open", link, None, None, 1))
                if rc > 32:
                    return True
            except Exception:
                pass

    # 2) Telegram.exe + link (cold start)
    if telegram:
        for link in (https_url, tg_url):
            try:
                subprocess.Popen([telegram, "--", link], shell=False)
                return True
            except Exception:
                try:
                    subprocess.Popen([telegram, link], shell=False)
                    return True
                except Exception:
                    pass

    if os.name == "nt":
        try:
            os.startfile(https_url)  # type: ignore[attr-defined]
            return True
        except Exception:
            pass
    return False


def _paste_and_send_keys(hwnd: int) -> None:
    """Fokus chat → klik input → Ctrl+V → Send (tanpa ESC — ESC menutup chat!)."""
    import time

    if hwnd:
        _activate_hwnd(hwnd)
        time.sleep(0.15)
        _click_compose_area(hwnd)
        time.sleep(0.12)
    _send_ctrl_v()
    # Gambar butuh waktu muncul di preview / caption
    time.sleep(0.45)
    if hwnd:
        _click_telegram_send_button(hwnd)
        time.sleep(0.15)
    _send_enter_key()
    time.sleep(0.12)
    # Cadangan kedua Enter (beberapa build TG butuh Enter di caption)
    _send_enter_key()


def paste_and_send_to_telegram_group(
    group_name: str = "",
    telegram_exe: str = "",
    *,
    settle_sec: float = 0.55,
    root: Any | None = None,
    group_url: str = "",
    clipboard_refresh: Any | None = None,
) -> tuple[bool, str]:
    """
    Alur:
      - Jika grup sudah terbuka: fokus → paste → Send (jangan buka link / ESC).
      - Jika belum: buka t.me / tg:// → tunggu → paste → Send.
    """
    import time

    if os.name != "nt":
        return False, "Otomasi Telegram hanya di Windows."

    url = (group_url or _telegram_group_url()).strip()
    label = (group_name or _telegram_group_name()).strip() or url
    # Slug dari URL untuk deteksi judul (kadang judul = username)
    slug = ""
    try:
        slug = url.rstrip("/").split("/")[-1].split("?")[0].lstrip("+")
    except Exception:
        pass

    _release_our_focus(root)

    was_running = bool(_telegram_pids())
    hwnd0 = _find_telegram_hwnd() if was_running else 0
    already = bool(
        hwnd0
        and (
            _is_group_already_open(hwnd0, label)
            or (slug and _is_group_already_open(hwnd0, slug))
        )
    )

    if already:
        # Jangan buka ulang deep link / ESC — cukup fokus + paste
        _activate_hwnd(hwnd0)
        time.sleep(0.2)
    else:
        if not open_telegram_group_link(url, telegram_exe=telegram_exe):
            if not open_telegram(telegram_exe, background=False):
                return False, "Telegram Desktop tidak ditemukan / link gagal dibuka."

        pids: list[int] = []
        wait_loops = 30 if not was_running else 16
        for _ in range(wait_loops):
            time.sleep(0.12)
            pids = _telegram_pids()
            if pids:
                break
        if not pids:
            return False, "Proses Telegram.exe tidak ditemukan."

        time.sleep(1.25 if not was_running else max(0.55, settle_sec))

    # Refresh clipboard tepat sebelum paste (link/fokus bisa mengganggu timing)
    if callable(clipboard_refresh):
        try:
            clipboard_refresh()
        except Exception:
            pass
        time.sleep(0.08)

    _release_our_focus(root)
    hwnd = _find_telegram_hwnd() or hwnd0
    if not hwnd:
        return False, "Jendela Telegram tidak ditemukan."

    _paste_and_send_keys(hwnd)

    mode = "chat aktif" if already else f"via {url}"
    return True, f'Kirim ke "{label}" ({mode}).'


def send_via_telegram(
    screenshot: Path,
    telegram_exe: str = "",
    root: Any | None = None,
) -> tuple[bool, list[str]]:
    """Copy screenshot, buka deep link grup → paste & kirim."""
    tips: list[str] = []

    def _refresh() -> bool:
        return copy_image_to_clipboard(screenshot) or copy_image_powershell(screenshot)

    copied = _refresh()
    if copied:
        tips.append("Gambar sudah di clipboard.")
    else:
        tips.append(f"Clipboard gagal. File tersimpan: {screenshot}")
        return copied, tips

    ok, msg = paste_and_send_to_telegram_group(
        telegram_exe=telegram_exe,
        root=root,
        clipboard_refresh=_refresh,
    )
    tips.append(msg if ok else f"Otomasi gagal: {msg}. Tempel manual (Ctrl+V).")
    if not ok:
        open_telegram_group_link(telegram_exe=telegram_exe)
    return copied, tips


def send_text_via_telegram(
    text: str,
    telegram_exe: str = "",
    root: Any | None = None,
) -> tuple[bool, list[str]]:
    """Copy plain text, buka deep link grup → paste & kirim."""
    tips: list[str] = []
    payload = text or ""

    def _refresh() -> bool:
        return copy_text_to_clipboard(payload, root=root)

    copied = _refresh()
    if copied:
        tips.append("Teks sudah di clipboard.")
    else:
        tips.append("Gagal menyalin teks ke clipboard.")
        return copied, tips

    ok, msg = paste_and_send_to_telegram_group(
        telegram_exe=telegram_exe,
        root=root,
        clipboard_refresh=_refresh,
    )
    tips.append(msg if ok else f"Otomasi gagal: {msg}. Tempel manual (Ctrl+V).")
    if not ok:
        open_telegram_group_link(telegram_exe=telegram_exe)
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
    root: Any | None = None,
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
        def _refresh() -> bool:
            return copy_file_to_clipboard(path)

        ok, msg = paste_and_send_to_telegram_group(
            telegram_exe=telegram_exe,
            root=root,
            clipboard_refresh=_refresh,
        )
        tips.append(msg if ok else f"Otomasi gagal: {msg}. Tempel file manual (Ctrl+V).")
    elif telegram:
        open_telegram_group_link(telegram_exe=telegram_exe)
        tips.append("Buka chat Telegram, lalu tempel (Ctrl+V) untuk kirim file.")
    elif not copied:
        tips.append("Telegram tidak ditemukan.")
    else:
        tips.append("Telegram tidak ditemukan. File tetap di clipboard.")

    return copied, tips, path
