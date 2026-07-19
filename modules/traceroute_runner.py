"""Traceroute (tracert -d) runner."""

from __future__ import annotations

import subprocess
import threading
from typing import Callable


class TracerouteRunner:
    def __init__(
        self,
        target: str,
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.target = target
        self.on_line = on_line
        self.on_done = on_done
        self._proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            try:
                self._proc.kill()
            except Exception:
                pass

    def _run(self) -> None:
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.on_line(f"Tracing route to {self.target} (no DNS resolve)...")
            self.on_line("")
            self._proc = subprocess.Popen(
                ["tracert", "-d", self.target],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation,
            )
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                if self._stop.is_set():
                    break
                text = line.rstrip("\r\n")
                if text:
                    self.on_line(text)
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            self.stop()
            if self.on_done:
                self.on_done()
