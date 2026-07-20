"""Check Windows Firewall, Defender/AV, and Windows Update accurately."""

from __future__ import annotations

import re
import subprocess
import threading
from typing import Callable, TypedDict


class SecurityItem(TypedDict):
    key: str
    label: str
    status: str  # ON / OFF / PARTIAL / READY / DISABLED / UNKNOWN / RUNNING
    detail: str
    ok: bool


def _run_ps(command: str, timeout: int = 15) -> str:
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


def _run_cmd(args: list[str], timeout: int = 10) -> str:
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=timeout,
        )
        return ((completed.stdout or "") + (completed.stderr or "")).strip()
    except Exception:
        return ""


def _service_state(name: str) -> tuple[str, str, bool]:
    """Return (Status, StartType, has_trigger)."""
    status = "UNKNOWN"
    start_type = ""
    has_trigger = False

    out = _run_cmd(["sc", "query", name]).upper()
    if "RUNNING" in out:
        status = "RUNNING"
    elif "STOPPED" in out:
        status = "STOPPED"
    elif "PENDING" in out:
        status = "PENDING"

    qout = _run_cmd(["sc", "qc", name]).upper()
    if "AUTO_START" in qout:
        # AUTO_START (DELAYED) still counts as Automatic
        start_type = "Automatic"
    elif "DEMAND_START" in qout:
        start_type = "Manual"
    elif "DISABLED" in qout:
        start_type = "Disabled"

    trig = _run_cmd(["sc", "qtriggerinfo", name]).upper()
    if "START SERVICE" in trig or "TRIGGER" in trig:
        has_trigger = True

    return status, start_type, has_trigger


def _truthy(val: str) -> bool:
    return val.strip().lower() in {"true", "1", "yes", "on", "enabled"}


def check_firewall() -> SecurityItem:
    """Firewall OK hanya jika service MpsSvc running DAN profil aktif."""
    svc_status, svc_start, _ = _service_state("MpsSvc")
    svc_ok = svc_status == "RUNNING"

    profiles: dict[str, bool] = {}
    out = _run_ps(
        "Get-NetFirewallProfile -ErrorAction SilentlyContinue | "
        "ForEach-Object { \"$($_.Name)=$($_.Enabled)\" }"
    )
    for line in out.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        name, val = line.split("=", 1)
        profiles[name.strip()] = _truthy(val)

    # Fallback netsh (bahasa EN/ID)
    if not profiles:
        netsh = _run_cmd(["netsh", "advfirewall", "show", "allprofiles"])
        current = ""
        for raw in netsh.splitlines():
            line = raw.strip()
            low = line.lower()
            if "domain profile" in low or "profil domain" in low:
                current = "Domain"
            elif "private profile" in low or "profil pribadi" in low:
                current = "Private"
            elif "public profile" in low or "profil publik" in low:
                current = "Public"
            elif current and (
                "state" in low
                or "status" in low
                or low.startswith("keadaan")
                or low.startswith("state")
            ):
                on = ("on" in low) or ("aktif" in low) or ("enabled" in low)
                off = ("off" in low) or ("nonaktif" in low) or ("disabled" in low)
                if on and not off:
                    profiles[current] = True
                elif off:
                    profiles[current] = False
                current = ""

    if not profiles:
        ok = svc_ok
        return {
            "key": "firewall",
            "label": "Windows Firewall",
            "status": "ON" if ok else ("OFF" if svc_status == "STOPPED" else "UNKNOWN"),
            "detail": f"Service MpsSvc: {svc_status}"
            + (f" ({svc_start})" if svc_start else "")
            + " — profil tidak terbaca",
            "ok": ok,
        }

    enabled = [n for n, on in profiles.items() if on]
    disabled = [n for n, on in profiles.items() if not on]
    all_on = bool(profiles) and not disabled

    if not svc_ok:
        return {
            "key": "firewall",
            "label": "Windows Firewall",
            "status": "OFF",
            "detail": f"Service MpsSvc {svc_status}; profil: "
            + ", ".join(f"{k}={'ON' if v else 'OFF'}" for k, v in profiles.items()),
            "ok": False,
        }

    if all_on:
        return {
            "key": "firewall",
            "label": "Windows Firewall",
            "status": "ON",
            "detail": "Service berjalan; semua profil aktif: " + ", ".join(profiles.keys()),
            "ok": True,
        }
    if enabled:
        return {
            "key": "firewall",
            "label": "Windows Firewall",
            "status": "PARTIAL",
            "detail": f"Aktif: {', '.join(enabled)} | Nonaktif: {', '.join(disabled)}",
            "ok": False,
        }
    return {
        "key": "firewall",
        "label": "Windows Firewall",
        "status": "OFF",
        "detail": "Semua profil firewall nonaktif",
        "ok": False,
    }


