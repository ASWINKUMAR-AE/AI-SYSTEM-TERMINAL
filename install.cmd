@echo off
setlocal
echo ============================================================
echo   Installing ZetHub AI System Terminal globally on Windows...
echo ============================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
endlocal

