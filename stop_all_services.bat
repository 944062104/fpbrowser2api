@echo off
setlocal
chcp 65001 >nul
title AI号池双服务停止器

echo ========================================================
echo   正在停止 VirtualBrowser ^& FPBrowser2API 服务...
echo ========================================================
echo.

for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":9000 .*LISTENING"') do (
    echo 正在关闭 VirtualBrowser API [PID: %%a]...
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do (
    echo 正在关闭 FPBrowser2API 网关 [PID: %%a]...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo ========================================================
echo   服务已全部停止。
echo ========================================================
ping 127.0.0.1 -n 3 >nul
