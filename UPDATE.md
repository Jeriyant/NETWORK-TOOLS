# Cara publish update (GitHub Releases)

App mengecek update setiap kali dijalankan **hanya** ke GitHub Releases:
https://github.com/Jeriyant/NETWORK-TOOLS/releases

## Langkah rilis

1. Naikkan `APP_VERSION` di `modules/settings.py` (contoh: `1.12`)
2. Build: `build.bat` → `dist\NetworkTools\` + `dist\NetworkTools.zip`
3. Buat Release di GitHub:
   - Tag: `v1.12`
   - Title: `Network Tools 1.12`
   - Upload asset: **`NetworkTools.zip`** (wajib — paket onedir)
4. Publish release (centang *latest*)

## Instalasi manual

1. Unduh `NetworkTools.zip`
2. Ekstrak ke folder mana saja (disarankan: `%LOCALAPPDATA%\NetworkTools`)
3. Jalankan `NetworkTools.exe` di dalam folder hasil ekstrak (bersama folder `_internal`)

> Catatan: mulai v1.12 app memakai **onedir** (bukan one-file), sehingga tidak lagi
> mengekstrak runtime ke `Temp\_MEI...` (penyebab error `python312.dll` saat update).

User dengan versi lama akan ditawari update saat membuka app (atau diarahkan ke halaman Release).
