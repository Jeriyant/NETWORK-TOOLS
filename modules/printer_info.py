"""Printer driver list + uninstall / reinstall helpers."""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from typing import Callable


def _creation() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_ps(command: str, timeout: int = 120) -> tuple[int, str]:
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
            creationflags=_creation(),
            timeout=timeout,
        )
        out = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode, out.strip()
    except Exception as exc:
        return 1, str(exc)


def list_printer_drivers() -> list[dict[str, str]]:
    """Return installed printer drivers via PowerShell Get-PrinterDriver."""
    ps = (
        "Get-PrinterDriver | Select-Object Name, Manufacturer, "
        "PrinterEnvironment, MajorVersion, InfPath, Path | "
        "ConvertTo-Json -Compress"
    )
    code, raw = _run_ps(ps, timeout=60)
    if code != 0 or not raw.strip():
        return _list_printer_drivers_fallback()
    try:
        start = raw.find("[")
        start_obj = raw.find("{")
        if start < 0 or (start_obj >= 0 and start_obj < start):
            start = start_obj
        if start >= 0:
            raw = raw[start:]
        data = json.loads(raw)
    except Exception:
        return _list_printer_drivers_fallback()
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    rows: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "name": str(item.get("Name") or "—"),
                "manufacturer": str(item.get("Manufacturer") or "—"),
                "environment": str(item.get("PrinterEnvironment") or "—"),
                "version": str(item.get("MajorVersion") or "—"),
                "inf_path": str(item.get("InfPath") or item.get("Path") or ""),
            }
        )
    rows.sort(key=lambda r: r["name"].lower())
    return rows


def _list_printer_drivers_fallback() -> list[dict[str, str]]:
    """Fallback via Get-Printer (driver name from installed printers)."""
    ps = (
        "Get-Printer | Select-Object Name, DriverName, PortName, Shared | "
        "ConvertTo-Json -Compress"
    )
    code, raw = _run_ps(ps, timeout=60)
    if code != 0 or not raw.strip():
        return []
    try:
        start = raw.find("[")
        start_obj = raw.find("{")
        if start < 0 or (start_obj >= 0 and start_obj < start):
            start = start_obj
        if start >= 0:
            raw = raw[start:]
        data = json.loads(raw)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        drv = str(item.get("DriverName") or "").strip() or "—"
        key = drv.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "name": drv,
                "manufacturer": "—",
                "environment": str(item.get("PortName") or "—"),
                "version": "—",
                "inf_path": "",
            }
        )
    rows.sort(key=lambda r: r["name"].lower())
    return rows


def uninstall_printer_driver(name: str) -> tuple[bool, str]:
    """Hapus driver printer (butuh Admin)."""
    n = (name or "").replace('"', "")
    if not n or n == "—":
        return False, "Nama driver kosong."
    ps = (
        f'$n = "{n}"; '
        "Get-Printer | Where-Object { $_.DriverName -eq $n } | "
        "ForEach-Object { try { Remove-Printer -Name $_.Name -Confirm:$false } catch {} }; "
        "Remove-PrinterDriver -Name $n -RemoveFromDriverStore -ErrorAction Stop; "
        "'OK'"
    )
    code, out = _run_ps(ps, timeout=180)
    if code == 0 and "OK" in out:
        return True, out
    ps2 = f'Remove-PrinterDriver -Name "{n}" -ErrorAction Stop; "OK"'
    code2, out2 = _run_ps(ps2, timeout=120)
    if code2 == 0 and "OK" in out2:
        return True, out2
    return False, out or out2 or "Gagal uninstall driver."


