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


# --- UI automation ala AutoHotkey (Windows / WScript.Shell SendKeys) ---

_PASSCODE_HINTS = (
    "local passcode",
    "passcode",
    "enter a passcode",
    "enter your passcode",
    "kode sandi",
    "kode lokal",
    "masukkan kode",
    "unlock telegram",
)
_LOGIN_HINTS = (
    "log in by phone",
    "log in to telegram",
    "qr code",
    "scan qr",
    "your phone number",
    "phone number",
    "nomor telepon",
    "start messaging",
    "masuk dengan",
    "kode qr",
)
_READY_HINTS = (
    "saved messages",
    "archived chats",
    "search",
    "chats",
    "new message",
    "pesan tersimpan",
    "obrolan",
    "cari",
)


def _telegram_group_name() -> str:
    try:
        from modules.settings import TELEGRAM_GROUP

        return str(TELEGRAM_GROUP or "Monitoring jaringan")
    except Exception:
        return "Monitoring jaringan"


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
            # "Telegram.exe","1234","Session Name","Session#","Mem Usage"
            parts = [p.strip().strip('"') for p in line.split(",")]
            if len(parts) >= 2 and parts[0].lower() == "telegram.exe":
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
    except Exception:
        pass
    return pids


def _close_telegram() -> None:
    """Tutup semua proses Telegram.exe (agar chat terbuka tidak mengganggu otomasi)."""
    import time

    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "Telegram.exe", "/T"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=20,
        )
    except Exception:
        pass
    for _ in range(25):
        if not _telegram_pids():
            break
        time.sleep(0.12)
    time.sleep(0.25)


def _tdata_suggests_session() -> bool:
    """True jika folder tdata mengisyaratkan sudah pernah login."""
    appdata = os.environ.get("APPDATA", "")
    if not appdata:
        return False
    tdata = Path(appdata) / "Telegram Desktop" / "tdata"
    if not tdata.is_dir():
        return False
    try:
        if (tdata / "key_datas").is_file():
            return True
        for child in tdata.iterdir():
            name = child.name.lower()
            if child.is_dir() and len(name) >= 16 and name.isalnum():
                return True
            if name.startswith("map") or name == "settingss":
                return True
    except Exception:
        return False
    return False


def _collect_telegram_ui_text(max_chars: int = 8000) -> str:
    """Ambil teks UI jendela Telegram via UI Automation (untuk cek login/passcode)."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ps = r"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient | Out-Null
Add-Type -AssemblyName UIAutomationTypes | Out-Null
$pids = @(Get-Process -Name 'Telegram' | Select-Object -ExpandProperty Id)
if (-not $pids) { '' ; exit 0 }
$root = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
  [System.Windows.Automation.AutomationElement]::ProcessIdProperty, [int]$pids[0])
$wins = @($root.FindAll([System.Windows.Automation.TreeScope]::Children, $cond))
$bag = New-Object System.Collections.Generic.List[string]
function Walk([System.Windows.Automation.AutomationElement]$el, [int]$depth) {
  if ($null -eq $el -or $depth -gt 10 -or $bag.Count -gt 400) { return }
  try {
    $n = [string]$el.Current.Name
    if ($n -and $n.Trim().Length -gt 0) { [void]$bag.Add($n.Trim()) }
  } catch {}
  try {
    $kids = $el.FindAll([System.Windows.Automation.TreeScope]::Children,
      [System.Windows.Automation.Condition]::TrueCondition)
    foreach ($k in $kids) { Walk $k ($depth + 1) }
  } catch {}
}
foreach ($w in $wins) { Walk $w 0 }
($bag | Select-Object -Unique) -join "`n"
"""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                ps,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=6,
        )
        text = (completed.stdout or "").strip()
        if len(text) > max_chars:
            return text[:max_chars]
        return text
    except Exception:
        return ""


def _probe_telegram_gate() -> tuple[str, str]:
    """
    Cek siap kirim.
    Return (state, message) state: ok | passcode | login | unknown
    """
    blob = _collect_telegram_ui_text().lower()
    titles = ""
    hwnd = _find_telegram_hwnd()
    if hwnd:
        try:
            import ctypes

            user32 = ctypes.windll.user32
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            titles = (buf.value or "").lower()
        except Exception:
            titles = ""
    combined = f"{blob}\n{titles}"

    if any(h in combined for h in _PASSCODE_HINTS):
        return (
            "passcode",
            "Telegram terkunci Local Passcode. Buka kunci dulu, lalu Kirim lagi.",
        )
    if any(h in combined for h in _LOGIN_HINTS):
        return (
            "login",
            "Telegram belum login. Login dulu di Telegram Desktop, lalu Kirim lagi.",
        )
    if any(h in combined for h in _READY_HINTS):
        return "ok", "Telegram siap."
    if _tdata_suggests_session():
        # Session ada, UI tidak menunjukkan passcode/login → anggap OK
        return "ok", "Telegram siap (sesi terdeteksi)."
    if combined.strip():
        return "unknown", "Status Telegram tidak jelas — lanjut mencoba kirim."
    return (
        "login",
        "Telegram belum login atau belum siap. Buka & login Telegram, lalu coba lagi.",
    )


