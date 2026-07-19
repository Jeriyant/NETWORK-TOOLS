@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt
echo.
echo Building NetworkTools.exe (single file)...
python -m PyInstaller --noconfirm --clean NetworkTools.spec

echo.
echo Selesai. Jalankan: dist\NetworkTools.exe
pause
