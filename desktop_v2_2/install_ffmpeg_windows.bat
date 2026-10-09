@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Shield Stream - Install Full FFmpeg

echo Installing the full FFmpeg package with Windows Package Manager...
where winget >nul 2>nul
if errorlevel 1 (
    echo.
    echo Windows Package Manager ^(winget^) is not available on this PC.
    echo Shield Stream V2.1 can still create compatibility previews using its bundled FFmpeg fallback.
    echo For full ffplay support, install a standard FFmpeg full build and make sure ffplay.exe is available.
    pause
    exit /b 1
)

winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo FFmpeg install did not complete. Shield Stream can still try its bundled compatibility-preview fallback.
    pause
    exit /b 1
)

echo.
echo Installation completed.
where ffmpeg 2>nul
where ffplay 2>nul

echo.
echo If ffplay is not printed above, close Shield Stream and start it again so Windows can refresh package paths.
echo Even without ffplay, V2.0.1 can prepare a 30-second in-app compatibility preview with FFmpeg.
pause
