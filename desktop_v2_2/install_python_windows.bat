@echo off
setlocal
cd /d "%~dp0"
title Install Python 3.12

where winget >nul 2>nul
if errorlevel 1 (
    echo Windows Package Manager ^(winget^) was not found.
    echo Please install Python 3.12 manually from python.org.
    pause
    exit /b 1
)

echo This will install Python 3.12 for the current Windows user.
choice /C YN /N /M "Continue? [Y/N]: "
if errorlevel 2 exit /b 0

winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo Python installation failed.
    pause
    exit /b 1
)

echo.
echo Python installation completed.
echo Now run run_windows.bat.
pause