def _restart_telegram(telegram_exe: str = "") -> tuple[bool, str]:
    """Tutup Telegram sepenuhnya, lalu buka lagi (hindari gagal jika grup sudah terbuka)."""
    import time

    _close_telegram()
    if not open_telegram(telegram_exe, background=False):
        return False, "Telegram Desktop tidak ditemukan."
    pids: list[int] = []
    for _ in range(30):
        time.sleep(0.15)
        pids = _telegram_pids()
        if pids and _find_telegram_hwnd():
            break
    if not pids:
        return False, "Telegram gagal dibuka ulang."
    # Biarkan UI settle sebentar setelah cold start
    time.sleep(0.55)
    return True, "Telegram dibuka ulang."


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
        # Skip child / tool windows tanpa title besar — ambil yang punya ukuran wajar
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


def _sendkeys_escape(text: str) -> str:
    """Escape karakter khusus SendKeys."""
    out: list[str] = []
    for ch in text:
        if ch in "+^%~(){}[]":
            out.append("{" + ch + "}")
        else:
            out.append(ch)
    return "".join(out)


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


def _run_vbs_sendkeys(group_name: str, telegram_pid: int) -> tuple[bool, str]:
    """Jalankan otomasi via WScript.Shell SendKeys (cepat, ala AutoHotkey)."""
    import time

    safe = _sendkeys_escape(group_name)
    vbs = f"""Option Explicit
Dim sh, ok, i
Set sh = CreateObject("WScript.Shell")
ok = False
For i = 1 To 4
  ok = sh.AppActivate({int(telegram_pid)})
  If ok Then Exit For
  ok = sh.AppActivate("Telegram")
  If ok Then Exit For
  WScript.Sleep 120
Next
WScript.Sleep 200
sh.SendKeys "^k"
WScript.Sleep 220
sh.SendKeys "{safe}"
WScript.Sleep 280
sh.SendKeys "{{ENTER}}"
WScript.Sleep 350
sh.SendKeys "^v"
WScript.Sleep 180
sh.SendKeys "{{ENTER}}"
"""
    path = Path(tempfile.gettempdir()) / f"network_tools_tg_send_{os.getpid()}.vbs"
    try:
        path.write_text(vbs, encoding="utf-8")
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            ["wscript.exe", "//B", "//Nologo", str(path)],
            capture_output=True,
            text=True,
            creationflags=creation,
            timeout=30,
        )
        if completed.returncode != 0:
            return False, f"SendKeys gagal (exit {completed.returncode})."
        return True, f'Grup "{group_name}" — screenshot dikirim.'
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def paste_and_send_to_telegram_group(
    group_name: str = "",
    telegram_exe: str = "",
    *,
    settle_sec: float = 0.35,
    root: Any | None = None,
) -> tuple[bool, str]:
    """
    Alur:
    1. Tutup Telegram.exe
    2. Buka lagi
    3. Cek sudah login & tanpa local passcode
    4. Ctrl+K grup → Ctrl+V → Enter
    """
    import time

    if os.name != "nt":
        return False, "Otomasi Telegram hanya di Windows."

    name = (group_name or _telegram_group_name()).strip() or "Monitoring jaringan"
    _release_our_focus(root)

    ok_restart, restart_msg = _restart_telegram(telegram_exe)
    if not ok_restart:
        return False, restart_msg

    pids = _telegram_pids()
    if not pids:
        return False, "Proses Telegram.exe tidak ditemukan setelah dibuka ulang."

    hwnd = _find_telegram_hwnd()
    if hwnd:
        _activate_hwnd(hwnd)
        time.sleep(0.2)
    _release_our_focus(root)

    state, gate_msg = _probe_telegram_gate()
    if state == "passcode":
        return False, gate_msg
    if state == "login":
        return False, gate_msg

    time.sleep(max(0.15, settle_sec))
    pids = _telegram_pids() or pids
    hwnd = _find_telegram_hwnd()
    if hwnd:
        _activate_hwnd(hwnd)
        time.sleep(0.1)
    _release_our_focus(root)

    ok, msg = _run_vbs_sendkeys(name, pids[0])
    if ok:
        return True, f"{restart_msg} {gate_msg} {msg}".strip()
    return False, msg


def send_via_telegram(
    screenshot: Path,
    telegram_exe: str = "",
    root: Any | None = None,
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

    ok, msg = paste_and_send_to_telegram_group(telegram_exe=telegram_exe, root=root)
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

    ok, msg = paste_and_send_to_telegram_group(telegram_exe=telegram_exe, root=root)
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
        ok, msg = paste_and_send_to_telegram_group(
            telegram_exe=telegram_exe, root=root
        )
        tips.append(msg if ok else f"Otomasi gagal: {msg}. Tempel file manual (Ctrl+V).")
    elif telegram:
        subprocess.Popen([telegram], shell=False)
        tips.append("Buka chat Telegram, lalu tempel (Ctrl+V) untuk kirim file.")
    elif not copied:
        tips.append("Telegram tidak ditemukan.")
    else:
        tips.append("Telegram tidak ditemukan. File tetap di clipboard.")

    return copied, tips, path
