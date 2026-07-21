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
APP_VERSION = "2.43"
UPDATE_REPO = "https://github.com/Jeriyant/NETWORK-TOOLS"

# Grup Telegram tujuan tombol Kirim (otomatis cari + paste + kirim)
TELEGRAM_GROUP = "Monitoring jaringan"


def app_root() -> Path:
    """Folder containing the EXE (or project root when running from source)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


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
