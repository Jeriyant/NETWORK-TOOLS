"""Check whether RDP (TCP 3389) is reachable on ping-menu hosts."""

from __future__ import annotations

import socket
import threading
import time
from typing import Callable

from modules.settings import HOSTS, resolve_target_ip

RDP_PORT = 3389
CONNECT_TIMEOUT = 2.5


def check_rdp_port(ip: str, port: int = RDP_PORT, timeout: float = CONNECT_TIMEOUT) -> tuple[bool, str]:
    """
    Probe RDP listener via TCP connect.
    Returns (is_running, detail).
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True, f"port {port} terbuka"
    except socket.timeout:
        return False, "timeout"
    except ConnectionRefusedError:
        return False, "connection refused"
    except OSError as exc:
        return False, str(exc) or "unreachable"


class RdpTestRunner:
    def __init__(
        self,
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
        port: int = RDP_PORT,
    ) -> None:
        self.on_line = on_line
        self.on_done = on_done
        self.port = port
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            self.on_line("=== RDP TEST ===")
            self.on_line(f"Cek service RDP (TCP {self.port}) pada host menu Ping")
            self.on_line("")

            running = 0
            down = 0
            skipped = 0

            for host in HOSTS:
                if self._stop.is_set():
                    self.on_line("Dibatalkan.")
                    break

                name = host.get("name", "?")
                ip_text = host.get("ip", "")
                display, ip = resolve_target_ip(name, ip_text)

                if not ip:
                    self.on_line(f"[SKIP]  {display:<14}  gateway tidak terdeteksi")
                    skipped += 1
                    continue

                t0 = time.perf_counter()
                ok, detail = check_rdp_port(ip, self.port)
                ms = (time.perf_counter() - t0) * 1000

                if ok:
                    running += 1
                    status = "RUNNING"
                else:
                    down += 1
                    status = "NOT RUNNING"

                self.on_line(
                    f"[{status:<11}]  {display:<14}  {ip:<15}  "
                    f"{detail}  ({ms:.0f} ms)"
                )

            self.on_line("")
            self.on_line(
                f"Selesai — RUNNING: {running}  |  NOT RUNNING: {down}"
                + (f"  |  SKIP: {skipped}" if skipped else "")
            )
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
