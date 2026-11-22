@echo off
chcp 65001 >nul
cd /d "%~dp0"

py -m pip install --disable-pip-version-check pyinstaller
if errorlevel 1 (
    echo Failed to install pyinstaller
    pause
    exit /b 1
)

py -m PyInstaller --noconfirm --clean --onefile --noconsole ^
  --name YYBToolbox --icon app.ico --add-data "app.ico;." ^
  --version-file version_info.txt yyb_toolbox.py
if errorlevel 1 (
    echo Build failed
    pause
    exit /b 1
)

echo.
echo Build complete: dist\YYBToolbox.exe
echo Rename it to the name you want to ship.
pause
