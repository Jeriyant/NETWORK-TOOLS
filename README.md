# Network Tools

Aplikasi desktop Windows untuk IT Networking.

## Build

```bat
build.bat
```

Hasil:
- Folder: `dist\NetworkTools\` (`NetworkTools.exe` + `_internal`)
- Paket rilis: `dist\NetworkTools.zip`

> Mulai v1.12 memakai **onedir** (bukan single-file), agar tidak extract runtime ke `Temp\_MEI` (penyebab error `python312.dll`).

## Fitur

| Tool | Perilaku |
|------|----------|
| **Ping / Traceroute** | Host tetap: Internet, Gateway (otomatis), Server-VPN/DB/App1–8 |
| **DNS Test** | Uji resolusi DNS |
| **Speedtest** | `https://jeriyant.speedtestcustom.com` (WebView2) |
| **Refresh Network** | Disable/enable NIC + renew DHCP (minta Administrator) |
| **Fix Printer** | Clear spooler: stop → hapus antrian → start (minta Administrator) |
| **Clear Cache** | Hapus TEMP & `RDP6` (minta Administrator) |
| **Anydesk** | Tutup AnyDesk lama, buka baru, salin ID, buka Telegram |

Footer: `Copyright © {tahun} JERIYANT - BARAMCITY`

## Update otomatis

Saat dijalankan, app mengecek **GitHub Releases** di `Jeriyant/NETWORK-TOOLS`.
Update dipasang ke `%LOCALAPPDATA%\NetworkTools`.

Lihat `UPDATE.md` untuk cara publish rilis baru.
