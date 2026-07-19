"""Scan the local LAN subnet for live hosts (ICMP ping)."""

from __future__ import annotations

import concurrent.futures
import ipaddress
import platform
import socket
import subprocess
import threading
from typing import Callable

from modules.system_info import primary_ipv4


def local_ipv4_and_prefix() -> tuple[str | None, int]:
    """Return (ip, prefixlen). Prefer /24 if mask unknown."""
    ip = primary_ipv4()
    if not ip or ip == "-":
        return None, 24

    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"(Get-NetIPAddress -AddressFamily IPv4 -IPAddress '{ip}' "
                f"-ErrorAction SilentlyContinue | Select-Object -First 1).PrefixLength",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=6,
        )
        raw = (completed.stdout or "").strip()
        if raw.isdigit():
            prefix = int(raw)
            if 8 <= prefix <= 30:
                return ip, prefix
    except Exception:
        pass
    return ip, 24


def _ping_host(ip: str, timeout_ms: int = 600) -> bool:
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    args = ["ping", "-n", "1", "-w", str(timeout_ms), ip]
    if platform.system().lower() != "windows":
        args = ["ping", "-c", "1", "-W", "1", ip]
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
            timeout=max(2, timeout_ms / 1000 + 1.5),
        )
        return completed.returncode == 0
    except Exception:
        return False


def _resolve_hostname(ip: str) -> str:
    try:
        name, _, _ = socket.gethostbyaddr(ip)
        return name or "-"
    except Exception:
        return "-"


class IpScannerRunner:
    """
    Callbacks (semua dipanggil dari thread worker — UI harus marshal ke main thread):
    - on_start(local_ip, network_str, total)
    - on_progress(checked, total)
    - on_host(ip, hostname, is_self)
    - on_done(found_count, total, cancelled)
    - on_error(message)
    """

    def __init__(
        self,
        on_start: Callable[[str, str, int], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_host: Callable[[str, str, bool], None] | None = None,
        on_done: Callable[[int, int, bool], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        workers: int = 64,
    ) -> None:
        self.on_start = on_start
        self.on_progress = on_progress
        self.on_host = on_host
        self.on_done = on_done
        self.on_error = on_error
        self.workers = workers
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        cancelled = False
        found_count = 0
        total = 0
        try:
            ip, prefix = local_ipv4_and_prefix()
            if not ip:
                if self.on_error:
                    self.on_error("IP lokal tidak terdeteksi. Periksa koneksi jaringan.")
                return

            try:
                iface = ipaddress.ip_interface(f"{ip}/{prefix}")
                network = iface.network
            except ValueError as exc:
                if self.on_error:
                    self.on_error(f"Subnet tidak valid: {exc}")
                return

            hosts = [str(h) for h in network.hosts()]
            max_hosts = 1022
            if len(hosts) > max_hosts:
                iface = ipaddress.ip_interface(f"{ip}/24")
                network = iface.network
                hosts = [str(h) for h in network.hosts()]

            total = len(hosts)
            if self.on_start:
                self.on_start(ip, str(network), total)

            found: list[tuple[str, str]] = []
            checked = 0
            lock = threading.Lock()

            def work(addr: str) -> None:
                nonlocal checked, found_count
                if self._stop.is_set():
                    return
                alive = _ping_host(addr)
                with lock:
                    checked += 1
                    n = checked
                if self.on_progress and (n % 8 == 0 or n == total):
                    self.on_progress(n, total)
                if alive and not self._stop.is_set():
                    host = _resolve_hostname(addr)
                    is_self = addr == ip
                    with lock:
                        found.append((addr, host))
                        found_count = len(found)
                    if self.on_host:
                        self.on_host(addr, host, is_self)

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = [pool.submit(work, h) for h in hosts]
                for fut in concurrent.futures.as_completed(futures):
                    if self._stop.is_set():
                        cancelled = True
                        break
                    try:
                        fut.result()
                    except Exception:
                        pass
                if self._stop.is_set():
                    cancelled = True
                    for fut in futures:
                        fut.cancel()

            if self.on_progress:
                self.on_progress(total if not cancelled else checked, total)
        except Exception as exc:
            if self.on_error:
                self.on_error(str(exc))
        finally:
            if self.on_done:
                self.on_done(found_count, total, cancelled)
