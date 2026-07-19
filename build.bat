@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt
echo.
echo Building NetworkTools (folder onedir)...
python -m PyInstaller --noconfirm --clean NetworkTools.spec
if errorlevel 1 exit /b 1

echo.
echo Membuat NetworkTools.zip untuk GitHub Release...
if exist "dist\NetworkTools.zip" del /F /Q "dist\NetworkTools.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\NetworkTools\*' -DestinationPath 'dist\NetworkTools.zip' -Force"

echo.
echo Selesai.
echo   Jalankan: dist\NetworkTools\NetworkTools.exe
echo   Release:  dist\NetworkTools.zip
pause
