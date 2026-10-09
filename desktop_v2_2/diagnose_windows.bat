@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Shield Stream V2.1 - Diagnostics

echo === Shield Stream V2.1 diagnostics ===
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment is missing. Run run_windows.bat first.
    pause
    goto :eof
)

".venv\Scripts\python.exe" -c "import sys; print('Python:', sys.version); import yt_dlp; print('yt-dlp:', yt_dlp.version.__version__); from downloader_app.runtime import find_aria2c, find_ffmpeg, find_ffplay, find_js_runtime; print('FFmpeg:', find_ffmpeg() or 'MISSING'); print('ffplay:', find_ffplay() or 'optional / not found'); print('aria2c:', find_aria2c() or 'optional / not found'); print('JS runtime:', find_js_runtime())"

echo.
echo Browser Companion bridge:
powershell -NoProfile -Command "try { $r=Invoke-RestMethod -Uri 'http://127.0.0.1:8765/health' -TimeoutSec 2; if($r.ok){Write-Host 'CONNECTED - Shield Stream desktop app is accepting Chrome media.' -ForegroundColor Green}else{Write-Host 'NOT READY'}} catch { Write-Host 'NOT CONNECTED - start Shield Stream first.' -ForegroundColor Yellow }"

echo.
echo JavaScript runtimes on PATH:
where deno 2>nul
where node 2>nul

echo.
echo If browser media is not detected, start playback and run Power scan 30s in the extension.
pause
