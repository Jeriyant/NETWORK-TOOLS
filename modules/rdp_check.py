"""Poll RDP (TCP 3389) status for multiple hosts — card UI companion."""

from __future__ import annotations

import socket
import threading
import time
from typing import Callable


class MultiHostRdpRunner:
    """
    Cek berkala apakah port RDP (default 3389 atau custom port) terbuka di tiap host.
    on_status(host_id, ok, status_text)
    """

    def __init__(
        self,
        targets: list[tuple[str, str, str] | tuple[str, str, str, int]],
        on_status: Callable[[str, bool, str], None],
        *,
        port: int = 3389,
        interval: float = 3.0,
        connect_timeout: float = 2.0,
    ) -> None:
        self.targets = list(targets)
        self.on_status = on_status
        self.default_port = int(port)
        self.interval = max(1.0, float(interval))
        self.connect_timeout = max(0.5, float(connect_timeout))
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        self._stop.clear()
        for item in self.targets:
            if len(item) == 4:
                host_id, _name, ip, item_port = item  # type: ignore
            else:
                host_id, _name, ip = item[:3]  # type: ignore
                item_port = self.default_port
            th = threading.Thread(
                target=self._loop,
                args=(host_id, ip, item_port),
                daemon=True,
            )
            self._threads.append(th)
            th.start()

    def stop(self) -> None:
        self._stop.set()

    def _check(self, ip: str, port: int) -> tuple[bool, str]:
        sock: socket.socket | None = None
        target_ip = ip.strip()
        if ":" in target_ip:
            parts = target_ip.split(":", 1)
            target_ip = parts[0].strip()
            try:
                port = int(parts[1].strip())
            except ValueError:
                pass
        try:
            sock = socket.create_connection((target_ip, port), timeout=self.connect_timeout)
            return True, f"RDP :{port} open"
        except TimeoutError:
            return False, f"RDP :{port} timeout"
        except OSError as exc:
            err = str(exc).lower()
            if "refused" in err or "10061" in err:
                return False, f"RDP :{port} closed"
            return False, f"RDP :{port} down"
        except Exception:
            return False, f"RDP :{port} down"
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def _loop(self, host_id: str, ip: str, port: int) -> None:
        while not self._stop.is_set():
            ok, text = self._check(ip, port)
            try:
                self.on_status(host_id, ok, text)
            except Exception:
                pass
            # Interval dengan interrupt cepat saat stop
            end = time.time() + self.interval
            while time.time() < end:
                if self._stop.is_set():
                    return
                time.sleep(0.2)
