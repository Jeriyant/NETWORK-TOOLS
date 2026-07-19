"""Open AnyDesk, copy client ID to clipboard, and open Telegram."""

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
    # Portable / common custom locations
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


def _read_id_from_conf(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    m = re.search(r"ad\.anynet\.id\s*=\s*([0-9]+)", text)
    if m:
        return m.group(1)
    return None


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
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [str(exe), "--get-id"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=creation,
        )
        out = ((completed.stdout or "") + (completed.stderr or "")).strip()
        m = re.search(r"(\d{5,})", out)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


class AnydeskRunner:
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
            self.on_line("Membuka AnyDesk...")
            try:
                subprocess.Popen([str(exe)], shell=False)
            except Exception as exc:
                self.on_line(f"Gagal membuka AnyDesk: {exc}")
                return

            # Tunggu sebentar agar ID / service siap
            time.sleep(1.5)

            self.on_line("Membaca AnyDesk ID...")
            anydesk_id = get_anydesk_id_cli(exe)
            if not anydesk_id:
                anydesk_id = read_anydesk_id_from_files()

            if not anydesk_id:
                # Coba lagi setelah jeda (ID kadang belum tertulis)
                time.sleep(2.0)
                anydesk_id = get_anydesk_id_cli(exe) or read_anydesk_id_from_files()

            if not anydesk_id:
                self.on_line("AnyDesk ID belum tersedia.")
                self.on_line("Buka AnyDesk sampai ID tampil, lalu Jalankan lagi.")
                return

            self.on_line(f"AnyDesk ID: {anydesk_id}")
            self.on_line("Menyalin ID ke clipboard...")

            from modules.telegram_share import copy_text_to_clipboard, open_telegram

            if copy_text_to_clipboard(anydesk_id):
                self.on_line("ID tersalin ke clipboard.")
            else:
                self.on_line("Gagal menyalin ke clipboard.")

            self.on_line("Membuka Telegram...")
            if open_telegram():
                self.on_line("Telegram dibuka — tempel ID dengan Ctrl+V atau Paste.")
            else:
                self.on_line("Telegram tidak ditemukan. ID sudah di clipboard.")

            self.on_line("")
            self.on_line("Selesai.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done(anydesk_id)
