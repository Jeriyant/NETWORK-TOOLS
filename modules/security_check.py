"""Check Windows Firewall, Defender, and Windows Update service."""

from __future__ import annotations

import subprocess
import threading
from typing import Callable, TypedDict


class SecurityItem(TypedDict):
    key: str
    label: str
    status: str  # ON / OFF / UNKNOWN / RUNNING / STOPPED
    detail: str
    ok: bool


def _run_ps(command: str, timeout: int = 12) -> str:
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
            timeout=timeout,
        )
        return (completed.stdout or "").strip()
    except Exception:
        return ""


def _service_state(name: str) -> tuple[str, str]:
    """Return (Status, StartType) for a Windows service."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["sc", "query", name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=8,
        )
        out = (completed.stdout or "") + (completed.stderr or "")
        status = "UNKNOWN"
        upper = out.upper()
        if "RUNNING" in upper:
            status = "RUNNING"
        elif "STOPPED" in upper:
            status = "STOPPED"
        elif "PENDING" in upper:
            status = "PENDING"

        start_type = ""
        try:
            qc = subprocess.run(
                ["sc", "qc", name],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation,
                timeout=8,
            )
            qout = (qc.stdout or "").upper()
            if "AUTO_START" in qout:
                start_type = "Automatic"
            elif "DEMAND_START" in qout:
                start_type = "Manual"
            elif "DISABLED" in qout:
                start_type = "Disabled"
        except Exception:
            pass
        return status, start_type
    except Exception:
        return "UNKNOWN", ""


def check_firewall() -> SecurityItem:
    # Get-NetFirewallProfile: Domain, Private, Public
    out = _run_ps(
        "Get-NetFirewallProfile | ForEach-Object { "
        "\"$($_.Name)=$($_.Enabled)\" }"
    )
    profiles: dict[str, bool] = {}
    for line in out.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        name, val = line.split("=", 1)
        profiles[name.strip()] = val.strip().lower() in {"true", "1", "yes"}

    if not profiles:
        # Fallback: MpsSvc
        status, start = _service_state("MpsSvc")
        ok = status == "RUNNING"
        return {
            "key": "firewall",
            "label": "Windows Firewall",
            "status": "ON" if ok else ("OFF" if status == "STOPPED" else "UNKNOWN"),
            "detail": f"Service MpsSvc: {status}" + (f" ({start})" if start else ""),
            "ok": ok,
        }

    enabled = [n for n, on in profiles.items() if on]
    disabled = [n for n, on in profiles.items() if not on]
    all_on = bool(profiles) and not disabled
    any_on = bool(enabled)
    if all_on:
        status = "ON"
        ok = True
        detail = "Semua profil aktif: " + ", ".join(profiles.keys())
    elif any_on:
        status = "PARTIAL"
        ok = False
        detail = f"Aktif: {', '.join(enabled) or '-'} | Nonaktif: {', '.join(disabled) or '-'}"
    else:
        status = "OFF"
        ok = False
        detail = "Semua profil firewall nonaktif"

    return {
        "key": "firewall",
        "label": "Windows Firewall",
        "status": status,
        "detail": detail,
        "ok": ok,
    }


def check_defender() -> SecurityItem:
    out = _run_ps(
        "try { $s = Get-MpComputerStatus; "
        "\"AV=$($s.AntivirusEnabled);RTP=$($s.RealTimeProtectionEnabled);"
        "AM=$($s.AMServiceEnabled);AS=$($s.AntispywareEnabled)\" } "
        "catch { \"ERR=$($_.Exception.Message)\" }"
    )
    if out.startswith("ERR=") or not out:
        # Fallback: WinDefend service
        status, start = _service_state("WinDefend")
        ok = status == "RUNNING"
        return {
            "key": "defender",
            "label": "Windows Defender",
            "status": "ON" if ok else ("OFF" if status == "STOPPED" else "UNKNOWN"),
            "detail": f"Service WinDefend: {status}" + (f" ({start})" if start else ""),
            "ok": ok,
        }

    flags: dict[str, bool] = {}
    for part in out.replace(";", "\n").splitlines():
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        flags[k.strip().upper()] = v.strip().lower() in {"true", "1", "yes"}

    av = flags.get("AV", False)
    rtp = flags.get("RTP", False)
    am = flags.get("AM", False)
    ok = av and rtp
    if ok:
        status = "ON"
        detail = "Antivirus & Real-time protection aktif"
    elif av or am:
        status = "PARTIAL"
        detail = f"Antivirus={av}, Realtime={rtp}, AMService={am}"
        ok = False
    else:
        status = "OFF"
        detail = "Antivirus / real-time protection nonaktif"

    return {
        "key": "defender",
        "label": "Windows Defender",
        "status": status,
        "detail": detail,
        "ok": ok,
    }


def check_windows_update() -> SecurityItem:
    status, start = _service_state("wuauserv")
    ok = status == "RUNNING" or (status == "STOPPED" and start == "Automatic")
    # Update service sering STOPPED tapi Automatic (trigger start) — masih sehat
    if status == "RUNNING":
        label_status = "RUNNING"
        detail = "Windows Update service berjalan"
        ok = True
    elif start == "Automatic" or start == "Manual":
        label_status = "READY"
        detail = f"Service wuauserv: {status} (Start: {start or '?'})"
        ok = start != "Disabled"
    elif start == "Disabled":
        label_status = "DISABLED"
        detail = "Windows Update service dinonaktifkan"
        ok = False
    else:
        label_status = status
        detail = f"Service wuauserv: {status}" + (f" ({start})" if start else "")
        ok = False

    return {
        "key": "wuauserv",
        "label": "Windows Update",
        "status": label_status,
        "detail": detail,
        "ok": ok,
    }


def collect_security_status() -> list[SecurityItem]:
    return [check_firewall(), check_defender(), check_windows_update()]


def format_security_text(items: list[SecurityItem], hostname: str = "") -> str:
    from modules.i18n import t

    lines = [t("sec.report.title")]
    if hostname:
        lines.append(t("apps.report.pc", host=hostname))
    lines.append("")
    for item in items:
        mark = t("sec.ok") if item["ok"] else t("sec.warn")
        lines.append(f"[{mark}] {item['label']}: {item['status']}")
        lines.append(f"     {item['detail']}")
        lines.append("")
    return "\n".join(lines).rstrip()


class SecurityCheckRunner:
    def __init__(
        self,
        on_result: Callable[[list[SecurityItem]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.on_result = on_result
        self.on_error = on_error
        self.on_done = on_done
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            items = collect_security_status()
            if self.on_result:
                self.on_result(items)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))
        finally:
            if self.on_done:
                self.on_done()