def _decode_product_state(state: int) -> tuple[bool, bool]:
    """SecurityCenter2 productState → (enabled, up_to_date)."""
    # Format umum: 0x00YYZZ — YY=10 enabled, ZZ=00 up-to-date
    hex6 = f"{int(state) & 0xFFFFFF:06X}"
    enabled = hex6[2:4] in {"10", "11"}
    up_to_date = hex6[4:6] == "00"
    return enabled, up_to_date


def _security_center_avs() -> list[dict[str, object]]:
    out = _run_ps(
        "Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct "
        "-ErrorAction SilentlyContinue | ForEach-Object { "
        "\"$($_.displayName)|$($_.productState)\" }"
    )
    items: list[dict[str, object]] = []
    for line in out.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        name, state_s = line.split("|", 1)
        try:
            state = int(state_s.strip())
        except ValueError:
            continue
        enabled, up_to_date = _decode_product_state(state)
        items.append(
            {
                "name": name.strip() or "Antivirus",
                "enabled": enabled,
                "up_to_date": up_to_date,
                "state": state,
            }
        )
    return items


def check_defender() -> SecurityItem:
    """Defender/AV: MpComputerStatus + SecurityCenter2 + umur signature."""
    mp = _run_ps(
        "try { $s = Get-MpComputerStatus -ErrorAction Stop; "
        "\"AV=$($s.AntivirusEnabled);RTP=$($s.RealTimeProtectionEnabled);"
        "AM=$($s.AMServiceEnabled);AS=$($s.AntispywareEnabled);"
        "AGE=$($s.AntivirusSignatureAge)\" } "
        "catch { \"ERR=$($_.Exception.Message)\" }"
    )

    flags: dict[str, str] = {}
    if mp and not mp.startswith("ERR="):
        for part in re.split(r"[;\r\n]+", mp):
            part = part.strip()
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            flags[k.strip().upper()] = v.strip()

    avs = _security_center_avs()
    active_avs = [a for a in avs if a.get("enabled")]
    outdated = [a for a in active_avs if not a.get("up_to_date")]

    av = _truthy(flags.get("AV", ""))
    rtp = _truthy(flags.get("RTP", ""))
    am = _truthy(flags.get("AM", ""))
    age_s = flags.get("AGE", "")
    try:
        sig_age = int(float(age_s)) if age_s != "" else -1
    except ValueError:
        sig_age = -1

    # Prefer Security Center if third-party AV is the active product
    third_party = [
        a
        for a in active_avs
        if "defender" not in str(a.get("name", "")).lower()
        and "windows security" not in str(a.get("name", "")).lower()
    ]

    if third_party:
        names = ", ".join(str(a["name"]) for a in third_party)
        if outdated:
            return {
                "key": "defender",
                "label": "Antivirus",
                "status": "PARTIAL",
                "detail": f"Aktif: {names} — definisi tidak mutakhir",
                "ok": False,
            }
        return {
            "key": "defender",
            "label": "Antivirus",
            "status": "ON",
            "detail": f"Dilindungi antivirus pihak ketiga: {names}",
            "ok": True,
        }

    # Windows Defender path
    if flags:
        if av and rtp:
            if sig_age > 7:
                return {
                    "key": "defender",
                    "label": "Windows Defender",
                    "status": "PARTIAL",
                    "detail": f"Realtime aktif, tapi signature sudah {sig_age} hari",
                    "ok": False,
                }
            detail = "Antivirus & real-time protection aktif"
            if sig_age >= 0:
                detail += f" (signature {sig_age} hari)"
            return {
                "key": "defender",
                "label": "Windows Defender",
                "status": "ON",
                "detail": detail,
                "ok": True,
            }
        if av or am:
            return {
                "key": "defender",
                "label": "Windows Defender",
                "status": "PARTIAL",
                "detail": f"Antivirus={av}, Realtime={rtp}, AMService={am}",
                "ok": False,
            }
        return {
            "key": "defender",
            "label": "Windows Defender",
            "status": "OFF",
            "detail": "Antivirus / real-time protection nonaktif",
            "ok": False,
        }

    if active_avs:
        names = ", ".join(str(a["name"]) for a in active_avs)
        ok = not outdated
        return {
            "key": "defender",
            "label": "Antivirus",
            "status": "ON" if ok else "PARTIAL",
            "detail": (
                f"Security Center: {names}"
                + (" — definisi tidak mutakhir" if outdated else "")
            ),
            "ok": ok,
        }

    # Last resort: WinDefend service
    status, start, _ = _service_state("WinDefend")
    ok = status == "RUNNING"
    return {
        "key": "defender",
        "label": "Windows Defender",
        "status": "ON" if ok else ("OFF" if status == "STOPPED" else "UNKNOWN"),
        "detail": f"Service WinDefend: {status}" + (f" ({start})" if start else ""),
        "ok": ok,
    }


