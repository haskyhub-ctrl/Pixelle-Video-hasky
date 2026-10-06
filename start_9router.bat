@echo off
setlocal
title 9Router

where 9router >nul 2>&1
if errorlevel 1 (
    echo [!] 9Router chua duoc cai.
    echo     1. Cai Node.js 20+ tu https://nodejs.org  (chon ban LTS)
    echo     2. Mo PowerShell va chay:  npm install -g 9router
    echo     3. Chay lai file nay.
    echo.
    pause
    exit /b 1
)

powershell -NoProfile -Command "if ((Test-NetConnection 127.0.0.1 -Port 20128 -WarningAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }" >nul 2>&1
if errorlevel 1 (
    echo Dang bat 9Router...
    start "9Router" /min 9router
    timeout /t 6 /nobreak >nul
) else (
    echo 9Router dang chay roi.
)

echo Mo dashboard: http://localhost:20128/dashboard
start "" "http://localhost:20128/dashboard"
