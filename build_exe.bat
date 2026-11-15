@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON=py -3"
) else (
    set "PYTHON=python"
)

for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"`) do set "DESKTOP=%%D"
if not defined DESKTOP (
    echo Could not find the Windows Desktop folder.
    exit /b 1
)

%PYTHON% -m PyInstaller --noconfirm --clean --onefile --windowed --name Sightline --icon "%~dp0Neon Crosshair Customizer Icon.ico" --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageTk --specpath build --distpath "%DESKTOP%" crosshair_studio.py
if errorlevel 1 (
    echo.
    echo Build failed. Review the error above.
    exit /b 1
)

echo.
echo Sightline.exe is ready on your Desktop.
