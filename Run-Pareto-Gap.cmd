@echo off
setlocal
title Pareto Gap
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    py -3 run.py %*
    goto finished
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if not errorlevel 1 (
    python run.py %*
    goto finished
)
echo.
echo Python 3.11 or newer is needed.
echo Install Python from https://www.python.org/downloads/
echo On Windows, select "Add Python to PATH" during setup.
echo Then double-click this file again.
:finished
echo.
pause
endlocal
