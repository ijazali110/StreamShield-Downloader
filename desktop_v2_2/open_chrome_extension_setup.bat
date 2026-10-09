@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "CHROME="

if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

echo.
echo Shield Stream Chrome Companion setup
echo ----------------------------------
echo 1. Chrome Extensions will open.
echo 2. Turn on Developer mode (top-right).
echo 3. Click Load unpacked.
echo 4. Select this folder:
echo    %CD%\chrome_extension
echo.
start "" explorer.exe "%CD%\chrome_extension"
if defined CHROME (
    start "" "%CHROME%" "chrome://extensions/"
) else (
    start "" "chrome://extensions/"
    echo If Chrome did not open, manually open: chrome://extensions/
)
pause
