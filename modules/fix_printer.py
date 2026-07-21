"""Clear spooler + backup / reinstall selected printer driver (Admin)."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from modules.printer_info import reinstall_printer_driver, uninstall_printer_driver


class FixPrinterRunner:
    """
    Alur Fix Printer (butuh driver terpilih):
    1) clear spooler
    2) backup driver (INF / DriverStore)
    3) uninstall driver
    4) install ulang dari backup
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
        self.on_line("=== 1/4 CLEAR SPOOLER ===")
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

    def _backup_driver(self, name: str, inf_path: str) -> str | None:
        self.on_line("=== 2/4 BACKUP DRIVER ===")
        self.on_line(f"Driver: {name}")
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:60]
        backup_dir = local / "NetworkTools" / "printer_backup" / f"{safe}_{stamp}"
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.on_line(f"Gagal buat folder backup: {exc}")
            return None

        inf = (inf_path or "").strip().strip('"')
        if not inf:
            # Coba baca InfPath via PowerShell
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            ps = (
                f'(Get-PrinterDriver -Name "{name}" -ErrorAction SilentlyContinue).InfPath'
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
                inf = (completed.stdout or "").strip().strip('"')
            except Exception:
                inf = ""

        if inf and Path(inf).is_file():
            self.on_line(f"INF: {inf}")
            src_dir = Path(inf).parent
            try:
                # Salin seluruh folder repository driver
                dest = backup_dir / src_dir.name
                shutil.copytree(src_dir, dest, dirs_exist_ok=True)
                # Pastikan INF ada di root backup juga
                shutil.copy2(inf, backup_dir / Path(inf).name)
                self.on_line(f"Backup OK → {backup_dir}")
                return str(backup_dir)
            except Exception as exc:
                self.on_line(f"Copy folder gagal ({exc}) — coba pnputil export…")

        # Fallback: pnputil /export-driver
        if inf:
            oem = Path(inf).name
            code, out = self._run_cmd(
                ["pnputil", "/export-driver", oem, str(backup_dir)]
            )
            self._emit(out)
            if code == 0:
                self.on_line(f"Backup (pnputil) OK → {backup_dir}")
                return str(backup_dir)

        self.on_line("Backup gagal — INF/DriverStore tidak ditemukan.")
        self.on_line(f"Folder kosong disiapkan: {backup_dir}")
        return str(backup_dir) if backup_dir.exists() else None

    def _find_inf_in_backup(self, backup_dir: str) -> str:
        root = Path(backup_dir)
        if not root.is_dir():
            return ""
        # Prefer INF di root, lalu recursive
        for pattern in ("*.inf", "**/*.inf"):
            found = sorted(root.glob(pattern))
            if found:
                return str(found[0])
        return ""

    def _run(self) -> None:
        try:
            name = (self.driver.get("name") or "").strip()
            inf_path = (self.driver.get("inf_path") or "").strip()
            if not name or name == "—":
                self.on_line("Pilih driver printer di daftar terlebih dahulu.")
                return

            self.on_line("=== FIX PRINTER ===")
            self.on_line(
                "Alur: clear spooler → backup driver → uninstall → install ulang"
            )
            self.on_line(f"Target driver: {name}")
            self.on_line("")

            self._clear_spooler()

            backup_dir = self._backup_driver(name, inf_path)
            self.on_line("")

            self.on_line("=== 3/4 UNINSTALL DRIVER ===")
            ok, msg = uninstall_printer_driver(name)
            self._emit(msg)
            if not ok:
                self.on_line("Uninstall gagal — install ulang dibatalkan.")
                return
            self.on_line("Uninstall OK.")
            time.sleep(1.0)
            self.on_line("")

            self.on_line("=== 4/4 INSTALL DRIVER ===")
            install_inf = ""
            if backup_dir:
                install_inf = self._find_inf_in_backup(backup_dir)
            if not install_inf and inf_path and Path(inf_path).is_file():
                install_inf = inf_path
            if install_inf:
                self.on_line(f"Install dari: {install_inf}")
            ok2, msg2 = reinstall_printer_driver(name, install_inf)
            self._emit(msg2)
            if ok2:
                self.on_line("Install OK.")
            else:
                self.on_line("Install belum sukses — gunakan wizard bila terbuka.")

            self.on_line("")
            self.on_line("Fix printer selesai.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
