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


def _anydesk_process_running() -> bool:
    """True jika ada proses AnyDesk.exe yang masih hidup."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq AnyDesk.exe", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=creation,
        )
        out = (completed.stdout or "").lower()
        return "anydesk.exe" in out
    except Exception:
        return False


def close_all_anydesk() -> tuple[bool, str]:
    """
    Tutup semua proses AnyDesk yang berjalan (UI + background).
    Returns (ada_yang_ditutup_atau_sudah_mati, pesan_log).
    """
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if not _anydesk_process_running():
        return False, "Tidak ada AnyDesk yang sedang berjalan."

    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "AnyDesk.exe", "/T"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=creation,
        )
    except Exception as exc:
        return False, f"Gagal menutup AnyDesk: {exc}"

    # Tunggu sampai proses benar-benar hilang
    for _ in range(20):
        if not _anydesk_process_running():
            return True, "Semua proses AnyDesk ditutup."
        time.sleep(0.25)

    if _anydesk_process_running():
        return False, "AnyDesk masih berjalan setelah taskkill (mungkin terkunci)."
    return True, "Semua proses AnyDesk ditutup."


def format_anydesk_share_text(anydesk_id: str, local_id: str, local_ip: str) -> str:
    """Teks untuk clipboard / tempel Telegram."""
    return (
        f"ID Anydesk\n{anydesk_id}\n\n"
        f"ID Lokal\n{local_id}\n\n"
        f"Alamat IP Lokal\n{local_ip}"
    )


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

            # Ambil ID dulu tanpa buka UI jika memungkinkan
            self.on_line("Membaca AnyDesk ID...")
            anydesk_id = get_anydesk_id_cli(exe) or read_anydesk_id_from_files()

            if not anydesk_id:
                self.on_line("Menutup AnyDesk yang sedang berjalan...")
                closed, msg = close_all_anydesk()
                self.on_line(msg)
                if closed:
                    time.sleep(1.0)

                self.on_line("Menjalankan AnyDesk di latar (minimized)…")
                try:
                    si = subprocess.STARTUPINFO()
                    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    si.wShowWindow = 6  # SW_MINIMIZE
                    subprocess.Popen([str(exe)], shell=False, startupinfo=si)
                except Exception as exc:
                    self.on_line(f"Gagal membuka AnyDesk: {exc}")
                    return

                time.sleep(2.5)
                anydesk_id = get_anydesk_id_cli(exe) or read_anydesk_id_from_files()
                if not anydesk_id:
                    time.sleep(2.0)
                    anydesk_id = get_anydesk_id_cli(exe) or read_anydesk_id_from_files()

            if not anydesk_id:
                self.on_line("AnyDesk ID belum tersedia.")
                self.on_line("Buka AnyDesk sampai ID tampil, lalu Jalankan lagi.")
                return

            self.on_line(f"AnyDesk ID: {anydesk_id}")
            self.on_line("Menyalin info ke clipboard...")

            from modules.system_info import hostname, primary_ipv4
            from modules.telegram_share import copy_text_to_clipboard, open_telegram

            local_id = hostname()
            local_ip = primary_ipv4()
            share_text = format_anydesk_share_text(anydesk_id, local_id, local_ip)

            if copy_text_to_clipboard(share_text):
                self.on_line("Info tersalin ke clipboard.")
            else:
                self.on_line("Gagal menyalin ke clipboard.")

            self.on_line("Membuka Telegram di latar belakang...")
            if open_telegram(background=True):
                self.on_line("Telegram dibuka (minimized) — tempel ID dengan Ctrl+V.")
            else:
                self.on_line("Telegram tidak ditemukan. ID sudah di clipboard.")

            self.on_line("")
            self.on_line("Selesai.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done(anydesk_id)
