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


def _local_ipv4_and_prefix() -> tuple[str | None, int]:
    """Return (ip, prefixlen). Prefer /24 if mask unknown."""
    ip = primary_ipv4()
    if not ip or ip == "-":
        return None, 24

    # Try PowerShell for prefix length
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
    # Windows: ping -n 1 -w timeout_ms
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
    def __init__(
        self,
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
        workers: int = 64,
    ) -> None:
        self.on_line = on_line
        self.on_done = on_done
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
        try:
            self.on_line("=== IP SCANNER ===")
            ip, prefix = _local_ipv4_and_prefix()
            if not ip:
                self.on_line("IP lokal tidak terdeteksi. Periksa koneksi jaringan.")
                return

            try:
                iface = ipaddress.ip_interface(f"{ip}/{prefix}")
                network = iface.network
            except ValueError as exc:
                self.on_line(f"Subnet tidak valid: {exc}")
                return

            hosts = [str(h) for h in network.hosts()]
            # Cap very large subnets (e.g. /16) to avoid huge scans
            max_hosts = 1022  # roughly /22
            if len(hosts) > max_hosts:
                self.on_line(
                    f"Subnet {network} terlalu besar ({len(hosts)} host). "
                    f"Memindai /24 di sekitar {ip}."
                )
                iface = ipaddress.ip_interface(f"{ip}/24")
                network = iface.network
                hosts = [str(h) for h in network.hosts()]

            self.on_line(f"IP lokal : {ip}/{prefix}")
            self.on_line(f"Subnet  : {network}")
            self.on_line(f"Target  : {len(hosts)} host")
            self.on_line("Memindai (ICMP ping)…")
            self.on_line("")

            found: list[tuple[str, str]] = []
            checked = 0
            lock = threading.Lock()

            def work(addr: str) -> None:
                nonlocal checked
                if self._stop.is_set():
                    return
                alive = _ping_host(addr)
                with lock:
                    checked += 1
                    n = checked
                if n % 32 == 0 or n == len(hosts):
                    self.on_line(f"  Progress: {n}/{len(hosts)}")
                if alive and not self._stop.is_set():
                    host = _resolve_hostname(addr)
                    with lock:
                        found.append((addr, host))
                    mark = " (PC ini)" if addr == ip else ""
                    self.on_line(f"  [UP] {addr:<15}  {host}{mark}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
                futures = [pool.submit(work, h) for h in hosts]
                for fut in concurrent.futures.as_completed(futures):
                    if self._stop.is_set():
                        break
                    try:
                        fut.result()
                    except Exception:
                        pass
                if self._stop.is_set():
                    for fut in futures:
                        fut.cancel()

            self.on_line("")
            if self._stop.is_set():
                self.on_line("Scan dibatalkan.")
            else:
                # Sort by IP
                def _key(item: tuple[str, str]) -> tuple[int, ...]:
                    parts = item[0].split(".")
                    return tuple(int(p) for p in parts)

                found.sort(key=_key)
                self.on_line(f"Selesai. Host hidup: {len(found)} / {len(hosts)}")
                if found:
                    self.on_line("")
                    self.on_line("Ringkasan:")
                    for addr, host in found:
                        mark = " *" if addr == ip else ""
                        self.on_line(f"  {addr:<15}  {host}{mark}")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
