"""Permanent built-in settings (no external config.json)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# --- Hosts for Ping / Traceroute ---
# Gateway ip="auto" = detect default gateway at runtime
HOSTS: list[dict[str, str]] = [
    {"name": "Internet", "ip": "8.8.8.8"},
    {"name": "Gateway", "ip": "auto"},
    {"name": "Server-VPN", "ip": "191.177.4.33"},
    {"name": "Server-DB", "ip": "191.177.4.1"},
    {"name": "Server-App1", "ip": "191.177.4.3"},
    {"name": "Server-App2", "ip": "191.177.4.4"},
    {"name": "Server-App3", "ip": "191.177.4.5"},
    {"name": "Server-App4", "ip": "191.177.4.6"},
    {"name": "Server-App5", "ip": "191.177.4.8"},
    {"name": "Server-App6", "ip": "191.177.4.9"},
    {"name": "Server-App7", "ip": "191.177.4.7"},
    {"name": "Server-App8", "ip": "191.177.4.11"},
]

SPEEDTEST_URL = "https://jeriyant.speedtestcustom.com"
DNS_LEAK_URL = "https://browserleaks.com/dns"

# AnyDesk download URL kept for optional use; menu Anydesk opens installed app + copies ID
ANYDESK_DRIVE_FILE_ID = "1bCt6Qwj4XgrpQC0h9j5lqqcEPDu63a8g"
ANYDESK_URL = (
    f"https://drive.google.com/uc?export=download&id={ANYDESK_DRIVE_FILE_ID}"
)

DNS_TEST_DOMAINS = [
    "google.com",
    "cloudflare.com",
    "microsoft.com",
    "whoami.akamai.net",
]

NETWORK_ADAPTER = ""  # empty = auto pick first Up adapter
DEFAULT_THEME = "system"
DEFAULT_LANG = "id"

# App version — naikkan setiap rilis baru (harus cocok dengan tag GitHub Release)
APP_VERSION = "2.49"
UPDATE_REPO = "https://github.com/Jeriyant/NETWORK-TOOLS"

# Grup Telegram tujuan tombol Kirim (deep link → Desktop → paste → Send)
TELEGRAM_GROUP = "Monitoring jaringan"
TELEGRAM_GROUP_URL = "https://t.me/cusjnetmonitor"

# Nama file di Desktop saat auto-copy EXE
DESKTOP_EXE_NAME = "NetworkTools.exe"


def app_root() -> Path:
    """Folder containing the EXE (or project root when running from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _user_desktop_dirs() -> list[Path]:
    """Lokasi Desktop Windows (termasuk OneDrive bila ada)."""
    found: list[Path] = []
    home = Path.home()
    candidates = [
        home / "Desktop",
        home / "OneDrive" / "Desktop",
        home / "OneDrive - Personal" / "Desktop",
    ]
    # USERPROFILE\Desktop via env
    userprofile = __import__("os").environ.get("USERPROFILE", "")
    if userprofile:
        candidates.append(Path(userprofile) / "Desktop")
    # Shell folder registry (paling akurat di Win10/11)
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            val, _ = winreg.QueryValueEx(key, "Desktop")
            if val:
                expanded = __import__("os").path.expandvars(str(val))
                candidates.insert(0, Path(expanded))
    except Exception:
        pass

    seen: set[str] = set()
    for p in candidates:
        try:
            rp = p.expanduser().resolve()
        except Exception:
            continue
        key = str(rp).lower()
        if key in seen:
            continue
        seen.add(key)
        if rp.is_dir():
            found.append(rp)
    return found


def ensure_copy_to_desktop() -> bool:
    """
    Saat startup (EXE): salin diri ke Desktop bila belum ada.
    Jika NetworkTools.exe sudah ada di Desktop → tidak melakukan apa-apa.
    Returns True jika berhasil menyalin, False jika skip/gagal.
    """
    import shutil

    if not getattr(sys, "frozen", False):
        return False
    try:
        src = Path(sys.executable).resolve()
    except Exception:
        return False
    if not src.is_file():
        return False

    desktops = _user_desktop_dirs()
    if not desktops:
        return False

    # Sudah jalan dari salah satu Desktop → skip
    src_parent = src.parent
    for desk in desktops:
        try:
            if src_parent == desk or src_parent.resolve() == desk.resolve():
                return False
        except Exception:
            pass

    # Target: Desktop utama (pertama yang valid)
    dest = desktops[0] / DESKTOP_EXE_NAME
    try:
        if dest.is_file():
            return False  # sudah ada — jangan timpa / jangan apa-apa
    except Exception:
        return False

    try:
        shutil.copy2(src, dest)
        return True
    except Exception:
        return False


def detect_default_gateway() -> str | None:
    """Return IPv4 default gateway, or None if not found."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Prefer PowerShell Get-NetRoute
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue "
                "| Sort-Object RouteMetric | Select-Object -First 1).NextHop",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
        )
        gw = (completed.stdout or "").strip()
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", gw):
            return gw
    except Exception:
        pass

    # Fallback: parse `route print -4`
    try:
        completed = subprocess.run(
            ["route", "print", "-4"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
        )
        for line in (completed.stdout or "").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "0.0.0.0":
                cand = parts[2]
                if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", cand):
                    return cand
    except Exception:
        pass
    return None


def host_dropdown_values() -> list[str]:
    values: list[str] = []
    for h in HOSTS:
        name = h["name"]
        ip = h["ip"]
        if ip == "auto":
            values.append(f"{name} - (otomatis cek gateway)")
        else:
            values.append(f"{name} - {ip}")
    return values


def resolve_target_ip(name: str, ip_text: str) -> tuple[str, str | None]:
    """
    Resolve dropdown selection to (display_name, ip).
    Returns (name, None) if gateway detection fails.
    """
    name = (name or "").strip()
    ip_text = (ip_text or "").strip()
    # Bersihkan sisa teks UI / encoding rusak
    ip_text = ip_text.replace("\u2014", " ").replace("â€”", " ").strip()
    if ip_text.startswith("("):
        ip_text = ip_text.strip("()").strip()
    if name.lower() == "gateway" or ip_text == "auto" or "otomatis" in ip_text.lower():
        gw = detect_default_gateway()
        return name or "Gateway", gw
    return name, ip_text
