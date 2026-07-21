"""Clear printer spooler only (Admin)."""

from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable


class FixPrinterRunner:
    """
    Alur Fix Printer:
    1) net stop spooler
    2) hapus antrian di System32\\spool\\PRINTERS
    3) net start spooler
    """

    def __init__(
        self,
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
        driver: dict[str, str] | None = None,
    ) -> None:
        self.on_line = on_line
        self.on_done = on_done
        self.driver = driver or {}
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run_cmd(self, args: list[str], shell: bool = False) -> tuple[int, str]:
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=shell,
            creationflags=creation,
        )
        out = (completed.stdout or "") + (completed.stderr or "")
        return completed.returncode, out.strip()

    def _emit(self, out: str) -> None:
        for line in (out or "").splitlines():
            line = line.strip()
            if line:
                self.on_line(line)

    def _clear_spooler(self) -> None:
        self.on_line("=== CLEAR SPOOLER ===")
        windir = os.environ.get("SYSTEMROOT", os.environ.get("WINDIR", r"C:\Windows"))
        spool = os.path.join(windir, "System32", "spool", "PRINTERS")
        self.on_line(f"Folder spool: {spool}")
        self.on_line("")

        self.on_line("> net stop spooler")
        code, out = self._run_cmd(["net", "stop", "spooler"])
        self._emit(out)
        if code != 0:
            self.on_line(f"(exit {code}) — lanjut mencoba hapus file...")
        self.on_line("")

        self.on_line(r"> del %systemroot%\System32\spool\printers\* /Q /F /S")
        code, out = self._run_cmd(
            ["cmd", "/c", r"del %systemroot%\System32\spool\printers\* /Q /F /S"]
        )
        self._emit(out or "(tidak ada output / folder sudah kosong)")
        self.on_line("")

        self.on_line("> net start spooler")
        code, out = self._run_cmd(["net", "start", "spooler"])
        self._emit(out)
        if code != 0:
            self.on_line(f"(exit {code}) — coba jalankan ulang sebagai Administrator.")
        self.on_line("")

    def _run(self) -> None:
        try:
            self.on_line("=== FIX PRINTER ===")
            self.on_line("Alur: clear spooler saja (stop → hapus antrian → start)")
            self.on_line("")
            self._clear_spooler()
            self.on_line("Clear spooler selesai.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
