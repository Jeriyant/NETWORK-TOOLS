"""Collect local machine summary for the header status strip."""

from __future__ import annotations

import ctypes
import platform
import re
import socket
import subprocess
from ctypes import wintypes
from typing import TypedDict


class SystemInfo(TypedDict):
    hostname: str
    ip: str
    cpu: str
    ram: str
    uptime: str
    windows: str


def _run_ps(command: str) -> str:
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=8,
        )
        return (completed.stdout or "").strip()
    except Exception:
        return ""


def hostname() -> str:
    try:
        return socket.gethostname() or platform.node() or "-"
    except Exception:
        return "-"


def primary_ipv4() -> str:
    out = _run_ps(
        "(Get-NetIPConfiguration | Where-Object { $_.IPv4DefaultGateway -ne $null "
        "-and $_.NetAdapter.Status -eq 'Up' } | Select-Object -First 1)."
        "IPv4Address.IPAddress"
    )
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", out):
        return out

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except Exception:
        pass
    return "-"


def _clean_spaces(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def cpu_name() -> str:
    out = _run_ps(
        "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"
    )
    if out:
        return _clean_spaces(out)
    return _clean_spaces(platform.processor() or "") or "-"


def ram_summary() -> str:
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            raise OSError("GlobalMemoryStatusEx failed")
        total_gb = stat.ullTotalPhys / (1024**3)
        used_gb = (stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3)
        return f"{total_gb:.0f} GB · {used_gb:.1f} used"
    except Exception:
        return "-"


def uptime_summary() -> str:
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.GetTickCount64.restype = ctypes.c_ulonglong
        ms = int(kernel32.GetTickCount64())
        sec = ms // 1000
        days, rem = divmod(sec, 86400)
        hours, rem = divmod(rem, 3600)
        mins, _ = divmod(rem, 60)
        if days > 0:
            return f"{days}d {hours}h {mins}m"
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"
    except Exception:
        return "-"


def windows_version() -> str:
    out = _run_ps(
        "$p=Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion'; "
        "$name=$p.ProductName; $disp=$p.DisplayVersion; if (-not $disp) { $disp=$p.ReleaseId }; "
        "$build=$p.CurrentBuild; $ubr=$p.UBR; "
        "if ([int]$build -ge 22000 -and $name -like 'Windows 10*') { "
        "  $name=$name -replace 'Windows 10','Windows 11' "
        "}; "
        "\"$name $disp (Build $build.$ubr)\""
    )
    if out:
        return _clean_spaces(out)
    return platform.platform() or "-"


def collect_system_info() -> SystemInfo:
    return {
        "hostname": hostname(),
        "ip": primary_ipv4(),
        "cpu": cpu_name(),
        "ram": ram_summary(),
        "uptime": uptime_summary(),
        "windows": windows_version(),
    }
