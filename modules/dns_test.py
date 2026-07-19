"""DNS leak / resolution style tests."""

from __future__ import annotations

import socket
import subprocess
import threading
from typing import Callable

import dns.resolver


PUBLIC_RESOLVERS = {
    "Google": "8.8.8.8",
    "Cloudflare": "1.1.1.1",
    "OpenDNS": "208.67.222.222",
    "Quad9": "9.9.9.9",
}


def _system_dns_servers() -> list[str]:
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.check_output(
            ["ipconfig", "/all"],
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation,
        )
    except Exception:
        return []

    servers: list[str] = []
    capture = False
    for raw in out.splitlines():
        line = raw.strip()
        lower = line.lower()
        if "dns servers" in lower or "server dns" in lower:
            capture = True
            parts = line.split(":", 1)
            if len(parts) == 2 and parts[1].strip():
                val = parts[1].strip()
                if val and val not in servers:
                    servers.append(val)
            continue
        if capture:
            if line and not any(ch.isalpha() for ch in line.split()[0] if line.split()):
                # continuation indented IP
                if line not in servers and all(c.isdigit() or c == "." or c == ":" for c in line):
                    servers.append(line)
                else:
                    capture = False
            elif ":" in line and not line.lower().startswith("dns"):
                capture = False
            elif line and line[0].isalpha():
                capture = False
    return servers


def _resolve_with(resolver_ip: str | None, domain: str) -> str:
    resolver = dns.resolver.Resolver(configure=False if resolver_ip else True)
    if resolver_ip:
        resolver.nameservers = [resolver_ip]
    resolver.lifetime = 4.0
    answers = resolver.resolve(domain, "A")
    return ", ".join(sorted({rdata.to_text() for rdata in answers}))


class DnsTestRunner:
    def __init__(
        self,
        domains: list[str],
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.domains = domains
        self.on_line = on_line
        self.on_done = on_done
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
            self.on_line("=== DNS TEST / LEAK CHECK ===")
            self.on_line("")
            hostname = socket.gethostname()
            try:
                local_ip = socket.gethostbyname(hostname)
            except Exception:
                local_ip = "unknown"
            self.on_line(f"Hostname     : {hostname}")
            self.on_line(f"Local IP     : {local_ip}")
            self.on_line("")

            system_dns = _system_dns_servers()
            self.on_line("--- System DNS Servers ---")
            if system_dns:
                for dns_ip in system_dns:
                    self.on_line(f"  {dns_ip}")
            else:
                self.on_line("  (tidak terdeteksi via ipconfig)")
            self.on_line("")

            domains = self.domains or ["google.com"]
            self.on_line("--- Resolve via System DNS ---")
            for domain in domains:
                if self._stop.is_set():
                    break
                try:
                    result = _resolve_with(None, domain)
                    self.on_line(f"  {domain:28} -> {result}")
                except Exception as exc:
                    self.on_line(f"  {domain:28} -> ERROR: {exc}")
            self.on_line("")

            self.on_line("--- Resolve via Public Resolvers ---")
            sample = domains[0]
            for name, ip in PUBLIC_RESOLVERS.items():
                if self._stop.is_set():
                    break
                try:
                    result = _resolve_with(ip, sample)
                    self.on_line(f"  [{name:10}] {ip:15} {sample} -> {result}")
                except Exception as exc:
                    self.on_line(f"  [{name:10}] {ip:15} ERROR: {exc}")

            self.on_line("")
            self.on_line("--- Leak Summary ---")
            if system_dns:
                public_set = set(PUBLIC_RESOLVERS.values())
                leaked = [d for d in system_dns if d not in public_set]
                if leaked:
                    self.on_line(
                        "  DNS sistem memakai resolver non-publik "
                        f"(mungkin ISP/router): {', '.join(leaked)}"
                    )
                else:
                    self.on_line(
                        "  DNS sistem memakai resolver publik umum "
                        f"({', '.join(system_dns)})."
                    )
            else:
                self.on_line("  Tidak bisa membandingkan — DNS sistem tidak terbaca.")
            self.on_line("")
            self.on_line("DNS test selesai.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
