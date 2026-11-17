@echo off
REM Windows: double-click. Requires WSL (wsl --install) - runs start.sh inside it.
cd /d "%~dp0"
wsl bash -lc "./start.sh"
pause
