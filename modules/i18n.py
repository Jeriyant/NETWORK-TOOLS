"""Simple ID/EN localization. Default language: Indonesian."""

from __future__ import annotations

from typing import Any

DEFAULT_LANG = "id"
LANGS = ("id", "en")

_LANG = DEFAULT_LANG

# key -> {id, en}
_STRINGS: dict[str, dict[str, str]] = {
    # App
    "app.title": {"id": "Network Tools  v{version}", "en": "Network Tools  v{version}"},
    "app.brand": {"id": "NETWORK TOOLS", "en": "NETWORK TOOLS"},
    "app.tagline": {
        "id": "Untilitas IT - Tools Professional IT Networking CUSJ",
        "en": "Untilitas IT - Tools Professional IT Networking CUSJ",
    },
    "app.open": {"id": "Buka", "en": "Open"},
    "app.back": {"id": "Kembali", "en": "Back"},
    "app.send": {"id": "Kirim", "en": "Send"},
    "app.refresh": {"id": "Refresh", "en": "Refresh"},
    "app.recheck": {"id": "Cek Ulang", "en": "Recheck"},
    "app.reload": {"id": "Muat Ulang", "en": "Reload"},
    "app.page_loading": {"id": "Memuat halaman…", "en": "Loading page…"},
    "app.startup_loading": {
        "id": "Memuat informasi sistem…",
        "en": "Loading system info…",
    },
    "trace.loading": {
        "id": "Menjalankan Traceroute, Harap Tunggu",
        "en": "Running Traceroute, please wait",
    },
    "app.start_scan": {"id": "Mulai Scan", "en": "Start Scan"},
    "app.stop": {"id": "Stop", "en": "Stop"},
    "app.run": {"id": "Jalankan", "en": "Run"},
    "app.select_host": {"id": "Pilih host:", "en": "Select host:"},
    "app.start_ping": {"id": "Mulai", "en": "Start"},
    "app.start_trace": {"id": "Mulai", "en": "Start"},
    # Theme / language
    "theme.system": {"id": "Tema: Windows", "en": "Theme: Windows"},
    "theme.light": {"id": "Tema: Light", "en": "Theme: Light"},
    "theme.dark": {"id": "Tema: Dark", "en": "Theme: Dark"},
    "theme.neon_magenta": {"id": "Tema: Neon Magenta", "en": "Theme: Neon Magenta"},
    "lang.id": {"id": "Bahasa: Indonesia", "en": "Language: Indonesian"},
    "lang.en": {"id": "Bahasa: English", "en": "Language: English"},
    # Sysinfo
    "sys.host": {"id": "HOST", "en": "HOST"},
    "sys.ip": {"id": "IP", "en": "IP"},
    "sys.latency": {"id": "LATENSI", "en": "LATENCY"},
    "sys.cpu": {"id": "CPU", "en": "CPU"},
    "sys.ram": {"id": "RAM", "en": "RAM"},
    "sys.uptime": {"id": "UPTIME", "en": "UPTIME"},
    "sys.windows": {"id": "WINDOWS", "en": "WINDOWS"},
    # Tools
    "tool.ping.title": {"id": "Ping", "en": "Ping"},
    "tool.ping.desc": {
        "id": "Ping live ke semua host — kartu status online/RTO",
        "en": "Live ping to all hosts — online/RTO status cards",
    },
    "tool.traceroute.title": {"id": "Traceroute", "en": "Traceroute"},
    "tool.traceroute.desc": {
        "id": "Traceroute ke 8.8.8.8 + peta topologi jalur",
        "en": "Traceroute to 8.8.8.8 with path topology map",
    },
    "tool.speedtest.title": {"id": "Speedtest", "en": "Speedtest"},
    "tool.speedtest.desc": {
        "id": "Uji kecepatan unduh/unggah internet",
        "en": "Test download/upload internet speed",
    },
    "tool.dns.title": {"id": "DNS Test", "en": "DNS Test"},
    "tool.dns.desc": {
        "id": "Cek kebocoran DNS (DNS leak test)",
        "en": "Check for DNS leaks",
    },
    "tool.ipscan.title": {"id": "IP Scanner", "en": "IP Scanner"},
    "tool.ipscan.desc": {
        "id": "Scan host hidup di subnet lokal",
        "en": "Scan live hosts on the local subnet",
    },
    "tool.apps.title": {"id": "Daftar Aplikasi", "en": "Installed Apps"},
    "tool.apps.desc": {
        "id": "Lihat & uninstall aplikasi Windows",
        "en": "View & uninstall Windows applications",
    },
    "tool.security.title": {"id": "Cek Keamanan", "en": "Security Check"},
    "tool.security.desc": {
        "id": "Status Firewall, Defender & Update",
        "en": "Firewall, Defender & Update status",
    },
    "tool.refresh.title": {"id": "Network", "en": "Network"},
    "tool.refresh.desc": {
        "id": "Info adapter, enable/disable & Fix Network",
        "en": "Adapter info, enable/disable & Fix Network",
    },
    "network.loading": {
        "id": "Memuat adapter jaringan…",
        "en": "Loading network adapters…",
    },
    "network.empty": {
        "id": "Tidak ada adapter terdeteksi.",
        "en": "No adapters detected.",
    },
    "network.count": {
        "id": "{n} adapter jaringan",
        "en": "{n} network adapters",
    },
    "network.fix": {"id": "Fix Network", "en": "Fix Network"},
    "network.fixing": {
        "id": "Memperbaiki jaringan…",
        "en": "Fixing network…",
    },
    "network.enable": {"id": "Enable", "en": "Enable"},
    "network.disable": {"id": "Disable", "en": "Disable"},
    "network.properties": {"id": "Properti", "en": "Properties"},
    "network.status": {"id": "Status / Informasi", "en": "Status / Info"},
    "network.info.name": {"id": "Nama", "en": "Name"},
    "network.info.status": {"id": "Status", "en": "Status"},
    "network.info.desc": {"id": "Deskripsi", "en": "Description"},
    "network.info.mac": {"id": "MAC", "en": "MAC"},
    "network.info.speed": {"id": "Speed", "en": "Speed"},
    "network.info.media": {"id": "Media", "en": "Media"},
    "network.info.ipv4": {"id": "IPv4", "en": "IPv4"},
    "network.info.gateway": {"id": "Gateway", "en": "Gateway"},
    "network.info.dns": {"id": "DNS", "en": "DNS"},
    "network.info.copy": {"id": "Salin semua", "en": "Copy all"},
    "network.info.copied": {"id": "Disalin ke clipboard.", "en": "Copied to clipboard."},
    "network.info.close": {"id": "Tutup", "en": "Close"},
    "tool.printer.title": {"id": "Printer", "en": "Printer"},
    "tool.printer.desc": {
        "id": "Daftar driver + clear spooler (Fix Printer)",
        "en": "Driver list + clear spooler (Fix Printer)",
    },
    "printer.loading": {
        "id": "Memuat driver printer…",
        "en": "Loading printer drivers…",
    },
    "printer.count": {
        "id": "{n} driver printer terinstall",
        "en": "{n} printer drivers installed",
    },
    "printer.empty": {
        "id": "Tidak ada driver printer terdeteksi.",
        "en": "No printer drivers detected.",
    },
    "printer.fail": {"id": "Gagal memuat daftar driver", "en": "Failed to load drivers"},
    "printer.fix": {"id": "Fix Printer", "en": "Fix Printer"},
    "printer.col.name": {"id": "NAMA DRIVER", "en": "DRIVER NAME"},
    "printer.col.mfr": {"id": "MANUFACTURER", "en": "MANUFACTURER"},
    "printer.col.env": {"id": "ENVIRONMENT", "en": "ENVIRONMENT"},
    "printer.col.ver": {"id": "VERSI", "en": "VERSION"},
    "printer.fixing": {
        "id": "Membersihkan spooler printer…",
        "en": "Clearing printer spooler…",
    },
    "printer.fix_need_select": {
        "id": "Pilih driver printer di daftar terlebih dahulu.",
        "en": "Select a printer driver in the list first.",
    },
    "printer.uninstall": {"id": "Uninstall", "en": "Uninstall"},
    "printer.reinstall": {"id": "Reinstall", "en": "Reinstall"},
    "printer.confirm_uninstall": {
        "id": "Uninstall driver printer “{name}”?\nPrinter yang memakai driver ini juga akan dihapus.",
        "en": "Uninstall printer driver “{name}”?\nPrinters using this driver will also be removed.",
    },
    "printer.confirm_reinstall": {
        "id": "Reinstall driver “{name}”?",
        "en": "Reinstall driver “{name}”?",
    },
    "printer.select": {
        "id": "Pilih driver terlebih dahulu.",
        "en": "Select a driver first.",
    },
    "printer.uninstalling": {
        "id": "Menguninstall driver printer…",
        "en": "Uninstalling printer driver…",
    },
    "printer.reinstalling": {
        "id": "Mereinstall driver printer…",
        "en": "Reinstalling printer driver…",
    },
    "tool.fixrdp.title": {"id": "RDP", "en": "RDP"},
    "tool.fixrdp.desc": {
        "id": "Cek status RDP Server-App + Fix RDP/cache",
        "en": "Check Server-App RDP status + Fix RDP/cache",
    },
    "rdp.checking": {
        "id": "Memeriksa status RDP (port 3389)…",
        "en": "Checking RDP status (port 3389)…",
    },
    "rdp.fix": {"id": "Fix RDP", "en": "Fix RDP"},
    "rdp.fixing": {
        "id": "Menjalankan Fix RDP + Clear Cache…",
        "en": "Running Fix RDP + Clear Cache…",
    },
    "rdp.summary": {
        "id": "Online: {ok}  ·  Offline: {bad}  ·  Total: {total}",
        "en": "Online: {ok}  ·  Offline: {bad}  ·  Total: {total}",
    },
    "rdp.wait": {"id": "Menunggu…", "en": "Waiting…"},
    "rdp.no_hosts": {
        "id": "Tidak ada Server-App di daftar host.",
        "en": "No Server-App hosts in the list.",
    },
    "tool.scp.title": {"id": "SSH", "en": "SSH"},
    "tool.scp.desc": {
        "id": "SSH: explorer file + terminal (nano/upload/download)",
        "en": "SSH: file explorer + terminal (nano/upload/download)",
    },
    "scp.protocol": {"id": "Protokol", "en": "Protocol"},
    "scp.proto.ssh": {"id": "SSH", "en": "SSH"},
    "scp.proto.scp": {"id": "SCP", "en": "SCP"},
    "scp.proto.sftp": {"id": "SFTP", "en": "SFTP"},
    "scp.save": {"id": "Simpan", "en": "Save"},
    "scp.clear_saved": {"id": "Hapus", "en": "Clear"},
    "scp.saved_ok": {"id": "Parameter koneksi disimpan.", "en": "Connection parameters saved."},
    "scp.cleared_ok": {"id": "Parameter tersimpan dihapus.", "en": "Saved parameters cleared."},
    "scp.drop_hint": {
        "id": "Drop file Windows = upload · seret file remote = download ke Explorer",
        "en": "Drop Windows files to upload · drag remote file to download to Explorer",
    },
    "scp.mode_ssh": {
        "id": "Mode SSH — perintah remote (tetap dual: explorer + terminal).",
        "en": "SSH mode — remote commands (dual: explorer + terminal).",
    },
    "scp.mode_scp": {
        "id": "Mode SCP — preferensi transfer SCP (explorer + SSH tetap aktif).",
        "en": "SCP mode — prefer SCP transfer (explorer + SSH stay active).",
    },
    "scp.mode_sftp": {
        "id": "Mode SFTP — preferensi explorer SFTP (SSH command tetap aktif).",
        "en": "SFTP mode — prefer SFTP explorer (SSH commands stay active).",
    },
    "scp.mode_dual": {
        "id": "Mode dual: explorer file (SFTP/SCP) + perintah SSH aktif bersamaan.",
        "en": "Dual mode: file explorer (SFTP/SCP) + SSH commands together.",
    },
    "scp.host": {"id": "Alamat IP / Host", "en": "IP Address / Host"},
    "scp.port": {"id": "Port", "en": "Port"},
    "scp.user": {"id": "Username", "en": "Username"},
    "scp.pass": {"id": "Password", "en": "Password"},
    "scp.connect": {"id": "Hubungkan", "en": "Connect"},
    "scp.disconnect": {"id": "Putuskan", "en": "Disconnect"},
    "scp.connecting": {"id": "Menghubungkan…", "en": "Connecting…"},
    "scp.connected": {"id": "Terhubung ke {user}@{host}:{port}", "en": "Connected to {user}@{host}:{port}"},
    "scp.disconnected": {"id": "Belum terhubung", "en": "Not connected"},
    "scp.back": {"id": "Kembali", "en": "Back"},
    "scp.up": {"id": "Naik", "en": "Up"},
    "scp.refresh": {"id": "Refresh", "en": "Refresh"},
    "scp.new_folder": {"id": "Folder Baru", "en": "New Folder"},
    "scp.new_file": {"id": "File Baru", "en": "New File"},
    "scp.upload": {"id": "Upload", "en": "Upload"},
    "scp.download": {"id": "Download", "en": "Download"},
    "scp.rename": {"id": "Rename", "en": "Rename"},
    "scp.delete": {"id": "Hapus", "en": "Delete"},
    "scp.copy_path": {"id": "Salin Path", "en": "Copy Path"},
    "scp.copy_name": {"id": "Salin Nama", "en": "Copy Name"},
    "scp.open": {"id": "Buka", "en": "Open"},
    "scp.path": {"id": "Path", "en": "Path"},
    "scp.col.name": {"id": "NAMA", "en": "NAME"},
    "scp.col.size": {"id": "UKURAN", "en": "SIZE"},
    "scp.col.mtime": {"id": "DIUBAH", "en": "MODIFIED"},
    "scp.col.type": {"id": "TIPE", "en": "TYPE"},
    "scp.cmd": {"id": "Perintah SSH", "en": "SSH Command"},
    "scp.run": {"id": "Jalankan", "en": "Run"},
    "scp.prompt_folder": {"id": "Nama folder baru:", "en": "New folder name:"},
    "scp.prompt_file": {"id": "Nama file baru:", "en": "New file name:"},
    "scp.prompt_rename": {"id": "Nama baru:", "en": "New name:"},
    "scp.confirm_delete": {
        "id": "Hapus \"{name}\"? Tindakan ini tidak bisa dibatalkan.",
        "en": "Delete \"{name}\"? This cannot be undone.",
    },
    "scp.empty": {"id": "Folder kosong", "en": "Empty folder"},
    "scp.need_connect": {
        "id": "Hubungkan dulu ke host sebelum memakai explorer.",
        "en": "Connect to a host before using the explorer.",
    },
    "tool.anydesk.title": {"id": "Anydesk", "en": "Anydesk"},
    "tool.anydesk.desc": {
        "id": "Taskkill, jalankan AnyDesk, tampilkan ID (tanpa UAC)",
        "en": "Taskkill, run AnyDesk, show ID (no UAC)",
    },
    # Apps list
    "apps.loading": {"id": "Memuat daftar aplikasi…", "en": "Loading application list…"},
    "apps.fetching": {
        "id": "Mengambil daftar dari Windows…",
        "en": "Reading list from Windows…",
    },
    "apps.count": {"id": "{n} aplikasi terinstall", "en": "{n} applications installed"},
    "apps.empty": {"id": "Tidak ada aplikasi terdeteksi.", "en": "No applications detected."},
    "apps.fail": {"id": "Gagal memuat daftar", "en": "Failed to load list"},
    "apps.col.name": {"id": "NAMA APLIKASI", "en": "APPLICATION"},
    "apps.col.version": {"id": "VERSI", "en": "VERSION"},
    "apps.col.publisher": {"id": "PUBLISHER", "en": "PUBLISHER"},
    "apps.uninstall": {"id": "Uninstall", "en": "Uninstall"},
    "apps.clean_uninstall": {"id": "Uninstall Bersih", "en": "Clean Uninstall"},
    "apps.reinstall": {"id": "Reinstall", "en": "Reinstall"},
    "apps.confirm_uninstall": {
        "id": "Uninstall “{name}”?",
        "en": "Uninstall “{name}”?",
    },
    "apps.confirm_clean": {
        "id": "Uninstall “{name}” secara bersih?\nUninstaller + hapus sisa folder instalasi.",
        "en": "Clean uninstall “{name}”?\nRuns uninstaller and removes leftover install folder.",
    },
    "apps.select": {
        "id": "Pilih aplikasi terlebih dahulu.",
        "en": "Select an application first.",
    },
    "apps.report.title": {
        "id": "=== DAFTAR APLIKASI TERINSTALL ===",
        "en": "=== INSTALLED APPLICATIONS ===",
    },
    "apps.report.pc": {"id": "PC: {host}", "en": "PC: {host}"},
    "apps.report.total": {"id": "Total: {n}", "en": "Total: {n}"},
    "apps.report.version": {"id": "Versi", "en": "Version"},
    "apps.report.publisher": {"id": "Publisher", "en": "Publisher"},
    # Security
    "sec.checking": {
        "id": "Memeriksa status keamanan Windows…",
        "en": "Checking Windows security status…",
    },
    "sec.wait": {"id": "Mohon tunggu…", "en": "Please wait…"},
    "sec.result": {
        "id": "Hasil: {ok}/{total} komponen aman",
        "en": "Result: {ok}/{total} components healthy",
    },
    "sec.none": {"id": "Tidak ada hasil", "en": "No results"},
    "sec.fail": {"id": "Gagal: {msg}", "en": "Failed: {msg}"},
    "sec.report.title": {
        "id": "=== CEK KEAMANAN WINDOWS ===",
        "en": "=== WINDOWS SECURITY CHECK ===",
    },
    "sec.ok": {"id": "OK", "en": "OK"},
    "sec.warn": {"id": "PERHATIAN", "en": "ATTENTION"},
    "sec.firewall": {"id": "Windows Firewall", "en": "Windows Firewall"},
    "sec.defender": {"id": "Windows Defender", "en": "Windows Defender"},
    "sec.wu": {"id": "Windows Update", "en": "Windows Update"},
    "sec.netprofile": {"id": "Profil Jaringan", "en": "Network Profile"},
    # IP Scanner
    "ipscan.local_ip": {"id": "IP LOKAL", "en": "LOCAL IP"},
    "ipscan.subnet": {"id": "SUBNET", "en": "SUBNET"},
    "ipscan.progress": {"id": "PROGRESS", "en": "PROGRESS"},
    "ipscan.alive": {"id": "HOST HIDUP", "en": "LIVE HOSTS"},
    "ipscan.ready": {
        "id": "Siap memindai subnet PC ini.",
        "en": "Ready to scan this PC’s subnet.",
    },
    "ipscan.col.ip": {"id": "ALAMAT IP", "en": "IP ADDRESS"},
    "ipscan.col.host": {"id": "HOSTNAME", "en": "HOSTNAME"},
    "ipscan.col.status": {"id": "STATUS", "en": "STATUS"},
    "ipscan.online": {"id": "Online", "en": "Online"},
    "ipscan.this_pc": {"id": "PC ini", "en": "This PC"},
    "ipscan.empty": {
        "id": "Belum ada hasil. Klik Mulai Scan.",
        "en": "No results yet. Click Start Scan.",
    },
    "ipscan.scanning": {"id": "Sedang memindai…", "en": "Scanning…"},
    "ipscan.no_hosts": {
        "id": "Tidak ada host yang merespons ping.",
        "en": "No hosts responded to ping.",
    },
    # Update
    "update.title": {
        "id": "Update Wajib — Network Tools",
        "en": "Mandatory Update — Network Tools",
    },
    "update.badge": {"id": "UPDATE WAJIB", "en": "MANDATORY UPDATE"},
    "update.heading": {"id": "Versi baru tersedia", "en": "A new version is available"},
    "update.sub": {
        "id": "Pasang pembaruan untuk melanjutkan.",
        "en": "Install the update to continue.",
    },
    "update.now": {"id": "Update Sekarang", "en": "Update Now"},
    "update.footer": {
        "id": "Tanpa update, aplikasi tidak dapat digunakan.",
        "en": "The app cannot be used without updating.",
    },
    "update.current": {"id": "SAAT INI", "en": "CURRENT"},
    "update.latest": {"id": "TERBARU", "en": "LATEST"},
    "update.notes": {"id": "Catatan rilis", "en": "Release notes"},
    "update.notes_fallback": {
        "id": "Pembaruan keamanan & perbaikan stabilitas.",
        "en": "Security updates and stability fixes.",
    },
    "update.installing": {"id": "Memasang v{ver}", "en": "Installing v{ver}"},
    "update.dev": {
        "id": "Mode development: unduh EXE dari GitHub, lalu ganti manual.",
        "en": "Development mode: download the EXE from GitHub and replace it manually.",
    },
    # Kirim
    "send.dialog_title": {"id": "Network Tools — Kirim", "en": "Network Tools — Send"},
    "send.shot_ready": {"id": "Screenshot siap", "en": "Screenshot ready"},
    "send.shot_sub": {
        "id": "Buka chat Telegram, lalu tempel gambar:",
        "en": "Open a Telegram chat, then paste the image:",
    },
    "send.text_ready": {"id": "Teks siap dikirim", "en": "Text ready to send"},
    "send.text_sub": {
        "id": "Buka chat Telegram, lalu tempel teks:",
        "en": "Open a Telegram chat, then paste the text:",
    },
    "send.not_ready": {"id": "Belum siap", "en": "Not ready"},
    "send.not_ready_sub": {
        "id": "Muat data dulu, lalu klik Kirim.",
        "en": "Load the data first, then click Send.",
    },
    "send.no_data": {
        "id": "Belum ada data untuk dikirim. Tunggu hingga daftar/hasil selesai dimuat.",
        "en": "No data to send yet. Wait until the list/results finish loading.",
    },
    "send.ok": {"id": "Mengerti", "en": "Got it"},
    # Anydesk dialog
    "anydesk.dialog_title": {"id": "AnyDesk ID siap", "en": "AnyDesk ID ready"},
    "anydesk.dialog_sub": {
        "id": "ID sudah disalin. Tekan Kirim untuk membuka Telegram.",
        "en": "ID copied. Press Send to open Telegram.",
    },
    "anydesk.id_label": {"id": "ID Anydesk", "en": "AnyDesk ID"},
    "anydesk.local_id_label": {"id": "ID Lokal", "en": "Local ID"},
    "anydesk.local_ip_label": {"id": "Alamat IP Lokal", "en": "Local IP Address"},
    "anydesk.copy_all": {"id": "Salin semua", "en": "Copy all"},
    "anydesk.copy_one": {"id": "Salin", "en": "Copy"},
    "anydesk.copied": {"id": "Tersalin ke clipboard", "en": "Copied to clipboard"},
    "anydesk.copied_one": {
        "id": "{label} tersalin",
        "en": "{label} copied",
    },
    "anydesk.telegram_opened": {
        "id": "Telegram dibuka — tempel dengan Ctrl+V",
        "en": "Telegram opened — paste with Ctrl+V",
    },
    "anydesk.telegram_missing": {
        "id": "Telegram tidak ditemukan. ID sudah di clipboard.",
        "en": "Telegram not found. ID is on the clipboard.",
    },
    # Done notifications
    "done.title": {"id": "Proses selesai", "en": "Process complete"},
    "done.refresh": {
        "id": "Fix Network sudah selesai.",
        "en": "Fix Network has finished.",
    },
    "done.printer": {
        "id": "Clear spooler printer sudah selesai.",
        "en": "Printer spooler clear has finished.",
    },
    "done.fixrdp": {
        "id": "Fix RDP + Clear Cache sudah selesai.",
        "en": "Fix RDP + Clear Cache has finished.",
    },
}


