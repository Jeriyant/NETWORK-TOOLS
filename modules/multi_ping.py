"""Multi-host continuous ping for dashboard-style cards."""

from __future__ import annotations

import re
import subprocess
import threading
from typing import Callable

_RTT_RE = re.compile(
    r"(?:time|waktu)[=<]\s*(\d+)\s*ms",
    re.IGNORECASE,
)


def parse_ping_status(line: str) -> tuple[bool | None, str]:
    """
    Parse one ping output line.
    Returns (True, 'Reply 12 ms') / (False, 'Request timed out') / (None, '') if ignore.
    """
    text = (line or "").strip()
    if not text:
        return None, ""
    low = text.lower()

    if (
        "timed out" in low
        or "habis waktu" in low
        or "waktu tunggu permintaan" in low
        or "request timed out" in low
        or "general failure" in low
        or "destination host unreachable" in low
        or "tidak dapat diakses" in low
        or "could not find host" in low
        or "tidak menemukan host" in low
    ):
        return False, "Request timed out"

    m = _RTT_RE.search(text)
    if m:
        return True, f"Reply {m.group(1)} ms"

    if (
        "reply from" in low
        or "balasan dari" in low
        or ("bytes=" in low and "ttl=" in low)
        or ("byte=" in low and "ttl=" in low)
    ):
        return True, "Reply"

    return None, ""


class MultiHostPingRunner:
    """Ping terus ke banyak host; callback status per host_id."""

    def __init__(
        self,
        targets: list[tuple[str, str, str]],
        on_status: Callable[[str, bool, str], None],
    ) -> None:
        # targets: (host_id, display_name, ip)
        self.targets = targets
        self.on_status = on_status
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._procs: list[subprocess.Popen[str]] = []

    def start(self) -> None:
        self._stop.clear()
        self._threads = []
        self._procs = []
        for host_id, _name, ip in self.targets:
            th = threading.Thread(
                target=self._run_one,
                args=(host_id, ip),
                daemon=True,
            )
            self._threads.append(th)
            th.start()

    def stop(self) -> None:
        self._stop.set()
        for proc in list(self._procs):
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.kill()
                except Exception:
                    pass

    def _run_one(self, host_id: str, ip: str) -> None:
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.Popen(
                ["ping", "-t", ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=creation,
            )
            self._procs.append(proc)
            assert proc.stdout is not None
            for line in proc.stdout:
                if self._stop.is_set():
                    break
                ok, status = parse_ping_status(line)
                if ok is None:
                    continue
                try:
                    self.on_status(host_id, ok, status)
                except Exception:
                    pass
        except Exception as exc:
            try:
                self.on_status(host_id, False, f"Error: {exc}")
            except Exception:
                pass
        finally:
            if not self._stop.is_set():
                # process ended unexpectedly — mark offline
                try:
                    self.on_status(host_id, False, "Request timed out")
                except Exception:
                    pass
