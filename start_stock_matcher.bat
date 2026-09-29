@echo off
setlocal
cd /d "%~dp0"

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
    goto :end
)

if not exist ".venv" (
    echo [1/3] Installing dependencies, first run takes a few minutes...
    uv sync
    if errorlevel 1 (
        echo [ERROR] uv sync failed. See the messages above.
        goto :end
    )
)

if not exist ".env" (
    echo [2/3] Creating .env - fill in your API keys, save, then close Notepad.
    copy ".env.example" ".env" >nul
    notepad ".env"
)

echo [3/3] Starting Stock Matcher at http://localhost:8501
echo Press Ctrl+C in this window to stop.
echo.
uv run streamlit run pixelle_video/stock_matcher/app.py
if errorlevel 1 echo [ERROR] Stock Matcher stopped with an error. See the messages above.

:end
echo.
pause
