@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title "FPBrowser2API Service"

set "PY_EXE=python"
if exist "D:\Python313\python.exe" (
    set "PY_EXE=D:\Python313\python.exe"
)

echo Starting FPBrowser2API Service...
echo Using Python: %PY_EXE%
echo.

"%PY_EXE%" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] FPBrowser2API exited with an error.
)
pause
