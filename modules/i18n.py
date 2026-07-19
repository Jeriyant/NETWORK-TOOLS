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
        "id": "Utilitas IT Networking — ping, DNS, speedtest & perbaikan cepat",
        "en": "IT Networking utilities — ping, DNS, speedtest & quick fixes",
    },
    "app.open": {"id": "Buka", "en": "Open"},
    "app.back": {"id": "Kembali", "en": "Back"},
    "app.send": {"id": "Kirim", "en": "Send"},
    "app.refresh": {"id": "Refresh", "en": "Refresh"},
    "app.recheck": {"id": "Cek Ulang", "en": "Recheck"},
    "app.reload": {"id": "Muat Ulang", "en": "Reload"},
    "app.page_loading": {"id": "Memuat halaman…", "en": "Loading page…"},
    "app.start_scan": {"id": "Mulai Scan", "en": "Start Scan"},
    "app.stop": {"id": "Stop", "en": "Stop"},
    "app.run": {"id": "Jalankan", "en": "Run"},
    "app.select_host": {"id": "Pilih host:", "en": "Select host:"},
    "app.start_ping": {"id": "Mulai Ping", "en": "Start Ping"},
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
        "id": "Ping terus ke host dari daftar",
        "en": "Continuous ping to hosts from the list",
    },
    "tool.traceroute.title": {"id": "Traceroute", "en": "Traceroute"},
    "tool.traceroute.desc": {
        "id": "tracert -d ke alamat IP/host",
        "en": "tracert -d to an IP/host",
    },
    "tool.speedtest.title": {"id": "Speedtest", "en": "Speedtest"},
    "tool.speedtest.desc": {
        "id": "Speedtest di browser bawaan aplikasi",
        "en": "Speedtest in the built-in browser",
    },
    "tool.dns.title": {"id": "DNS Test", "en": "DNS Test"},
    "tool.dns.desc": {
        "id": "DNS leak test di browser bawaan",
        "en": "DNS leak test in the built-in browser",
    },
    "tool.ipscan.title": {"id": "IP Scanner", "en": "IP Scanner"},
    "tool.ipscan.desc": {
        "id": "Scan host hidup di subnet PC ini",
        "en": "Scan live hosts on this PC’s subnet",
    },
    "tool.apps.title": {"id": "Daftar Aplikasi", "en": "Installed Apps"},
    "tool.apps.desc": {
        "id": "Tampilkan aplikasi terinstall di Windows",
        "en": "Show applications installed on Windows",
    },
    "tool.security.title": {"id": "Cek Keamanan", "en": "Security Check"},
    "tool.security.desc": {
        "id": "Firewall, Defender & Windows Update",
        "en": "Firewall, Defender & Windows Update",
    },
    "tool.refresh.title": {"id": "Refresh Network", "en": "Refresh Network"},
    "tool.refresh.desc": {
        "id": "Otomatis renew DHCP (Admin)",
        "en": "Auto renew DHCP (Admin)",
    },
    "tool.printer.title": {"id": "Fix Printer", "en": "Fix Printer"},
    "tool.printer.desc": {
        "id": "Otomatis clear spooler (Admin)",
        "en": "Auto clear print spooler (Admin)",
    },
    "tool.fixrdp.title": {"id": "Fix RDP", "en": "Fix RDP"},
    "tool.fixrdp.desc": {
        "id": "Reset RDP client agar fresh (Admin)",
        "en": "Reset RDP client for a fresh start (Admin)",
    },
    "tool.cache.title": {"id": "Clear Cache", "en": "Clear Cache"},
    "tool.cache.desc": {
        "id": "Otomatis hapus TEMP & RDP6 (Admin)",
        "en": "Auto clear TEMP & RDP6 (Admin)",
    },
    "tool.anydesk.title": {"id": "Anydesk", "en": "Anydesk"},
    "tool.anydesk.desc": {
        "id": "Otomatis tutup/buka AnyDesk + salin ID ke Telegram",
        "en": "Auto restart AnyDesk and copy ID to Telegram",
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
