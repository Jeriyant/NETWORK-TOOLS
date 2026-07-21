"""Open AnyDesk tray / read ID; Telegram dibuka dari tombol Kirim."""

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
        if "SERVICE_NOT_RUNNING" in out.upper():
            return None
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


def _force_kill_anydesk(exe: Path | None = None) -> str:
    """Tutup AnyDesk: CLI stop → taskkill → elevated taskkill bila perlu."""
    import ctypes

    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    notes: list[str] = []

    if exe is not None and exe.is_file():
        for flag in ("--stop", "--shutdown"):
            try:
                subprocess.run(
                    [str(exe), flag],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=15,
                    creationflags=creation,
                )
                notes.append(f"AnyDesk {flag}")
            except Exception as exc:
                notes.append(f"{flag}: {exc}")
        time.sleep(0.6)

    try:
        completed = subprocess.run(
            ["taskkill", "/F", "/IM", "AnyDesk.exe", "/T"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=creation,
        )
        out = ((completed.stdout or "") + (completed.stderr or "")).strip()
        # Ringkas: jangan spam Access Denied per-PID
        if "Access is denied" in out or "akses ditolak" in out.lower():
            notes.append("taskkill: sebagian proses terkunci (butuh elevasi)…")
        elif out:
            # Ambil baris sukses saja
            ok_lines = [
                ln
                for ln in out.splitlines()
                if "SUCCESS" in ln.upper() or "berhasil" in ln.lower()
            ]
            notes.append("; ".join(ok_lines) if ok_lines else "taskkill dijalankan.")
        else:
            notes.append(f"taskkill exit {completed.returncode}")
    except Exception as exc:
        notes.append(str(exc))

    time.sleep(0.4)
    if _anydesk_process_running():
        notes.append("Menjalankan taskkill sebagai Administrator…")
        try:
            # SW_HIDE = 0; rc > 32 = success
            rc = int(
                ctypes.windll.shell32.ShellExecuteW(
                    None,
                    "runas",
                    "taskkill.exe",
                    "/F /IM AnyDesk.exe /T",
                    None,
                    0,
                )
            )
            if rc <= 32:
                notes.append(f"Elevasi dibatalkan / gagal (kode {rc}).")
            else:
                time.sleep(2.0)
                notes.append("taskkill elevated OK.")
        except Exception as exc:
            notes.append(f"Elevasi: {exc}")

    if _anydesk_process_running():
        notes.append("Peringatan: AnyDesk masih berjalan (service mungkin terkunci).")
    else:
        notes.append("AnyDesk berhasil ditutup.")
    return "\n".join(notes)


def _start_anydesk_tray(exe: Path) -> tuple[bool, str]:
    """Jalankan AnyDesk di system tray saja (--tray / --control)."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    last = "Gagal start tray"
    for args in (
        [str(exe), "--tray"],
        [str(exe), "--control"],
    ):
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0  # SW_HIDE
            subprocess.Popen(
                args,
                shell=False,
                startupinfo=si,
                creationflags=creation,
            )
            return True, f"AnyDesk tray: {' '.join(args[1:])}"
        except Exception as exc:
            last = str(exc)
            continue
    return False, last


def _ensure_service(exe: Path) -> None:
    """Coba start service AnyDesk (butuh admin; gagal diabaikan)."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        subprocess.run(
            [str(exe), "--start"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            creationflags=creation,
        )
    except Exception:
        pass


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

    def _poll_id(self, exe: Path, rounds: int = 6, delay: float = 1.2) -> str | None:
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

            # Alur: tutup paksa → tray → baca ID → notifikasi
            self.on_line("1/3 Menutup paksa AnyDesk…")
            for line in _force_kill_anydesk(exe).splitlines():
                if line.strip():
                    self.on_line(f"  {line}")
            time.sleep(0.8)

            self.on_line("2/3 Menjalankan AnyDesk mode tray…")
            _ensure_service(exe)
            ok, msg = _start_anydesk_tray(exe)
            self.on_line(f"  {msg}" if ok else f"  Tray: {msg}")
            time.sleep(1.5)

            self.on_line("3/3 Membaca AnyDesk ID…")
            anydesk_id = self._poll_id(exe, rounds=10, delay=1.2)

            if not anydesk_id:
                self.on_line("  ID belum ada — coba tray ulang…")
                _start_anydesk_tray(exe)
                anydesk_id = self._poll_id(exe, rounds=8, delay=1.5)

            if not anydesk_id:
                self.on_line("AnyDesk ID belum tersedia.")
                self.on_line("Pastikan AnyDesk terpasang & online di system tray.")
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

            if _anydesk_process_running():
                self.on_line("AnyDesk di system tray (tanpa jendela utama).")
            self.on_line("")
            self.on_line("Selesai — menampilkan notifikasi.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done(anydesk_id)
