@echo off
setlocal
chcp 65001 >nul
title AI号池全套服务启动器 (代理池 + VirtualBrowser + FPBrowser2API)

echo ========================================================
echo   AI号池全套服务一键启动器
echo ========================================================
echo.

set "PY_EXE=python"
if exist "D:\Python313\python.exe" (
    set "PY_EXE=D:\Python313\python.exe"
)

echo [1/3] 正在启动 10 节点独立代理池服务 (端口: 7891~7900)...
if exist "%~dp0bin\mihomo.exe" (
    if exist "%~dp0data\worker_proxy_pool.yaml" (
        start "Mihomo 10-Proxy Pool" /d "%~dp0" "%~dp0bin\mihomo.exe" -f "%~dp0data\worker_proxy_pool.yaml"
    )
)

timeout /t 1 /nobreak >nul

echo [2/3] 正在启动 VirtualBrowser API 服务 (端口: 9000)...
if exist "%~dp0..\VirtualBrowser\api_server" (
    start "VirtualBrowser API Server" /d "%~dp0..\VirtualBrowser\api_server" cmd /k "%PY_EXE% server.py"
) else (
    echo [提示] 未在同级目录找到 VirtualBrowser，请确认手动启动 VirtualBrowser 客户端。
)

timeout /t 2 /nobreak >nul

echo [3/3] 正在启动 FPBrowser2API 调度网关服务 (端口: 8000)...
start "FPBrowser2API Gateway" /d "%~dp0" cmd /k "%PY_EXE% main.py"

echo.
echo ========================================================
echo   所有服务已成功启动！
echo   - 10 节点独立代理池: 127.0.0.1:7891 ~ 7900
echo   - VirtualBrowser API: http://127.0.0.1:9000
echo   - FPBrowser2API 网关: http://127.0.0.1:8000
echo   请保持弹出的服务窗口运行，最小化即可。
echo ========================================================
timeout /t 5
