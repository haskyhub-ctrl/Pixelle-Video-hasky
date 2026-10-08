#!/bin/bash
# Khởi động app Nghiên cứu ngách (DeepNiche-style) + Pixelle-Video
set -e
cd "$(dirname "$0")"

echo "🔎 Kiểm tra kết nối API (số liệu thật)..."
uv run python -m pixelle_video.services.niche.doctor || true
echo ""
echo "🚀 Mở giao diện web tại http://localhost:8501 ..."
uv run streamlit run web/app.py
