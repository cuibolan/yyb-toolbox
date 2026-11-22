@echo off
chcp 65001 >nul
cd /d "%~dp0"
for %%f in ("%~dp0*.exe") do (
    start "" "%%~f"
    exit /b
)
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe "yyb_toolbox.py"
    exit /b
)
start "" py "yyb_toolbox.py"
