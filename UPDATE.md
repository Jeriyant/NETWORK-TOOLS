# Cara publish update (GitHub Releases)

App mengecek update setiap kali dijalankan **hanya** ke GitHub Releases:
https://github.com/Jeriyant/NETWORK-TOOLS/releases

## Langkah rilis

1. Naikkan `APP_VERSION` di `modules/settings.py` (contoh: `1.0.3`)
2. Build: `build.bat` → `dist\NetworkTools.exe`
3. Buat Release di GitHub:
   - Tag: `v1.0.3`
   - Title: `Network Tools 1.0.3`
   - Upload asset: **`NetworkTools.exe`**
4. Publish release (centang *latest*)

User dengan versi lama akan ditawari update saat membuka app.