def reinstall_printer_driver(name: str, inf_path: str = "") -> tuple[bool, str]:
    """Reinstall driver dari INF (pnputil + printui / Add-PrinterDriver)."""
    n = (name or "").replace('"', "")
    inf = (inf_path or "").strip().strip('"')
    notes: list[str] = []

    if inf and Path(inf).is_file():
        try:
            completed = subprocess.run(
                ["pnputil", "/add-driver", inf, "/install"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_creation(),
                timeout=180,
            )
            out = ((completed.stdout or "") + (completed.stderr or "")).strip()
            notes.append(out or f"pnputil exit {completed.returncode}")
        except Exception as exc:
            notes.append(f"pnputil: {exc}")

        # Classic PrintUI install-from-INF (paling andal untuk Type 3 driver)
        try:
            completed = subprocess.run(
                [
                    "rundll32",
                    "printui.dll,PrintUIEntry",
                    "/ia",
                    "/m",
                    n,
                    "/h",
                    "x64",
                    "/v",
                    "Type 3 - User Mode",
                    "/f",
                    inf,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_creation(),
                timeout=180,
            )
            out = ((completed.stdout or "") + (completed.stderr or "")).strip()
            notes.append(out or f"printui /ia exit {completed.returncode}")
            if completed.returncode == 0:
                # Verifikasi driver muncul
                c_chk, o_chk = _run_ps(
                    f'if (Get-PrinterDriver -Name "{n}" -ErrorAction SilentlyContinue) '
                    '{ "OK" } else { "MISSING" }',
                    timeout=60,
                )
                notes.append(o_chk)
                if "OK" in (o_chk or ""):
                    return True, "\n".join(notes)
        except Exception as exc:
            notes.append(f"printui: {exc}")

        # PowerShell Add-PrinterDriver dengan -InfPath
        ps = (
            f'$n = "{n}"; $inf = "{inf}"; '
            "try { "
            "  Add-PrinterDriver -Name $n -InfPath $inf -ErrorAction Stop; "
            '  "OK" '
            "} catch { "
            "  try { "
            "    Add-PrinterDriver -Name $n -ErrorAction Stop; "
            '    "OK" '
            "  } catch { $_.Exception.Message } "
            "}"
        )
        c2, o2 = _run_ps(ps, timeout=120)
        notes.append(o2)
        if c2 == 0 and "OK" in (o2 or ""):
            return True, "\n".join(notes)

        # Coba lagi tanpa constrains /h /v
        try:
            completed = subprocess.run(
                [
                    "rundll32",
                    "printui.dll,PrintUIEntry",
                    "/ia",
                    "/m",
                    n,
                    "/f",
                    inf,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=_creation(),
                timeout=180,
            )
            out = ((completed.stdout or "") + (completed.stderr or "")).strip()
            notes.append(out or f"printui /ia (simple) exit {completed.returncode}")
            c_chk, o_chk = _run_ps(
                f'if (Get-PrinterDriver -Name "{n}" -ErrorAction SilentlyContinue) '
                '{ "OK" } else { "MISSING" }',
                timeout=60,
            )
            notes.append(o_chk)
            if completed.returncode == 0 and "OK" in (o_chk or ""):
                return True, "\n".join(notes)
        except Exception as exc:
            notes.append(str(exc))

        return False, "\n".join(notes) if notes else "Install driver gagal."

    try:
        subprocess.Popen(
            ["printui.exe", "/il"],
            shell=False,
            creationflags=_creation(),
        )
        return True, "INF tidak tersedia — membuka wizard Install Printer."
    except Exception as exc:
        return False, str(exc) if not notes else "\n".join(notes + [str(exc)])


class PrinterDriversRunner:
    def __init__(
        self,
        on_drivers: Callable[[list[dict[str, str]]], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.on_drivers = on_drivers
        self.on_error = on_error

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            rows = list_printer_drivers()
            self.on_drivers(rows)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))
            else:
                self.on_drivers([])


class PrinterDriverActionRunner:
    def __init__(
        self,
        action: str,
        driver: dict[str, str],
        on_line: Callable[[str], None],
        on_done: Callable[[bool], None] | None = None,
    ) -> None:
        self.action = action
        self.driver = driver
        self.on_line = on_line
        self.on_done = on_done

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        ok = False
        try:
            name = self.driver.get("name", "?")
            self.on_line(f"=== {self.action.upper()} DRIVER — {name} ===")
            if self.action == "uninstall":
                ok, msg = uninstall_printer_driver(name)
            else:
                ok, msg = reinstall_printer_driver(name, self.driver.get("inf_path", ""))
            for line in (msg or "").splitlines():
                if line.strip():
                    self.on_line(line)
            self.on_line("Selesai." if ok else "Gagal / perlu tindakan manual.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
            ok = False
        finally:
            if self.on_done:
                self.on_done(ok)
