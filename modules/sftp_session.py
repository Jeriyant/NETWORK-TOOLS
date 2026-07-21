"""SSH / SFTP / SCP session helpers (paramiko).

Catatan:
- Banyak server (port custom) mengizinkan SSH + SCP tetapi menolak subsystem SFTP.
  Error klasik: "EOF during negotiation" saat buka SFTP.
- Karena itu koneksi SSH dipisah dari SFTP; file ops bisa fallback ke SCP/shell.
"""

from __future__ import annotations

import re
import shlex
import socket
import stat
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import paramiko
from paramiko.ssh_exception import (
    AuthenticationException,
    SSHException,
)

try:
    from scp import SCPClient
except Exception:  # pragma: no cover
    SCPClient = None  # type: ignore[misc, assignment]


@dataclass
class RemoteEntry:
    name: str
    path: str
    is_dir: bool
    size: int
    mtime: float
    mode: int

    @property
    def size_label(self) -> str:
        if self.is_dir:
            return "—"
        n = float(self.size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if n < 1024 or unit == "TB":
                if unit == "B":
                    return f"{int(n)} {unit}"
                return f"{n:.1f} {unit}"
            n /= 1024
        return f"{self.size} B"

    @property
    def mtime_label(self) -> str:
        try:
            return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "—"

    @property
    def type_label(self) -> str:
        return "Folder" if self.is_dir else "File"


def _friendly_connect_error(exc: BaseException, host: str, port: int, banner: str = "") -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    low = msg.lower()
    banner_note = f"\nBanner server: {banner.strip()}" if banner.strip() else ""
    if "eof during negotiation" in low or ("eof" in low and "negotiat" in low):
        return (
            f"Gagal negosiasi ke {host}:{port}.{banner_note}\n\n"
            "Sering terjadi jika:\n"
            "• Subsystem SFTP dimatikan (SSH tetap bisa) — coba protokol SSH/SCP\n"
            "• Algoritma cipher/kex tidak cocok\n"
            "• Firewall/fail2ban memutus handshake\n"
            "• Port bukan daemon SSH\n\n"
            f"Detail: {msg}"
        )
    if isinstance(exc, AuthenticationException) or "auth" in low:
        return (
            f"Autentikasi gagal ke {host}:{port}.\n"
            "Periksa Username / Password.\n\n"
            f"Detail: {msg}"
        )
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in low:
        return (
            f"Timeout menghubungi {host}:{port}.\n"
            "Host tidak merespons / firewall memblokir port.\n\n"
            f"Detail: {msg}"
        )
    if "connection refused" in low or "10061" in low:
        return (
            f"Koneksi ditolak di {host}:{port}.\n"
            "Layanan SSH tidak berjalan atau port salah.\n\n"
            f"Detail: {msg}"
        )
    if "no route" in low or "unreachable" in low or "getaddrinfo" in low:
        return f"Host tidak dapat dijangkau: {host}\n\nDetail: {msg}"
    if "not ssh" in low or "banner" in low:
        return (
            f"Port {port} di {host} tidak merespons sebagai SSH.{banner_note}\n\n"
            f"Detail: {msg}"
        )
    return f"Gagal menghubungkan ke {host}:{port}{banner_note}\n\n{msg}"


def _peek_ssh_banner(host: str, port: int, timeout: float = 8.0) -> str:
    """Baca banner awal; pastikan layanan berbicara SSH."""
    sock: socket.socket | None = None
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
        data = sock.recv(256)
        text = (data or b"").decode("utf-8", errors="replace").strip()
        return text
    except Exception as exc:
        return f"(gagal baca banner: {exc})"
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


class SftpSession:
    """SSH session dengan SFTP opsional + fallback SCP/shell."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._client: paramiko.SSHClient | None = None
        self._transport: paramiko.Transport | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self.host = ""
        self.port = 22
        self.username = ""
        self.cwd = "/"
        self.history: list[str] = []
        self.protocol = "SFTP"
        self.sftp_ok = False
        self.last_banner = ""
        self.connect_note = ""

    @property
    def connected(self) -> bool:
        tr = self._transport
        return tr is not None and tr.is_active()

    def connect(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float = 35.0,
        protocol: str = "SFTP",
    ) -> None:
        host = (host or "").strip()
        username = (username or "").strip()
        if not host:
            raise ValueError("Host/IP wajib diisi")
        if not username:
            raise ValueError("Username wajib diisi")
        port = int(port or 22)
        password = password or ""
        protocol = (protocol or "SFTP").strip().upper()
        self.disconnect()

        banner = _peek_ssh_banner(host, port, timeout=min(timeout, 10.0))
        self.last_banner = banner
        # Hanya tolak jika jelas bukan SSH (mis. HTTP). Gagal baca banner tidak membatalkan.
        if (
            banner
            and not banner.startswith("(gagal")
            and not banner.upper().startswith("SSH-")
        ):
            raise ConnectionError(
                _friendly_connect_error(
                    RuntimeError(f"Respons bukan SSH banner: {banner[:120]}"),
                    host,
                    port,
                    banner,
                )
            )

        attempts: list[dict[str, Any]] = [
            {"label": "default", "disabled_algorithms": None, "fake_openssh": True, "want_sftp": True},
            {
                "label": "legacy-rsa",
                "disabled_algorithms": {"pubkeys": ["rsa-sha2-256", "rsa-sha2-512"]},
                "fake_openssh": True,
                "want_sftp": True,
            },
            {
                "label": "legacy-kex",
                "disabled_algorithms": {
                    "pubkeys": ["rsa-sha2-256", "rsa-sha2-512"],
                    "kex": [
                        "ecdh-sha2-nistp256",
                        "ecdh-sha2-nistp384",
                        "ecdh-sha2-nistp521",
                        "curve25519-sha256",
                        "curve25519-sha256@libssh.org",
                    ],
                },
                "fake_openssh": True,
                "want_sftp": True,
            },
            {"label": "paramiko-banner", "disabled_algorithms": None, "fake_openssh": False, "want_sftp": True},
            {
                "label": "sshclient",
                "use_sshclient": True,
                "disabled_algorithms": {"pubkeys": ["rsa-sha2-256", "rsa-sha2-512"]},
                "fake_openssh": True,
                "want_sftp": True,
            },
            # Terakhir: SSH saja jika SFTP memutus koneksi (EOF)
            {"label": "ssh-only", "disabled_algorithms": None, "fake_openssh": True, "want_sftp": False},
        ]

        last_exc: BaseException | None = None
        for attempt in attempts:
            try:
                want_sftp = bool(attempt.get("want_sftp", True))
                if attempt.get("use_sshclient"):
                    client, transport, sftp, cwd, note = self._connect_via_sshclient(
                        host=host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=timeout,
                        disabled_algorithms=attempt.get("disabled_algorithms"),
                        want_sftp=want_sftp,
                        protocol=protocol,
                    )
                else:
                    client, transport, sftp, cwd, note = self._connect_via_transport(
                        host=host,
                        port=port,
                        username=username,
                        password=password,
                        timeout=timeout,
                        disabled_algorithms=attempt.get("disabled_algorithms"),
                        fake_openssh=bool(attempt.get("fake_openssh")),
                        want_sftp=want_sftp,
                        protocol=protocol,
                    )
                with self._lock:
                    self._client = client
                    self._transport = transport
                    self._sftp = sftp
                    self.sftp_ok = sftp is not None
                    self.host = host
                    self.port = port
                    self.username = username
                    self.cwd = cwd
                    self.history = []
                    self.protocol = protocol
                    self.connect_note = note
                return
            except Exception as exc:
                last_exc = exc
                continue

        detail = last_exc if last_exc is not None else RuntimeError("unknown")
        raise ConnectionError(
            _friendly_connect_error(detail, host, port, self.last_banner)
        ) from last_exc

    def _connect_via_sshclient(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float,
        disabled_algorithms: dict[str, list[str]] | None,
        want_sftp: bool,
        protocol: str,
    ) -> tuple[paramiko.SSHClient, paramiko.Transport, paramiko.SFTPClient | None, str, str]:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict[str, Any] = {
            "hostname": host,
            "port": port,
            "username": username,
            "password": password,
            "timeout": timeout,
            "allow_agent": False,
            "look_for_keys": False,
            "banner_timeout": max(timeout, 45.0),
            "auth_timeout": max(timeout, 45.0),
            "channel_timeout": max(timeout, 45.0),
        }
        if disabled_algorithms:
            kwargs["disabled_algorithms"] = disabled_algorithms
        client.connect(**kwargs)
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            try:
                client.close()
            except Exception:
                pass
            raise SSHException("SSHClient connect OK tapi transport tidak aktif")
        transport.set_keepalive(30)
        sftp, note = self._open_file_channel(transport, timeout, want_sftp, protocol)
        cwd = self._resolve_cwd(sftp, transport)
        return client, transport, sftp, cwd, note

    def _connect_via_transport(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: float,
        disabled_algorithms: dict[str, list[str]] | None,
        fake_openssh: bool,
        want_sftp: bool,
        protocol: str,
    ) -> tuple[paramiko.SSHClient, paramiko.Transport, paramiko.SFTPClient | None, str, str]:
        sock = socket.create_connection((host, port), timeout=timeout)
        try:
            sock.settimeout(timeout)
        except Exception:
            pass

        transport = paramiko.Transport(sock, disabled_algorithms=disabled_algorithms or {})
        transport.banner_timeout = max(timeout, 45.0)
        transport.auth_timeout = max(timeout, 45.0)
        if fake_openssh:
            transport.local_version = "SSH-2.0-OpenSSH_9.6"

        try:
            transport.start_client(timeout=timeout)
        except Exception:
            try:
                transport.close()
            except Exception:
                pass
            raise

        if not transport.is_active():
            try:
                transport.close()
            except Exception:
                pass
            raise SSHException("Transport SSH tidak aktif setelah start_client")

        transport.set_keepalive(30)
        self._authenticate(transport, username, password)

        sftp, note = self._open_file_channel(transport, timeout, want_sftp, protocol)
        cwd = self._resolve_cwd(sftp, transport)

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client._transport = transport  # type: ignore[attr-defined]
        return client, transport, sftp, cwd, note

    def _open_file_channel(
        self,
        transport: paramiko.Transport,
        timeout: float,
        want_sftp: bool,
        protocol: str,
    ) -> tuple[paramiko.SFTPClient | None, str]:
        """Selalu coba SFTP agar explorer terisi; SSH command tetap tersedia.

        Jika SFTP gagal (EOF subsystem), session SSH tetap hidup + fallback shell/SCP.
        """
        if not want_sftp:
            return None, f"Mode {protocol} — tanpa SFTP"
        return self._try_open_sftp(transport, timeout)

    def _authenticate(
        self, transport: paramiko.Transport, username: str, password: str
    ) -> None:
        authed = False
        auth_errors: list[str] = []

        # Beberapa server butuh none-auth dulu
        try:
            transport.auth_none(username)
        except Exception:
            pass

        try:
            transport.auth_password(username, password)
            authed = True
        except Exception as e1:
            auth_errors.append(f"password: {e1}")

        if not authed:

            def _kb_handler(
                _title: str,
                _instructions: str,
                prompt_list: list[tuple[str, bool]],
            ) -> list[str]:
                return [password for _p, _echo in prompt_list]

            try:
                transport.auth_interactive(username, _kb_handler)
                authed = True
            except Exception as e2:
                auth_errors.append(f"keyboard-interactive: {e2}")

        if not authed:
            raise AuthenticationException(
                " / ".join(auth_errors) if auth_errors else "Authentication failed"
            )

    def _try_open_sftp(
        self, transport: paramiko.Transport, timeout: float
    ) -> tuple[paramiko.SFTPClient | None, str]:
        errors: list[str] = []
        # from_transport
        try:
            sftp = paramiko.SFTPClient.from_transport(transport)
            if sftp is not None:
                # smoke-test: listdir home
                try:
                    sftp.listdir(".")
                except Exception as smoke:
                    try:
                        sftp.close()
                    except Exception:
                        pass
                    raise smoke
                return sftp, "SFTP siap (dual dengan SSH)"
        except Exception as exc:
            errors.append(str(exc))

        # channel subsystem
        try:
            chan = transport.open_session(timeout=timeout)
            chan.invoke_subsystem("sftp")
            time.sleep(0.2)
            sftp = paramiko.SFTPClient(chan)
            try:
                sftp.listdir(".")
            except Exception as smoke:
                try:
                    sftp.close()
                except Exception:
                    pass
                raise smoke
            return sftp, "SFTP siap via channel (dual dengan SSH)"
        except Exception as exc:
            errors.append(str(exc))

        detail = "; ".join(errors) if errors else "unknown"
        if not transport.is_active():
            raise SSHException(f"Transport mati setelah SFTP gagal: {detail}")
        return None, f"SFTP gagal ({detail}) — explorer pakai shell/SCP, SSH tetap aktif"

    def _resolve_cwd(
        self, sftp: paramiko.SFTPClient | None, transport: paramiko.Transport
    ) -> str:
        if sftp is not None:
            try:
                return sftp.normalize(".")
            except Exception:
                try:
                    return sftp.getcwd() or "/"
                except Exception:
                    pass
        # shell pwd / echo $HOME / echo /
        try:
            _code, out, _err = self._exec_on_transport(
                transport, "pwd 2>/dev/null; echo; echo \"$HOME\"; echo /"
            )
            for line in (out or "").splitlines():
                line = line.strip()
                if line.startswith("/") and len(line) < 512:
                    return line
        except Exception:
            pass
        return "/"

    def _exec_on_transport(
        self,
        transport: paramiko.Transport,
        command: str,
        timeout: float = 60.0,
    ) -> tuple[int, str, str]:
        chan = transport.open_session(timeout=timeout)
        try:
            chan.set_combine_stderr(False)
        except Exception:
            pass
        chan.settimeout(timeout)
        chan.exec_command(command)
        out_chunks: list[str] = []
        err_chunks: list[str] = []
        deadline = time.time() + timeout
        while time.time() < deadline:
            got = False
            if chan.recv_ready():
                out_chunks.append(chan.recv(8192).decode("utf-8", errors="replace"))
                got = True
            if chan.recv_stderr_ready():
                err_chunks.append(chan.recv_stderr(8192).decode("utf-8", errors="replace"))
                got = True
            if chan.exit_status_ready() and not chan.recv_ready() and not chan.recv_stderr_ready():
                break
            if not got:
                time.sleep(0.05)
        code = chan.recv_exit_status()
        try:
            chan.close()
        except Exception:
            pass
        return code, "".join(out_chunks), "".join(err_chunks)

    def list_dir(self, path: str | None = None) -> list[RemoteEntry]:
        path = path or self.cwd or "/"
        if self._sftp is not None:
            try:
                return self._list_sftp(path)
            except Exception:
                # SFTP putus di tengah jalan → fallback shell
                pass
        return self._list_shell(path)

    def _list_sftp(self, path: str) -> list[RemoteEntry]:
        sftp = self._sftp
        assert sftp is not None
        with self._lock:
            attrs = sftp.listdir_attr(path)
        entries: list[RemoteEntry] = []
        for a in attrs:
            name = a.filename
            if name in (".", ".."):
                continue
            mode = int(getattr(a, "st_mode", 0) or 0)
            is_dir = stat.S_ISDIR(mode)
            full = path.rstrip("/") + "/" + name if path != "/" else "/" + name
            entries.append(
                RemoteEntry(
                    name=name,
                    path=full,
                    is_dir=is_dir,
                    size=int(getattr(a, "st_size", 0) or 0),
                    mtime=float(getattr(a, "st_mtime", 0) or 0),
                    mode=mode,
                )
            )
        entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        return entries

    def _list_shell(self, path: str) -> list[RemoteEntry]:
        """Fallback listing via shell jika SFTP tidak ada."""
        tr = self._require_transport()
        q = shlex.quote(path)
        # Beberapa busybox tidak dukung --time-style
        cmds = [
            f"ls -la --time-style=long-iso {q}",
            f"ls -la {q}",
            f"ls -1Ap {q}",
            f"ls -1 {q}",
        ]
        text = ""
        with self._lock:
            for cmd in cmds:
                code, out, err = self._exec_on_transport(tr, f"{cmd} 2>&1")
                blob = (out or "") + (err or "")
                if blob.strip() and "No such file" not in blob and "cannot access" not in blob:
                    text = blob
                    break
                if not text:
                    text = blob

        entries: list[RemoteEntry] = []
        # Format panjang klasik GNU/BusyBox
        pat_long = re.compile(
            r"^([d\-lbcps])"
            r"([rwxsStT\-]{9})\s+"
            r"\d+\s+\S+\s+\S+\s+"
            r"(\d+)\s+"
            r"(?:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}|\S+\s+\d+\s+[\d:]+)\s+"
            r"(.+)$"
        )
        for line in text.splitlines():
            line = line.rstrip()
            if not line or line.lower().startswith("total "):
                continue
            m = pat_long.match(line)
            if m:
                kind = m.group(1)
                size = int(m.group(3))
                name = m.group(4).strip()
                if " -> " in name:
                    name = name.split(" -> ", 1)[0].strip()
                if name in (".", ".."):
                    continue
                is_dir = kind == "d"
                full = path.rstrip("/") + "/" + name if path != "/" else "/" + name
                entries.append(
                    RemoteEntry(
                        name=name,
                        path=full,
                        is_dir=is_dir,
                        size=size,
                        mtime=0.0,
                        mode=0,
                    )
                )
                continue
            # Format singkat: name atau name/
            name = line.strip()
            if not name or name in (".", ".."):
                continue
            if name.startswith("ls:"):
                continue
            is_dir = name.endswith("/")
            name = name.rstrip("/")
            if not name or name in (".", ".."):
                continue
            full = path.rstrip("/") + "/" + name if path != "/" else "/" + name
            entries.append(
                RemoteEntry(
                    name=name,
                    path=full,
                    is_dir=is_dir,
                    size=0,
                    mtime=0.0,
                    mode=0,
                )
            )
        # dedupe by name
        seen: set[str] = set()
        uniq: list[RemoteEntry] = []
        for e in entries:
            if e.name in seen:
                continue
            seen.add(e.name)
            uniq.append(e)
        uniq.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        return uniq

    def disconnect(self) -> None:
        with self._lock:
            if self._sftp is not None:
                try:
                    self._sftp.close()
                except Exception:
                    pass
                self._sftp = None
            if self._client is not None:
                try:
                    self._client._transport = None  # type: ignore[attr-defined]
                    self._client.close()
                except Exception:
                    pass
                self._client = None
            if self._transport is not None:
                try:
                    self._transport.close()
                except Exception:
                    pass
                self._transport = None
            self.cwd = "/"
            self.history = []
            self.sftp_ok = False
            self.connect_note = ""

    def _require_transport(self) -> paramiko.Transport:
        tr = self._transport
        if tr is None or not tr.is_active():
            raise RuntimeError("Belum terhubung")
        return tr

    def _join(self, name: str) -> str:
        base = self.cwd.rstrip("/") or ""
        name = name.strip().strip("/")
        if not name:
            return self.cwd or "/"
        if name.startswith("/"):
            return name
        return f"{base}/{name}" if base else f"/{name}"

    def chdir(self, path: str, *, record_history: bool = True) -> str:
        path = (path or "/").strip() or "/"
        if self._sftp is not None:
            with self._lock:
                norm = self._sftp.normalize(path)
                self._sftp.listdir(norm)
                if record_history and self.cwd and self.cwd != norm:
                    self.history.append(self.cwd)
                self.cwd = norm
                return self.cwd

        # shell: cd + pwd
        tr = self._require_transport()
        q = shlex.quote(path)
        with self._lock:
            code, out, err = self._exec_on_transport(
                tr, f"cd {q} && pwd"
            )
        if code != 0:
            raise SSHException((err or out or f"cd gagal: {path}").strip())
        norm = "/"
        for line in (out or "").splitlines():
            line = line.strip()
            if line.startswith("/"):
                norm = line
                break
        if record_history and self.cwd and self.cwd != norm:
            self.history.append(self.cwd)
        self.cwd = norm
        return self.cwd

    def go_up(self) -> str:
        cur = self.cwd or "/"
        if cur in ("/", ""):
            return cur
        parent = cur.rsplit("/", 1)[0] or "/"
        return self.chdir(parent, record_history=True)

    def go_back(self) -> str | None:
        if not self.history:
            return None
        prev = self.history.pop()
        return self.chdir(prev, record_history=False)

    def mkdir(self, name: str) -> str:
        path = self._join(name)
        if self._sftp is not None:
            with self._lock:
                self._sftp.mkdir(path)
            return path
        tr = self._require_transport()
        with self._lock:
            code, out, err = self._exec_on_transport(tr, f"mkdir -p {shlex.quote(path)}")
        if code != 0:
            raise SSHException((err or out or "mkdir gagal").strip())
        return path

    def create_file(self, name: str, content: bytes = b"") -> str:
        path = self._join(name)
        if self._sftp is not None:
            with self._lock:
                with self._sftp.file(path, "wb") as f:
                    if content:
                        f.write(content)
            return path
        # shell touch / printf
        tr = self._require_transport()
        with self._lock:
            code, out, err = self._exec_on_transport(tr, f"touch {shlex.quote(path)}")
        if code != 0:
            raise SSHException((err or out or "create file gagal").strip())
        return path

    def remove(self, path: str) -> None:
        if self._sftp is not None:
            sftp = self._sftp
            with self._lock:
                try:
                    st = sftp.stat(path)
                    if stat.S_ISDIR(int(st.st_mode or 0)):
                        self._rmtree(sftp, path)
                    else:
                        sftp.remove(path)
                except IOError:
                    try:
                        sftp.remove(path)
                    except Exception:
                        self._rmtree(sftp, path)
            return
        tr = self._require_transport()
        with self._lock:
            code, out, err = self._exec_on_transport(tr, f"rm -rf {shlex.quote(path)}")
        if code != 0:
            raise SSHException((err or out or "hapus gagal").strip())

    def _rmtree(self, sftp: paramiko.SFTPClient, path: str) -> None:
        for a in sftp.listdir_attr(path):
            name = a.filename
            if name in (".", ".."):
                continue
            child = path.rstrip("/") + "/" + name
            mode = int(getattr(a, "st_mode", 0) or 0)
            if stat.S_ISDIR(mode):
                self._rmtree(sftp, child)
            else:
                sftp.remove(child)
        sftp.rmdir(path)

    def rename(self, old_path: str, new_name: str) -> str:
        new_name = new_name.strip().strip("/")
        parent = old_path.rsplit("/", 1)[0] or "/"
        new_path = (parent.rstrip("/") + "/" + new_name) if parent != "/" else "/" + new_name
        if self._sftp is not None:
            with self._lock:
                self._sftp.rename(old_path, new_path)
            return new_path
        tr = self._require_transport()
        with self._lock:
            code, out, err = self._exec_on_transport(
                tr, f"mv {shlex.quote(old_path)} {shlex.quote(new_path)}"
            )
        if code != 0:
            raise SSHException((err or out or "rename gagal").strip())
        return new_path

    def download(self, remote_path: str, local_path: str | Path) -> None:
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if self._sftp is not None:
            with self._lock:
                self._sftp.get(remote_path, str(local_path))
            return
        self._scp_get(remote_path, str(local_path))

    def upload(self, local_path: str | Path, remote_name: str | None = None) -> str:
        local_path = Path(local_path)
        name = remote_name or local_path.name
        remote = self._join(name)
        if self._sftp is not None:
            with self._lock:
                self._sftp.put(str(local_path), remote)
            return remote
        self._scp_put(str(local_path), remote)
        return remote

    def _scp_put(self, local_path: str, remote_path: str) -> None:
        tr = self._require_transport()
        if SCPClient is None:
            raise RuntimeError("Modul scp tidak tersedia untuk fallback upload")
        with self._lock:
            with SCPClient(tr) as scp:
                scp.put(local_path, remote_path)

    def _scp_get(self, remote_path: str, local_path: str) -> None:
        tr = self._require_transport()
        if SCPClient is None:
            raise RuntimeError("Modul scp tidak tersedia untuk fallback download")
        with self._lock:
            with SCPClient(tr) as scp:
                scp.get(remote_path, local_path)

    def exec_command(
        self,
        command: str,
        on_line: Callable[[str], None] | None = None,
        timeout: float = 120.0,
    ) -> tuple[int, str, str]:
        cmd = (command or "").strip()
        if not cmd:
            return 0, "", ""
        with self._lock:
            transport = self._require_transport()
            chan = transport.open_session(timeout=timeout)
            chan.settimeout(timeout)
            chan.exec_command(cmd)
            out_chunks: list[str] = []
            err_chunks: list[str] = []
            while True:
                if chan.recv_ready():
                    data = chan.recv(4096).decode("utf-8", errors="replace")
                    for line in data.splitlines():
                        out_chunks.append(line)
                        if on_line:
                            on_line(line)
                if chan.recv_stderr_ready():
                    data = chan.recv_stderr(4096).decode("utf-8", errors="replace")
                    for line in data.splitlines():
                        err_chunks.append(line)
                        if on_line and line:
                            on_line(f"[stderr] {line}")
                if (
                    chan.exit_status_ready()
                    and not chan.recv_ready()
                    and not chan.recv_stderr_ready()
                ):
                    break
            code = chan.recv_exit_status()
            try:
                chan.close()
            except Exception:
                pass
        return code, "\n".join(out_chunks), "\n".join(err_chunks)

    def write_text_file(self, path: str, text: str) -> None:
        data = (text or "").encode("utf-8")
        if self._sftp is not None:
            with self._lock:
                with self._sftp.file(path, "wb") as f:
                    f.write(data)
            return
        # fallback: printf via shell (aman untuk file kecil)
        tr = self._require_transport()
        # base64 agar aman
        import base64

        b64 = base64.b64encode(data).decode("ascii")
        cmd = f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(path)}"
        with self._lock:
            code, out, err = self._exec_on_transport(tr, cmd)
        if code != 0:
            raise SSHException((err or out or "write gagal").strip())

    def read_text_preview(self, path: str, max_bytes: int = 64_000) -> str:
        if self._sftp is not None:
            with self._lock:
                with self._sftp.file(path, "rb") as f:
                    data = f.read(max_bytes)
            try:
                return data.decode("utf-8")
            except Exception:
                return data.decode("utf-8", errors="replace")
        tr = self._require_transport()
        with self._lock:
            _code, out, _err = self._exec_on_transport(
                tr, f"head -c {int(max_bytes)} {shlex.quote(path)}"
            )
        return out or ""
