"""Reset Remote Desktop client state for a fresh RDP session (requires Admin for some steps)."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable


class FixRdpRunner:
    """
    Buat RDP client 'fresh':
    - matikan ConnectionClient / mstsc / msrdc
    - hapus folder RDP6 & cache Terminal Server Client
    - bersihkan registry RDP (MRU, servers, default)
    - hapus kredensial TERMSRV dari Credential Manager (jika ada)
    """

    _PROCESSES = (
        "ConnectionClient.exe",
        "mstsc.exe",
        "msrdc.exe",
        "rdpclip.exe",
    )

    def __init__(
        self,
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.on_line = on_line
        self.on_done = on_done
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

    def _kill_processes(self) -> None:
        self.on_line("1) Mematikan proses RDP client…")
        for name in self._PROCESSES:
            self.on_line(f"  > taskkill /F /IM {name} /T")
            code, out = self._run_cmd(["taskkill", "/F", "/IM", name, "/T"])
            if code == 0:
                self._emit(out or f"  {name} dihentikan.")
            else:
                # 128 = process not found — normal
                self.on_line(f"  (tidak berjalan / sudah mati)")
        self.on_line("")

    def _remove_tree(self, label: str, path: Path) -> None:
        self.on_line(f"  {label}")
        self.on_line(f"    {path}")
        if not path.exists():
            self.on_line("    (tidak ada — dilewati)")
            return
        try:
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            else:
                shutil.rmtree(path, ignore_errors=True)
            if path.exists():
                # Partial lock — clear contents
                removed = 0
                failed = 0
                for entry in list(path.iterdir()):
                    try:
                        if entry.is_dir():
                            shutil.rmtree(entry, ignore_errors=True)
                        else:
                            entry.unlink(missing_ok=True)
                        removed += 1
                    except Exception:
                        failed += 1
                self.on_line(f"    Dibersihkan: {removed} item, gagal: {failed}")
            else:
                self.on_line("    Dihapus.")
        except Exception as exc:
            self.on_line(f"    Gagal: {exc}")

    def _clear_folders(self) -> None:
        self.on_line("2) Menghapus cache / folder RDP…")
        user = Path(os.environ.get("USERPROFILE", str(Path.home())))
        local = Path(os.environ.get("LOCALAPPDATA", str(user / "AppData" / "Local")))
        roaming = Path(os.environ.get("APPDATA", str(user / "AppData" / "Roaming")))

        targets = [
            ("RDP6", user / "RDP6"),
            ("Terminal Server Client Cache", local / "Microsoft" / "Terminal Server Client" / "Cache"),
            ("Terminal Server Client", local / "Microsoft" / "Terminal Server Client"),
            (
                "Roaming Terminal Server Client",
                roaming / "Microsoft" / "Terminal Server Client",
            ),
        ]
        # Microsoft Remote Desktop / Connection Client package state
        packages = local / "Packages"
        if packages.is_dir():
            for pkg in packages.iterdir():
                name = pkg.name.lower()
                if "remote" in name and "desktop" in name:
                    targets.append((f"Package LocalState ({pkg.name})", pkg / "LocalState"))
                    targets.append((f"Package TempState ({pkg.name})", pkg / "TempState"))

        seen: set[str] = set()
        for label, path in targets:
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            self._remove_tree(label, path)
        self.on_line("")

    def _clear_registry(self) -> None:
        self.on_line("3) Membersihkan registry RDP (HKCU)…")
        # Hapus pohon Terminal Server Client (MRU, Servers, Default, LocalDevices)
        key = r"HKCU\Software\Microsoft\Terminal Server Client"
        self.on_line(f"  > reg delete \"{key}\" /f")
        code, out = self._run_cmd(["reg", "delete", key, "/f"])
        if code == 0:
            self.on_line("    OK — registry RDP dihapus.")
        else:
            msg = (out or "").lower()
            if "unable to find" in msg or "tidak dapat menemukan" in msg or code == 1:
                self.on_line("    (kunci tidak ada — dilewati)")
            else:
                self._emit(out or f"    exit {code}")
        self.on_line("")

    def _clear_credentials(self) -> None:
        self.on_line("4) Menghapus kredensial TERMSRV (Credential Manager)…")
        code, out = self._run_cmd(["cmdkey", "/list"])
        if code != 0 and not out:
            self.on_line("  Tidak bisa membaca cmdkey /list.")
            self.on_line("")
            return

        targets: list[str] = []
        for line in (out or "").splitlines():
            line = line.strip()
            # Target: TERMSRV/host or LegacyGeneric:target=TERMSRV/...
            if "TERMSRV" not in line.upper():
                continue
            if ":" in line:
                # "Target: TERMSRV/10.0.0.1" or "Target: LegacyGeneric:target=TERMSRV/..."
                _, _, rest = line.partition(":")
                target = rest.strip()
            else:
                target = line
            if target and target not in targets:
                targets.append(target)

        if not targets:
            self.on_line("  Tidak ada kredensial TERMSRV.")
            self.on_line("")
            return

        for target in targets:
            self.on_line(f"  > cmdkey /delete:{target}")
            c, o = self._run_cmd(["cmdkey", f"/delete:{target}"])
            if c == 0:
                self.on_line("    Dihapus.")
            else:
                self._emit(o or f"    exit {c}")
        self.on_line("")

    def _run(self) -> None:
        try:
            self.on_line("=== FIX RDP (Reset Remote Desktop) ===")
            self.on_line("Membuat sesi RDP client fresh.")
            self.on_line("")

            self._kill_processes()
            self._clear_folders()
            self._clear_registry()
            self._clear_credentials()

            self.on_line("Fix RDP selesai.")
            self.on_line("Buka Remote Desktop / Connection Client lagi untuk koneksi baru.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
