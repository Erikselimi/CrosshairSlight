@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 crosshair_studio.py
) else (
    python crosshair_studio.py
)

if errorlevel 1 (
    echo.
    echo Sightline could not start. Review the error above.
    pause
)
