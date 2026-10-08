# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Kết nối API — configure all data-source keys and test them live."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from pixelle_video.config import config_manager
from web.components.niche_ui import get_service, page_header, render_api_settings, run

page_header("Tài khoản", "Kết nối API",
            "Cắm key của bạn để chạy số liệu thật. Mọi key lưu trên máy bạn (config.yaml / .env), không gửi đi đâu.")

render_api_settings(expanded=True)

st.markdown("#### 🔌 Nguồn dữ liệu & trạng thái")
cfg = config_manager.config
rows = [
    ("LLM (AI)", cfg.is_llm_configured(), "Viết kịch bản, mổ băng, phân tích — OpenAI/DeepSeek/Qwen/Ollama"),
    ("YouTube Data API", bool(cfg.niche.youtube_api_key), "Toàn bộ khu YouTube"),
    ("TikHub", bool(cfg.niche.tikhub_api_key), "TikTok/Douyin + TikTok Shop (săn sản phẩm win)"),
    ("Reddit / Google Trends", True, "Không cần key"),
]
for name, ok, desc in rows:
    st.markdown(f"{'✅' if ok else '⚠️'} **{name}** — {desc}")

st.markdown("#### ✅ Kiểm tra kết nối (gọi thật)")
if st.button("Chạy kiểm tra", type="primary"):
    from pixelle_video.services.niche import doctor
    svc = get_service()
    cfgn = svc.cfg
    async def checks():
        out = []
        out.append(("YouTube", await doctor._check_youtube(cfgn)))
        out.append(("LLM", await doctor._check_llm(config_manager.config)))
        out.append(("Reddit", await doctor._check_reddit()))
        out.append(("Google Trends", await doctor._check_trends(cfgn)))
        if cfgn.tikhub_api_key:
            out.append(("TikHub · TikTok", await doctor._check_tikhub(cfgn, "tiktok")))
        return out
    res = run(checks(), "Đang gọi thử từng API...")
    if res:
        for name, (status, detail) in res:
            st.markdown(f"{status}  **{name}** — {detail}")

st.caption("Nguồn TikTok Shop (số đã bán, video gắn giỏ): mặc định dùng TikHub. Nếu bạn dùng Kalodata/EchoTik, "
           "báo mình để thêm adapter — chỉ cần endpoint + định dạng trả về.")
