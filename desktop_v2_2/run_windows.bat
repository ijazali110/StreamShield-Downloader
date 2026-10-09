@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Shield Stream - Setup and Run

set "PYEXE="

rem Reuse a healthy virtual environment if it already exists.
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; print(sys.version)" >nul 2>nul
    if not errorlevel 1 goto :venv_ready
    echo Existing virtual environment is broken. Recreating it...
    rmdir /s /q ".venv" >nul 2>nul
)

call :find_python
if defined PYEXE goto :create_venv

echo.
echo No working Python 3.11+ installation was found.
echo The Windows Python launcher may be pointing to an old or removed Python install.
echo.
where winget >nul 2>nul
if errorlevel 1 goto :manual_python

choice /C YN /N /M "Install Python 3.12 automatically with Windows Package Manager? [Y/N]: "
if errorlevel 2 goto :manual_python

echo.
echo Installing Python 3.12...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :manual_python

call :find_python
if not defined PYEXE (
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE goto :manual_python

:create_venv
echo.
echo Using Python: %PYEXE%
echo Creating Python virtual environment...
"%PYEXE%" -m venv ".venv"
if errorlevel 1 goto :venv_error

:venv_ready
echo.
echo Installing/updating downloader engine...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :pip_error
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :pip_error

call :ensure_js_runtime

echo.
echo Checking engine...
".venv\Scripts\python.exe" -c "from downloader_app.runtime import engine_summary; print(engine_summary())"

echo.
echo Starting Shield Stream V2.2 On-Video Download Menu...
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto :app_error
goto :eof

:ensure_js_runtime
where deno >nul 2>nul
if not errorlevel 1 exit /b 0
where node >nul 2>nul
if not errorlevel 1 exit /b 0
if exist "%USERPROFILE%\.deno\bin\deno.exe" exit /b 0
if exist "%ProgramFiles%\nodejs\node.exe" exit /b 0

echo.
echo IMPORTANT: Some sites, including YouTube, need a JavaScript runtime.
echo Deno is the runtime recommended by yt-dlp.
where winget >nul 2>nul
if errorlevel 1 (
    echo Deno is not installed. You can install it later with install_deno_windows.bat.
    exit /b 0
)
choice /C YN /N /M "Install Deno now for reliable site compatibility? [Y/N]: "
if errorlevel 2 exit /b 0
winget install -e --id DenoLand.Deno --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo Deno installation did not complete. The app will still open. Run install_deno_windows.bat later if YouTube reports a JavaScript runtime error.
)
exit /b 0

:find_python
rem Prefer direct installations first so a stale py.exe launcher cannot block startup.
for %%P in (314 313 312 311) do (
    if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python%%P\python.exe" (
        "%LocalAppData%\Programs\Python\Python%%P\python.exe" -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
        if not errorlevel 1 set "PYEXE=%LocalAppData%\Programs\Python\Python%%P\python.exe"
    )
    if not defined PYEXE if exist "%ProgramFiles%\Python%%P\python.exe" (
        "%ProgramFiles%\Python%%P\python.exe" -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
        if not errorlevel 1 set "PYEXE=%ProgramFiles%\Python%%P\python.exe"
    )
)
if defined PYEXE goto :eof

python -c "import sys; assert sys.version_info >= (3,11); print(sys.executable)" >nul 2>nul
if not errorlevel 1 (
    for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%I"
)
if defined PYEXE goto :eof

for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PYEXE (
        py -%%V -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
        if not errorlevel 1 for /f "usebackq delims=" %%I in (`py -%%V -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%I"
    )
)
goto :eof

:manual_python
echo.
echo Python is required for this source-code build.
echo Install Python 3.12 from python.org and make sure "Add python.exe to PATH" is enabled.
echo Then double-click run_windows.bat again.
echo.
pause
goto :eof

:venv_error
echo.
echo Could not create the virtual environment.
echo If you previously removed Python, delete the .venv folder and run this launcher again.
echo.
pause
goto :eof

:pip_error
echo.
echo Package installation failed. Check your internet connection and run this launcher again.
echo.
pause
goto :eof

:app_error
echo.
echo The application closed with an error. Copy the error shown above and send it to me.
echo.
pause
goto :eof
