# Cara publish update (GitHub)

App mengecek update setiap kali dijalankan ke:
https://github.com/Jeriyant/NETWORK-TOOLS

Urutan cek:
1. **GitHub Releases** (`/releases/latest`) — asset `.exe`
2. Fallback **`update.json`** di branch `main`

## Opsi A — GitHub Releases (disarankan)

1. Naikkan `APP_VERSION` di `modules/settings.py` (contoh: `1.0.1`)
2. Build: `build.bat` → `dist\NetworkTools.exe`
3. Buat Release di GitHub:
   - Tag: `v1.0.1`
   - Upload asset: `NetworkTools.exe`
4. User yang punya versi lama akan ditawari update saat buka app

## Opsi B — update.json

1. Edit `update.json`:

```json
{
  "version": "1.0.1",
  "url": "https://github.com/Jeriyant/NETWORK-TOOLS/releases/download/v1.0.1/NetworkTools.exe",
  "changelog": "Perbaikan ...",
  "mandatory": false
}
```

2. Commit & push ke `main`
3. Pastikan `url` adalah unduhan langsung ke file `.exe`
