"""List installed printer drivers (Windows)."""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Any, Callable


def list_printer_drivers() -> list[dict[str, str]]:
    """Return installed printer drivers via PowerShell Get-PrinterDriver."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ps = (
        "Get-PrinterDriver | Select-Object Name, Manufacturer, "
        "PrinterEnvironment, MajorVersion, Path | "
        "ConvertTo-Json -Compress"
    )
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
            timeout=60,
        )
        raw = (completed.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
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
                }
            )
        rows.sort(key=lambda r: r["name"].lower())
        return rows
    except Exception:
        return _list_printer_drivers_fallback()


def _list_printer_drivers_fallback() -> list[dict[str, str]]:
    """Fallback via Get-Printer (driver name from installed printers)."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ps = (
        "Get-Printer | Select-Object Name, DriverName, PortName, Shared | "
        "ConvertTo-Json -Compress"
    )
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
            timeout=60,
        )
        raw = (completed.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
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
                }
            )
        rows.sort(key=lambda r: r["name"].lower())
        return rows
    except Exception:
        return []


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
