@echo off
cd /d "%~dp0"
echo Installing dependencies...
python -m pip install -r requirements.txt
echo.
echo Building NetworkTools (onedir)...
python -m PyInstaller --noconfirm --clean NetworkTools.spec
if errorlevel 1 exit /b 1

echo.
echo Membuat NetworkTools.zip...
if exist dist\NetworkTools.zip del /f /q dist\NetworkTools.zip
powershell -NoProfile -Command "Compress-Archive -Path 'dist\NetworkTools\*' -DestinationPath 'dist\NetworkTools.zip' -Force"

echo.
echo Selesai.
echo   Folder: dist\NetworkTools\NetworkTools.exe
echo   ZIP:    dist\NetworkTools.zip
pause
