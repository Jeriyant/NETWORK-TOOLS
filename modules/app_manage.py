"""Uninstall / clean-uninstall / reinstall helpers for installed apps."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable


def _creation() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args: list[str], timeout: int = 600) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation(),
            timeout=timeout,
            shell=False,
        )
        out = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode, out.strip()
    except Exception as exc:
        return 1, str(exc)


def _run_cmd_line(cmdline: str, timeout: int = 600) -> tuple[int, str]:
    """Jalankan UninstallString mentah lewat cmd."""
    try:
        completed = subprocess.run(
            cmdline,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=_creation(),
            timeout=timeout,
            shell=True,
        )
        out = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode, out.strip()
    except Exception as exc:
        return 1, str(exc)


def _silentize(uninstall: str) -> str:
    u = (uninstall or "").strip()
    if not u:
        return u
    low = u.lower()
    if "msiexec" in low:
        if "/qn" not in low and "/quiet" not in low:
            u = re.sub(r"(?i)/i\b", "/x", u)
            if "/x" not in u.lower() and "/X" not in u:
                # pastikan mode uninstall
                u = u.replace("/I", "/X").replace("/i", "/x")
            if "/qn" not in u.lower():
                u += " /qn /norestart"
        return u
    if "/silent" in low or "/s" in low or "-silent" in low or "/quiet" in low:
        return u
    return f'{u} /S'


def uninstall_app(app: dict[str, str], *, quiet: bool = False) -> tuple[bool, str]:
    """Jalankan uninstaller aplikasi. quiet=True pakai QuietUninstall bila ada."""
    quiet_s = (app.get("quiet_uninstall") or "").strip()
    normal = (app.get("uninstall") or "").strip()
    if quiet and quiet_s:
        cmd = quiet_s
    elif quiet and normal:
        cmd = _silentize(normal)
    else:
        cmd = normal or quiet_s
    if not cmd:
        return False, "UninstallString tidak ditemukan untuk aplikasi ini."
    code, out = _run_cmd_line(cmd)
    if code == 0:
        return True, out or "Uninstall selesai."
    return False, out or f"Uninstall exit code {code}"


def _safe_rmtree(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink(missing_ok=True)  # type: ignore[call-arg]
    except Exception:
        try:
            if path.exists():
                shutil.rmtree(str(path), ignore_errors=True)
        except Exception:
            pass


def clean_uninstall_app(app: dict[str, str]) -> tuple[bool, str]:
    """Uninstall + bersihkan sisa folder InstallLocation bila masih ada."""
    ok, msg = uninstall_app(app, quiet=True)
    notes = [msg]
    loc = (app.get("install_location") or "").strip().strip('"')
    if loc:
        p = Path(os.path.expandvars(loc))
        # Jangan hapus root drive / folder sistem
        blocked = {
            Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")).resolve(),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")).resolve(),
        }
        try:
            resolved = p.resolve()
        except Exception:
            resolved = p
        if resolved.exists() and resolved not in blocked and len(resolved.parts) >= 3:
            _safe_rmtree(resolved)
            notes.append(f"Folder dibersihkan: {resolved}")
    return ok, "\n".join(notes)


def reinstall_app(app: dict[str, str]) -> tuple[bool, str]:
    """Coba winget upgrade/reinstall; fallback buka InstallLocation."""
    name = (app.get("name") or "").strip()
    if not name:
        return False, "Nama aplikasi kosong."

    # winget reinstall / upgrade
    for args in (
        ["winget", "reinstall", "--name", name, "-e", "--accept-package-agreements", "--accept-source-agreements"],
        ["winget", "install", "--name", name, "-e", "--force", "--accept-package-agreements", "--accept-source-agreements"],
    ):
        code, out = _run(args, timeout=900)
        if code == 0:
            return True, out or "Reinstall via winget selesai."
        if "No package found" in out or "tidak ditemukan" in out.lower():
            continue
        # winget mungkin tidak ada
        if "is not recognized" in out.lower() or "not found" in out.lower():
            break

    loc = (app.get("install_location") or "").strip().strip('"')
    if loc:
        folder = Path(os.path.expandvars(loc))
        for cand in ("setup.exe", "install.exe", "installer.exe", "Setup.exe"):
            setup = folder / cand
            if setup.is_file():
                try:
                    subprocess.Popen([str(setup)], shell=False, creationflags=_creation())
                    return True, f"Installer dibuka: {setup}"
                except Exception as exc:
                    return False, str(exc)

    # Buka Apps & Features
    try:
        subprocess.Popen(
            ["explorer.exe", "ms-settings:appsfeatures"],
            shell=False,
            creationflags=_creation(),
        )
        return True, "Installer tidak ditemukan — membuka Apps & Features. Uninstall manual lalu install ulang."
    except Exception as exc:
        return False, str(exc)


class AppActionRunner:
    def __init__(
        self,
        action: str,
        app: dict[str, str],
        on_line: Callable[[str], None],
        on_done: Callable[[bool], None] | None = None,
    ) -> None:
        self.action = action
        self.app = app
        self.on_line = on_line
        self.on_done = on_done

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        ok = False
        try:
            name = self.app.get("name", "?")
            self.on_line(f"=== {self.action.upper()} — {name} ===")
            if self.action == "uninstall":
                ok, msg = uninstall_app(self.app, quiet=False)
            elif self.action == "clean":
                ok, msg = clean_uninstall_app(self.app)
            else:
                ok, msg = reinstall_app(self.app)
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