def check_windows_update() -> SecurityItem:
    """
    Windows Update sehat jika:
    - UsoSvc berjalan, ATAU
    - wuauserv RUNNING, ATAU
    - wuauserv tidak Disabled dan punya trigger start (normal di Win10/11).
    """
    wu_status, wu_start, wu_trigger = _service_state("wuauserv")
    uso_status, uso_start, _ = _service_state("UsoSvc")

    if wu_start == "Disabled":
        return {
            "key": "wuauserv",
            "label": "Windows Update",
            "status": "DISABLED",
            "detail": "Service wuauserv dinonaktifkan",
            "ok": False,
        }

    if uso_status == "RUNNING" or wu_status == "RUNNING":
        parts = []
        if uso_status == "RUNNING":
            parts.append("UsoSvc berjalan")
        if wu_status == "RUNNING":
            parts.append("wuauserv berjalan")
        elif wu_status != "UNKNOWN":
            parts.append(f"wuauserv {wu_status}" + (f"/{wu_start}" if wu_start else ""))
        return {
            "key": "wuauserv",
            "label": "Windows Update",
            "status": "ON",
            "detail": "; ".join(parts),
            "ok": True,
        }

    # Normal modern Windows: Manual + Trigger Start, stopped until needed
    if wu_start in {"Automatic", "Manual"} and (wu_trigger or wu_start == "Automatic"):
        detail = f"wuauserv {wu_status} ({wu_start}"
        if wu_trigger:
            detail += ", Trigger Start"
        detail += ")"
        if uso_status and uso_status != "UNKNOWN":
            detail += f"; UsoSvc {uso_status}"
            if uso_start:
                detail += f"/{uso_start}"
        return {
            "key": "wuauserv",
            "label": "Windows Update",
            "status": "READY",
            "detail": detail + " — siap dipicu sistem",
            "ok": True,
        }

    if uso_start == "Disabled":
        return {
            "key": "wuauserv",
            "label": "Windows Update",
            "status": "DISABLED",
            "detail": f"UsoSvc dinonaktifkan; wuauserv {wu_status}/{wu_start or '?'}",
            "ok": False,
        }

    return {
        "key": "wuauserv",
        "label": "Windows Update",
        "status": wu_status if wu_status != "UNKNOWN" else "UNKNOWN",
        "detail": f"wuauserv {wu_status}"
        + (f" ({wu_start})" if wu_start else "")
        + (f"; UsoSvc {uso_status}" if uso_status != "UNKNOWN" else ""),
        "ok": False,
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
