@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"
echo 🔎 Kiem tra ket noi API (so lieu that)...
uv run python -m pixelle_video.services.niche.doctor
echo.
echo 🚀 Mo giao dien web tai http://localhost:8501 ...
uv run streamlit run web/app.py
pause
