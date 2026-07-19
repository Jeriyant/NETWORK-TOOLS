# Cara publish update (GitHub Releases)

App mengecek update setiap kali dijalankan **hanya** ke GitHub Releases:
https://github.com/Jeriyant/NETWORK-TOOLS/releases

## Langkah rilis

1. Naikkan `APP_VERSION` di `modules/settings.py` (contoh: `1.12`)
2. Build: `build.bat` → folder `dist\NetworkTools\` + `dist\NetworkTools.zip`
3. Buat Release di GitHub:
   - Tag: `v1.12`
   - Title: `Network Tools 1.12`
   - Upload asset: **`NetworkTools.zip`** (isi: `NetworkTools.exe` + folder `_internal`)
4. Publish release (centang *latest*)

## Instalasi manual

1. Unduh `NetworkTools.zip`
2. Extract ke folder (mis. Desktop\NetworkTools)
3. Jalankan `NetworkTools.exe` di dalam folder itu

## Alur auto-update

1. App ditutup
2. File lama di lokasi program dihapus
3. Paket baru diextract/diganti
4. App dibuka lagi otomatis

> Catatan: mulai v1.12 build memakai **onedir** (bukan single-file) agar tidak crash `_MEI/python312.dll` saat update.
