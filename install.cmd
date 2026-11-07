@echo off
setlocal
echo ============================================================
echo   Installing AI System Terminal for ZETHUB on Windows...
echo ============================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
endlocal

