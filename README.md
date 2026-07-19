# Network Tools

Aplikasi desktop Windows (single-file `.exe`) untuk IT Networking.

## Build

```bat
build.bat
```

Hasil: `dist\NetworkTools.exe` (satu file, tanpa `config.json`).

## Fitur

| Tool | Perilaku |
|------|----------|
| **Ping / Traceroute** | Host tetap: Internet, Gateway (otomatis), Server-VPN/DB/App1–8 |
| **Speedtest** | `https://jeriyant.speedtestcustom.com` (WebView2) |
| **DNS Test** | `https://browserleaks.com/dns` (WebView2, seperti Speedtest) |
| **IP Scanner** | UI daftar host: scan subnet PC (ICMP), progress bar, status Online |
| **Refresh Network** | Disable/enable NIC + renew DHCP (minta Administrator) |
| **Fix Printer** | Clear spooler: stop → hapus antrian → start (minta Administrator) |
| **Fix RDP** | Reset RDP client: kill ConnectionClient, hapus RDP6/cache, bersihkan registry & kredensial TERMSRV |
| **Clear Cache** | Hapus TEMP & `RDP6` (minta Administrator) |
| **Anydesk** | Tutup AnyDesk lama, buka baru, salin ID, buka Telegram |

Footer: `Copyright © {tahun} JERIYANT - BARAMCITY`

## Update otomatis

Saat dijalankan, app mengecek **GitHub Releases** di `Jeriyant/NETWORK-TOOLS`.

Lihat `UPDATE.md` untuk cara publish rilis baru.