def get_lang() -> str:
    return _LANG


def set_lang(lang: str) -> None:
    global _LANG
    lang = (lang or DEFAULT_LANG).lower()
    _LANG = lang if lang in LANGS else DEFAULT_LANG


def t(key: str, **kwargs: Any) -> str:
    entry = _STRINGS.get(key) or {}
    text = entry.get(_LANG) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def lang_dropdown_values() -> list[str]:
    return [t("lang.id"), t("lang.en")]


def lang_from_label(label: str) -> str:
    en_labels = {
        _STRINGS["lang.en"]["id"],
        _STRINGS["lang.en"]["en"],
        "Language: English",
        "Bahasa: English",
    }
    if (label or "").strip() in en_labels:
        return "en"
    return "id"


def theme_label(mode: str) -> str:
    key = f"theme.{mode}"
    if key in _STRINGS:
        return t(key)
    return mode


def theme_dropdown_values() -> list[str]:
    from modules.theme import THEME_MODES

    return [theme_label(m) for m in THEME_MODES]


def mode_from_theme_label(label: str) -> str:
    from modules.theme import THEME_MODES

    for mode in THEME_MODES:
        for lang in LANGS:
            if _STRINGS.get(f"theme.{mode}", {}).get(lang) == label:
                return mode
    return "system"
