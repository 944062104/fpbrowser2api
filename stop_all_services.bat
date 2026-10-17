@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY_EXE=python"
if exist "D:\Program Files\anaconda3\python.exe" (
    set "PY_EXE=D:\Program Files\anaconda3\python.exe"
) else if exist "D:\Python313\python.exe" (
    set "PY_EXE=D:\Python313\python.exe"
)

"%PY_EXE%" stop_services.py
ping 127.0.0.1 -n 3 >nul