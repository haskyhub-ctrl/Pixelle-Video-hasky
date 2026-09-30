@echo off
setlocal
cd /d "%~dp0"
title Stock Matcher

echo ========================================
echo   Stock Matcher - Pixelle-Video
echo ========================================
echo.

where uv >nul 2>&1
if errorlevel 1 (
    echo [ERROR] uv is not installed.
    echo.
    echo Open PowerShell and run:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    echo Then close PowerShell and run this file again.
    goto :fail
)

if not exist ".venv" (
    echo [1/3] Installing dependencies, first run takes a few minutes...
    uv sync
    if errorlevel 1 (
        echo [ERROR] uv sync failed. See the messages above.
        goto :fail
    )
)

if not exist ".env" (
    echo [2/3] Creating .env - fill in your API keys, save, then close Notepad.
    copy ".env.example" ".env" >nul
    notepad ".env"
)

echo [3/3] Opening the Stock Matcher window...
echo Keep this window open while you work. Closing the app window stops it.
echo.
uv run --with pywebview python -m pixelle_video.stock_matcher.desktop
if errorlevel 1 (
    echo.
    echo Native window failed, opening in a browser window instead...
    uv run python -m pixelle_video.stock_matcher.desktop --browser
    if errorlevel 1 goto :fail
)
exit /b 0

:fail
echo.
pause
exit /b 1
