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

"""Phân tích kênh TikTok — a seller channel's videos scored (via TikHub search)."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from pixelle_video.services.niche import SearchFilters
from web.components.niche_ui import get_service, page_header, render_video_table, run

page_header("TikTok Affiliate", "Phân tích kênh TikTok",
            "Xem các video của một kênh/ngách TikTok: video nào nổ, dạng nội dung nào bán tốt.")

svc = get_service()
if not svc.cfg.tikhub_api_key:
    st.warning("⚠️ Cần **TikHub API key**. Cắm ở trang Kết nối API.")
    st.page_link("pages/niche/connect_api.py", label="🔌 Tới Kết nối API", icon="➡️")
    st.stop()

with st.form("tca_form"):
    c1, c2 = st.columns([4, 1])
    kw = c1.text_input("Tên kênh / @handle / ngách", placeholder="@tenkenh hoặc tên sản phẩm", label_visibility="collapsed")
    submitted = c2.form_submit_button("🔍 Phân tích", type="primary", width="stretch")

if submitted and kw.strip():
    f = SearchFilters(query=kw.strip(), platforms=["tiktok"], period="90d", max_results=50, strict_topic=False)
    st.session_state.tca = run(svc.search(f), "Đang tải video TikTok...")

res = st.session_state.get("tca")
if not res:
    st.stop()
for p, err in res.errors.items():
    st.warning(f"{p}: {err}")
render_video_table(res.videos, key="tca_table")
st.caption("Video xếp theo điểm vượt trội. Dùng 'Mổ băng video bán hàng' để học công thức video thắng.")
