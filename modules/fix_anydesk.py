"""Open AnyDesk, copy client ID to clipboard; Telegram dibuka dari tombol Kirim."""

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
        return False, f"Gagal taskkill: {exc}"

    for _ in range(8):
        time.sleep(0.4)
        if not _anydesk_process_running():
            return True, "AnyDesk ditutup paksa."
    if _anydesk_process_running():
        return False, "AnyDesk masih berjalan setelah taskkill."
    return True, "AnyDesk ditutup paksa."


def format_anydesk_share_text(anydesk_id: str, local_id: str, local_ip: str) -> str:
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

            # 1) Tutup paksa
            self.on_line("Menutup AnyDesk secara paksa…")
            closed, msg = close_all_anydesk()
            self.on_line(msg)
            if closed:
                time.sleep(1.0)

            # 2) Buka di latar (minimized)
            self.on_line("Membuka AnyDesk di latar belakang…")
            try:
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = 6  # SW_MINIMIZE
                subprocess.Popen([str(exe)], shell=False, startupinfo=si)
            except Exception as exc:
                self.on_line(f"Gagal membuka AnyDesk: {exc}")
                return

            # 3) Ambil & salin ID
            self.on_line("Menunggu ID AnyDesk…")
            for wait in (2.5, 2.0, 2.0, 2.0):
                time.sleep(wait)
                anydesk_id = get_anydesk_id_cli(exe) or read_anydesk_id_from_files()
                if anydesk_id:
                    break

            if not anydesk_id:
                self.on_line("AnyDesk ID belum tersedia.")
                self.on_line("Tunggu ID tampil di AnyDesk, lalu Jalankan lagi.")
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
            self.on_line("Selesai — notifikasi siap. Tekan Kirim untuk buka Telegram.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done(anydesk_id)
