"""List installed Windows applications (Uninstall registry)."""

from __future__ import annotations

import threading
import winreg
from typing import Callable

_UNINSTALL_PATHS = (
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
)


def _read_str(key: winreg.HKEYType, name: str) -> str:
    try:
        val, _ = winreg.QueryValueEx(key, name)
        return str(val or "").strip()
    except OSError:
        return ""


def collect_installed_apps() -> list[dict[str, str]]:
    """Return sorted unique apps with name / version / publisher / uninstall / icon."""
    seen: set[str] = set()
    apps: list[dict[str, str]] = []

    for hive, path in _UNINSTALL_PATHS:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    sub = winreg.OpenKey(root, sub_name)
                except OSError:
                    continue
                try:
                    display = _read_str(sub, "DisplayName")
                    if not display:
                        continue
                    if display.startswith("Update for ") or display.startswith("Security Update"):
                        continue
                    try:
                        sc_val, _ = winreg.QueryValueEx(sub, "SystemComponent")
                        if sc_val in (1, "1", b"\x01\x00\x00\x00"):
                            continue
                    except OSError:
                        pass
                    key = display.casefold()
                    if key in seen:
                        continue
                    seen.add(key)
                    apps.append(
                        {
                            "name": display,
                            "version": _read_str(sub, "DisplayVersion") or "—",
                            "publisher": _read_str(sub, "Publisher") or "—",
                            "icon": _read_str(sub, "DisplayIcon"),
                            "uninstall": _read_str(sub, "UninstallString"),
                            "quiet_uninstall": _read_str(sub, "QuietUninstallString"),
                            "install_location": _read_str(sub, "InstallLocation"),
                            "key_path": f"{path}\\{sub_name}",
                        }
                    )
                finally:
                    winreg.CloseKey(sub)
        finally:
            winreg.CloseKey(root)

    apps.sort(key=lambda a: a["name"].casefold())
    return apps


def format_apps_text(apps: list[dict[str, str]], hostname: str = "") -> str:
    from modules.i18n import t

    lines = [t("apps.report.title")]
    if hostname:
        lines.append(t("apps.report.pc", host=hostname))
    lines.append(t("apps.report.total", n=len(apps)))
    lines.append("")
    for idx, app in enumerate(apps, 1):
        ver = app.get("version") or "—"
        pub = app.get("publisher") or "—"
        lines.append(f"{idx}. {app['name']}")
        lines.append(
            f"   {t('apps.report.version')}: {ver}  |  {t('apps.report.publisher')}: {pub}"
        )
    return "\n".join(lines)


class InstalledAppsRunner:
    def __init__(
        self,
        on_apps: Callable[[list[dict[str, str]]], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.on_apps = on_apps
        self.on_error = on_error
        self.on_done = on_done
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            apps = collect_installed_apps()
            if self.on_apps:
                self.on_apps(apps)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))
        finally:
            if self.on_done:
                self.on_done()
