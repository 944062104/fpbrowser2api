@echo off
setlocal
chcp 65001 >nul
title AI号池全套服务停止器

cd /d "%~dp0"

set "PY_EXE=python"
if exist "D:\Program Files\anaconda3\python.exe" (
    set "PY_EXE=D:\Program Files\anaconda3\python.exe"
) else if exist "D:\Python313\python.exe" (
    set "PY_EXE=D:\Python313\python.exe"
)

echo ========================================================
echo   正在停止全套 AI 号池服务 (WARP代理 + VB + 网关)...
echo ========================================================
echo.

if exist "%~dp0stop_services.py" (
    "%PY_EXE%" "%~dp0stop_services.py"
) else (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":9000 .*LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
    )
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
    )
    for %%p in (40001 40002 40003 40004 40005) do (
        for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":%%p .*LISTENING"') do (
            taskkill /F /PID %%a >nul 2>&1
        )
    )
)

echo.
echo ========================================================
echo   服务已全部安全停止。
echo ========================================================
ping 127.0.0.1 -n 3 >nul
