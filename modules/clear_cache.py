"""Clear Windows temp and RDP6 cache folders."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Callable


class ClearCacheRunner:
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

    def _clear_dir(self, path: Path) -> tuple[int, int]:
        removed = 0
        failed = 0
        if not path.exists():
            return 0, 0
        for entry in list(path.iterdir()):
            try:
                if entry.is_file() or entry.is_symlink():
                    entry.unlink(missing_ok=True)
                    removed += 1
                elif entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=False)
                    removed += 1
            except Exception:
                failed += 1
        return removed, failed

    def _run(self) -> None:
        try:
            self.on_line("=== CLEAR CACHE ===")
            self.on_line("")

            targets: list[tuple[str, Path]] = []
            targets.append(("Windows TEMP", Path(tempfile.gettempdir())))
            targets.append(("User TEMP", Path(os.environ.get("TEMP", tempfile.gettempdir()))))

            windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
            targets.append(("Windows\\Temp", windir / "Temp"))

            userprofile = Path(os.environ.get("USERPROFILE", str(Path.home())))
            targets.append(("RDP6 Cache", userprofile / "RDP6"))

            # Deduplicate
            seen: set[str] = set()
            unique: list[tuple[str, Path]] = []
            for label, path in targets:
                key = str(path.resolve()) if path.exists() else str(path)
                if key in seen:
                    continue
                seen.add(key)
                unique.append((label, path))

            for label, path in unique:
                self.on_line(f"Membersihkan: {label}")
                self.on_line(f"  Path: {path}")
                if not path.exists():
                    self.on_line("  (folder tidak ada — dilewati)")
                    self.on_line("")
                    continue
                removed, failed = self._clear_dir(path)
                self.on_line(f"  Dihapus: {removed} item, gagal: {failed}")
                self.on_line("")

            self.on_line("Clear cache selesai.")
            self.on_line(
                "Catatan: beberapa file yang sedang dipakai Windows tidak bisa dihapus."
            )
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
