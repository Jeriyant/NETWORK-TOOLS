"""AnyDesk: taskkill → jalankan exe → baca ID → notifikasi."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable


def find_anydesk_exe() -> Path | None:
    candidates: list[Path] = []
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env, "")
        if base:
            candidates.append(Path(base) / "AnyDesk" / "AnyDesk.exe")
    which = shutil.which("AnyDesk.exe")
    if which:
        candidates.append(Path(which))
    for p in (
        Path(r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe"),
        Path(r"C:\Program Files\AnyDesk\AnyDesk.exe"),
    ):
        candidates.append(p)
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path
    return None


def _creation() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _read_id_from_conf(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(r"ad\.anynet\.id\s*=\s*([0-9]+)", text)
    return m.group(1) if m else None


def read_anydesk_id_from_files() -> str | None:
    paths: list[Path] = []
    program_data = os.environ.get("ProgramData", r"C:\ProgramData")
    appdata = os.environ.get("APPDATA", "")
    paths.append(Path(program_data) / "AnyDesk" / "system.conf")
    paths.append(Path(program_data) / "AnyDesk" / "service.conf")
    if appdata:
        paths.append(Path(appdata) / "AnyDesk" / "system.conf")
        paths.append(Path(appdata) / "AnyDesk" / "service.conf")
    for path in paths:
        if path.is_file():
            aid = _read_id_from_conf(path)
            if aid:
                return aid
    return None


def get_anydesk_id_cli(exe: Path) -> str | None:
    try:
        completed = subprocess.run(
            [str(exe), "--get-id"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=_creation(),
        )
        out = ((completed.stdout or "") + (completed.stderr or "")).strip()
        if "SERVICE_NOT_RUNNING" in out.upper():
            return None
        m = re.search(r"(\d{5,})", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def _taskkill_anydesk() -> str:
    """taskkill /F /IM AnyDesk.exe /T (best-effort, tanpa Admin)."""
    try:
        completed = subprocess.run(
            ["taskkill", "/F", "/IM", "AnyDesk.exe", "/T"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=_creation(),
        )
        out = ((completed.stdout or "") + (completed.stderr or "")).strip()
        if not out:
            return f"taskkill exit {completed.returncode}"
        # Ringkas baris error/sukses
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return "\n".join(lines[:6])
    except Exception as exc:
        return str(exc)


def _start_anydesk(exe: Path) -> tuple[bool, str]:
    """Jalankan AnyDesk.exe (normal)."""
    try:
        subprocess.Popen(
            [str(exe)],
            shell=False,
            creationflags=_creation(),
        )
        return True, f"Menjalankan: {exe}"
    except Exception as exc:
        return False, str(exc)


def format_anydesk_share_text(anydesk_id: str, local_id: str, local_ip: str) -> str:
    return (
        f"ID Anydesk\n{anydesk_id}\n\n"
        f"ID Lokal\n{local_id}\n\n"
        f"Alamat IP Lokal\n{local_ip}"
    )


class AnydeskRunner:
    """Alur: taskkill → jalankan AnyDesk.exe → baca ID → on_done."""

    def __init__(
        self,
        on_line: Callable[[str], None],
        on_done: Callable[[str | None], None] | None = None,
    ) -> None:
        self.on_line = on_line
        self.on_done = on_done
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _poll_id(self, exe: Path, rounds: int = 10, delay: float = 1.0) -> str | None:
        for i in range(rounds):
            aid = get_anydesk_id_cli(exe) or read_anydesk_id_from_files()
            if aid:
                return aid
            if i + 1 < rounds:
                time.sleep(delay)
        return None

    def _run(self) -> None:
        anydesk_id: str | None = None
        try:
            self.on_line("=== ANYDESK ===")
            self.on_line("")

            exe = find_anydesk_exe()
            if exe is None:
                self.on_line("AnyDesk tidak ditemukan di komputer ini.")
                self.on_line("Install AnyDesk terlebih dahulu, lalu coba lagi.")
                return

            self.on_line(f"Menemukan: {exe}")
            self.on_line("")

            self.on_line("1/3 taskkill AnyDesk.exe…")
            msg = _taskkill_anydesk()
            for line in msg.splitlines():
                if line.strip():
                    self.on_line(f"  {line}")
            time.sleep(1.0)

            self.on_line("2/3 Menjalankan AnyDesk.exe…")
            ok, start_msg = _start_anydesk(exe)
            self.on_line(f"  {start_msg}")
            if not ok:
                return
            time.sleep(2.0)

            self.on_line("3/3 Membaca AnyDesk ID…")
            anydesk_id = self._poll_id(exe, rounds=12, delay=1.0)
            if not anydesk_id:
                self.on_line("AnyDesk ID belum tersedia. Coba lagi sebentar.")
                return

            self.on_line(f"AnyDesk ID: {anydesk_id}")
            self.on_line("Menyalin info ke clipboard…")

            from modules.system_info import hostname, primary_ipv4
            from modules.telegram_share import copy_text_to_clipboard

            local_id = hostname()
            local_ip = primary_ipv4()
            share_text = format_anydesk_share_text(anydesk_id, local_id, local_ip)
            if copy_text_to_clipboard(share_text):
                self.on_line("Info tersalin ke clipboard.")
            else:
                self.on_line("Gagal menyalin ke clipboard.")

            self.on_line("")
            self.on_line("Selesai — menampilkan notifikasi ID.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done(anydesk_id)
