"""Parse traceroute hops, reverse-DNS, and classify hop device type."""

from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import threading
from typing import Callable

_HOP_LINE = re.compile(r"^\s*(\d+)\s+(.+)$")
_IP_RE = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_RTT_RE = re.compile(r"(\d+)\s*ms", re.IGNORECASE)

_ROUTER_KEYS = (
    "router",
    "gateway",
    "gw-",
    "-gw",
    ".gw.",
    "core",
    "edge",
    "bras",
    "bng",
    "olt",
    "dslam",
    "cpe",
    "modem",
    "switch",
    "firewall",
    "fw-",
    "nat",
    "bb.",
    "backbone",
    "pe-",
    "p-",
    "access",
)
_SERVER_KEYS = (
    "server",
    "srv",
    "dns",
    "cdn",
    "cloud",
    "google",
    "amazonaws",
    "azure",
    "akamai",
    "cloudflare",
    "ns1",
    "ns2",
    "host",
    "vps",
    "datacenter",
    "dc-",
)
_PC_KEYS = (
    "pc-",
    "desktop",
    "laptop",
    "workstation",
    "client",
    "user-",
    "nb-",
    "notebook",
)

WELL_KNOWN_DNS = {
    "8.8.8.8": ("dns", "🌐", "Google DNS"),
    "8.8.4.4": ("dns", "🌐", "Google DNS"),
    "1.1.1.1": ("dns", "🌐", "Cloudflare DNS"),
    "1.0.0.1": ("dns", "🌐", "Cloudflare DNS"),
    "9.9.9.9": ("dns", "🌐", "Quad9 DNS"),
}


def parse_tracert_hop(line: str) -> tuple[int, str | None, str] | None:
    """Returns (hop, ip_or_None, rtt_label) or None."""
    text = (line or "").rstrip()
    m = _HOP_LINE.match(text)
    if not m:
        return None
    hop = int(m.group(1))
    rest = m.group(2).strip()
    low = rest.lower()
    if "*" in rest and not _IP_RE.search(rest):
        return hop, None, "Request timed out"
    if "timed out" in low or "habis waktu" in low or "waktu tunggu" in low:
        return hop, None, "Request timed out"

    ip_m = _IP_RE.search(rest)
    if not ip_m:
        return hop, None, rest[:40] or "—"

    ip = ip_m.group(1)
    rtts = _RTT_RE.findall(rest)
    if rtts:
        try:
            avg = sum(int(x) for x in rtts) // len(rtts)
            return hop, ip, f"{avg} ms"
        except Exception:
            return hop, ip, f"{rtts[0]} ms"
    return hop, ip, "OK"


def reverse_dns(ip: str, timeout: float = 1.5) -> str | None:
    """PTR lookup; returns hostname or None."""
    if not ip:
        return None
    try:
        socket.setdefaulttimeout(timeout)
        name, _alias, _addrs = socket.gethostbyaddr(ip)
        return name
    except Exception:
        return None
    finally:
        socket.setdefaulttimeout(None)


def _is_private(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_private
    except Exception:
        return False


def classify_hop(
    *,
    ip: str | None,
    hostname: str | None = None,
    hop_num: int = 0,
    is_local: bool = False,
    is_target: bool = False,
) -> tuple[str, str, str]:
    """
    Classify hop device.
    Returns (kind, icon, label) e.g. ('router', '📡', 'Router').
    """
    if is_local:
        return "pc", "💻", "PC"
    if not ip:
        return "unknown", "❓", "Timeout"
    if ip in WELL_KNOWN_DNS or is_target:
        kind, icon, label = WELL_KNOWN_DNS.get(ip, ("server", "🗄", "Target"))
        return kind, icon, label

    hn = (hostname or "").lower()
    if any(k in hn for k in _ROUTER_KEYS):
        return "router", "📡", "Router"
    if any(k in hn for k in _SERVER_KEYS):
        return "server", "🗄", "Server"
    if any(k in hn for k in _PC_KEYS):
        return "pc", "💻", "PC"

    # Hop 1 hampir selalu gateway/router lokal
    if hop_num == 1:
        return "router", "📡", "Gateway"
    if _is_private(ip):
        return "router", "📡", "LAN / Router"

    # Hop tengah publik tanpa PTR yang jelas → biasanya router ISP
    if hop_num >= 2:
        return "router", "🔀", "ISP / Router"

    return "unknown", "●", "Host"


def resolve_and_classify(
    ip: str,
    hop_num: int,
    *,
    is_target: bool = False,
) -> tuple[str | None, str, str, str]:
    """Reverse DNS + classify. Returns (hostname, kind, icon, kind_label)."""
    host = reverse_dns(ip)
    kind, icon, label = classify_hop(
        ip=ip,
        hostname=host,
        hop_num=hop_num,
        is_target=is_target,
    )
    return host, kind, icon, label


class TracerouteTopologyRunner:
    """tracert -d ke target; callback per hop untuk digambar sebagai topologi."""

    def __init__(
        self,
        target: str,
        on_line: Callable[[str], None] | None = None,
        on_hop: Callable[[int, str | None, str], None] | None = None,
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.target = target
        self.on_line = on_line
        self.on_hop = on_hop
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
            if self.on_line:
                self.on_line(f"Tracing route to {self.target} …")
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
                if not text:
                    continue
                if self.on_line:
                    self.on_line(text)
                hop = parse_tracert_hop(text)
                if hop and self.on_hop:
                    try:
                        self.on_hop(*hop)
                    except Exception:
                        pass
        except Exception as exc:
            if self.on_line:
                self.on_line(f"Error: {exc}")
        finally:
            self.stop()
            if self.on_done:
                self.on_done()
