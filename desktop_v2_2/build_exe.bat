@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Shield Stream - Build EXE

set "PYEXE="

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys; print(sys.version)" >nul 2>nul
    if not errorlevel 1 goto :venv_ready
    echo Existing virtual environment is broken. Recreating it...
    rmdir /s /q ".venv" >nul 2>nul
)

call :find_python
if not defined PYEXE goto :no_python

echo Using Python: %PYEXE%
"%PYEXE%" -m venv ".venv"
if errorlevel 1 goto :error

:venv_ready
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
if errorlevel 1 goto :error

rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

echo.
echo Building Windows application...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed --name ShieldStream --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all imageio_ffmpeg --collect-all curl_cffi app.py
if errorlevel 1 goto :error

echo.
xcopy /E /I /Y "chrome_extension" "dist\ShieldStream\chrome_extension" >nul
copy /Y "open_chrome_extension_setup.bat" "dist\ShieldStream\open_chrome_extension_setup.bat" >nul

echo Build complete.
copy /Y "install_ffmpeg_windows.bat" "dist\ShieldStream\install_ffmpeg_windows.bat" >nul
copy /Y "install_aria2_windows.bat" "dist\ShieldStream\install_aria2_windows.bat" >nul
echo Open: dist\ShieldStream\ShieldStream.exe
echo Chrome Companion: dist\ShieldStream\chrome_extension
pause
goto :eof

:find_python
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
python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if not errorlevel 1 for /f "usebackq delims=" %%I in (`python -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%I"
if defined PYEXE goto :eof
for %%V in (3.14 3.13 3.12 3.11) do (
    if not defined PYEXE (
        py -%%V -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
        if not errorlevel 1 for /f "usebackq delims=" %%I in (`py -%%V -c "import sys; print(sys.executable)" 2^>nul`) do set "PYEXE=%%I"
    )
)
goto :eof

:no_python
echo.
echo No working Python 3.11+ installation was found.
echo Run run_windows.bat first; it can offer to install Python 3.12 automatically.
echo.
pause
goto :eof

:error
echo.
echo Build failed. Copy the error shown above and send it to me.
echo.
pause
