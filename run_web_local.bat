@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe python -m venv .venv
.venv\Scripts\python.exe -m pip install -r server\requirements.txt
if "%STREAMFORGE_PASSWORD%"=="" set /p STREAMFORGE_PASSWORD=Enter a private password (16 or more characters): 
set STREAMFORGE_SECURE_COOKIE=0
set STREAMFORGE_DATA=%CD%\web_data
.venv\Scripts\python.exe -m server.app
pause
