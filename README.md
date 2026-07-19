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
| **DNS Test** | Uji resolusi DNS |
| **RDP Test** | Cek service RDP (TCP 3389) pada host menu Ping |
| **Speedtest** | `https://jeriyant.speedtestcustom.com` (WebView2) |
| **Refresh Network** | Disable/enable NIC + renew DHCP (minta Administrator) |
| **Fix Printer** | Clear spooler: stop → hapus antrian → start (minta Administrator) |
| **Clear Cache** | Hapus TEMP & `RDP6` (minta Administrator) |
| **Anydesk** | Tutup AnyDesk lama, buka baru, salin ID, buka Telegram |

Footer: `Copyright © {tahun} JERIYANT - BARAMCITY`

## Update otomatis

Saat dijalankan, app mengecek **GitHub Releases** di `Jeriyant/NETWORK-TOOLS`.

Lihat `UPDATE.md` untuk cara publish rilis baru.
