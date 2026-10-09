@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Fast Video Downloader - Install Deno

echo YouTube now requires a JavaScript runtime for reliable yt-dlp downloads.
echo Installing Deno (recommended by yt-dlp)...
echo.

where winget >nul 2>nul
if errorlevel 1 (
    echo Windows Package Manager ^(winget^) was not found.
    echo Install Deno manually from https://deno.com/ and run this app again.
    echo.
    pause
    goto :eof
)

winget install -e --id DenoLand.Deno --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo.
    echo Deno installation failed. You can install Deno manually and then restart the app.
    pause
    goto :eof
)

echo.
echo Deno installed. Close and reopen Fast Video Downloader.
pause
