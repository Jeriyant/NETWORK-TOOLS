"""Disable/enable NIC or renew DHCP lease."""

from __future__ import annotations

import subprocess
import threading
from typing import Callable


def _run_ps(command: str) -> tuple[int, str]:
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation,
    )
    out = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, out.strip()


def _run_cmd(args: list[str]) -> tuple[int, str]:
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    completed = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation,
    )
    out = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, out.strip()


def list_net_adapters() -> list[dict[str, str]]:
    """Daftar adapter mirip ncpa.cpl: name, status, mac, speed."""
    code, out = _run_ps(
        "Get-NetAdapter | Select-Object Name, Status, MacAddress, LinkSpeed, "
        "InterfaceDescription | ConvertTo-Json -Compress"
    )
    if code != 0 or not out.strip():
        return []
    import json

    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    rows: list[dict[str, str]] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "name": str(item.get("Name") or ""),
                "status": str(item.get("Status") or ""),
                "mac": str(item.get("MacAddress") or ""),
                "speed": str(item.get("LinkSpeed") or ""),
                "desc": str(item.get("InterfaceDescription") or ""),
            }
        )
    rows.sort(key=lambda r: (0 if r["status"].lower() == "up" else 1, r["name"].lower()))
    return rows


def get_adapter_details(name: str) -> dict[str, str]:
    """Detail adapter untuk dialog Status/Informasi (termasuk DNS)."""
    n = (name or "").replace('"', "")
    if not n:
        return {}
    code, out = _run_ps(
        f'$a = Get-NetAdapter -Name "{n}" -ErrorAction SilentlyContinue; '
        "if (-not $a) { '{}' ; exit }; "
        "$ip = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "$gw = Get-NetRoute -InterfaceIndex $a.ifIndex -DestinationPrefix '0.0.0.0/0' "
        "-ErrorAction SilentlyContinue | Select-Object -First 1; "
        "$dns = @(Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex "
        "-AddressFamily IPv4 -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.ServerAddresses } | Where-Object { $_ }); "
        "[pscustomobject]@{ "
        "Name=$a.Name; Status=$a.Status; MacAddress=$a.MacAddress; "
        "LinkSpeed=$a.LinkSpeed; InterfaceDescription=$a.InterfaceDescription; "
        "ifIndex=$a.ifIndex; MediaType=$a.MediaType; "
        "IPv4=($(if($ip){$ip.IPAddress}else{''})); "
        "Prefix=($(if($ip){$ip.PrefixLength}else{''})); "
        "Gateway=($(if($gw){$gw.NextHop}else{''})); "
        "DNS=($dns -join ', ') "
        "} | ConvertTo-Json -Compress"
    )
    if code != 0 or not out.strip():
        return {"name": n}
    import json

    try:
        start = out.find("{")
        if start >= 0:
            out = out[start:]
        data = json.loads(out)
    except Exception:
        return {"name": n}
    if not isinstance(data, dict):
        return {"name": n}
    return {
        "name": str(data.get("Name") or n),
        "status": str(data.get("Status") or ""),
        "mac": str(data.get("MacAddress") or ""),
        "speed": str(data.get("LinkSpeed") or ""),
        "desc": str(data.get("InterfaceDescription") or ""),
        "ifindex": str(data.get("ifIndex") or ""),
        "media": str(data.get("MediaType") or ""),
        "ipv4": str(data.get("IPv4") or ""),
        "prefix": str(data.get("Prefix") or ""),
        "gateway": str(data.get("Gateway") or ""),
        "dns": str(data.get("DNS") or ""),
    }


def set_adapter_enabled(name: str, enabled: bool) -> tuple[bool, str]:
    """Enable/Disable-NetAdapter. Return (ok, message)."""
    n = (name or "").replace('"', "")
    if not n:
        return False, "Nama adapter kosong."
    cmd = "Enable-NetAdapter" if enabled else "Disable-NetAdapter"
    code, out = _run_ps(f'{cmd} -Name "{n}" -Confirm:$false')
    if code == 0:
        return True, out or f"{'Enable' if enabled else 'Disable'} OK: {n}"
    return False, out or f"Gagal {cmd} (mungkin butuh Administrator)."


def open_adapter_properties(name: str = "") -> tuple[bool, str]:
    """Buka jendela Network Connections (ncpa.cpl) / properti adapter."""
    creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        # ncpa.cpl — user bisa klik kanan Properti pada adapter
        subprocess.Popen(
            ["control.exe", "ncpa.cpl"],
            shell=False,
            creationflags=creation,
        )
        hint = f"Buka Properti pada “{name}” di Network Connections." if name else "Network Connections dibuka."
        return True, hint
    except Exception as exc:
        return False, str(exc)


class RefreshNetworkRunner:
    def __init__(
        self,
        adapter_name: str,
        on_line: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
    ) -> None:
        self.adapter_name = (adapter_name or "").strip()
        self.on_line = on_line
        self.on_done = on_done
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _pick_adapter(self) -> str | None:
        if self.adapter_name:
            return self.adapter_name

        code, out = _run_ps(
            "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | "
            "Select-Object -ExpandProperty Name"
        )
        if code != 0 or not out:
            return None
        lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
        return lines[0] if lines else None

    def _run(self) -> None:
        try:
            self.on_line("=== REFRESH NETWORK ===")
            self.on_line("")
            adapter = self._pick_adapter()
            if adapter:
                self.on_line(f"Adapter: {adapter}")
                self.on_line("Menonaktifkan adapter...")
                code, out = _run_ps(f'Disable-NetAdapter -Name "{adapter}" -Confirm:$false')
                if out:
                    self.on_line(out)
                if code != 0:
                    self.on_line("Disable gagal (mungkin butuh Run as Administrator).")

                self.on_line("Mengaktifkan kembali adapter...")
                code, out = _run_ps(f'Enable-NetAdapter -Name "{adapter}" -Confirm:$false')
                if out:
                    self.on_line(out)
                if code != 0:
                    self.on_line("Enable gagal (mungkin butuh Run as Administrator).")
            else:
                self.on_line("Adapter tidak ditemukan — lanjut renew DHCP saja.")

            self.on_line("")
            self.on_line("Melepaskan IP (ipconfig /release)...")
            code, out = _run_cmd(["ipconfig", "/release"])
            if out:
                self.on_line(out)

            self.on_line("Meminta IP baru (ipconfig /renew)...")
            code, out = _run_cmd(["ipconfig", "/renew"])
            if out:
                self.on_line(out)

            self.on_line("Flush DNS (ipconfig /flushdns)...")
            code, out = _run_cmd(["ipconfig", "/flushdns"])
            if out:
                self.on_line(out)

            self.on_line("")
            self.on_line("Refresh network selesai.")
        except Exception as exc:
            self.on_line(f"Error: {exc}")
        finally:
            if self.on_done:
                self.on_done()
