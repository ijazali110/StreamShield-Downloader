@echo off
setlocal
where aria2c >nul 2>&1
if %errorlevel%==0 (
  echo aria2c is already installed.
  aria2c --version | findstr /i "aria2 version"
  pause
  exit /b 0
)
where winget >nul 2>&1
if not %errorlevel%==0 (
  echo Windows Package Manager ^(winget^) was not found.
  echo Shield Stream will continue to use its built-in Fast mode without aria2.
  pause
  exit /b 1
)
echo Installing aria2 for optional Maximum speed mode...
winget install --id aria2.aria2 -e --accept-package-agreements --accept-source-agreements
if not %errorlevel%==0 (
  echo aria2 installation failed. Shield Stream Fast mode will still work.
  pause
  exit /b 1
)
echo Done. Restart Shield Stream before using Maximum speed mode.
pause
