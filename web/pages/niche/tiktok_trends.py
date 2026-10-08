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

"""Xu hướng TikTok — trending on TikTok/Douyin for picking products at the right time."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_ui import (
    chips,
    get_service,
    page_header,
    platform_label,
    render_video_table,
    run,
    usage_caption,
)

page_header("TikTok Affiliate", "Xu hướng TikTok",
            "Bắt sản phẩm / hashtag / nội dung đang nóng trên TikTok và Douyin để chọn đúng thời điểm lên video.")

svc = get_service()
if not svc.cfg.tikhub_api_key:
    st.warning("⚠️ Cần **TikHub API key** cho xu hướng TikTok/Douyin. Reddit/Google Trends vẫn chạy không cần key.")
c1, c2 = st.columns([4, 1])
region = c1.selectbox("Thị trường", ["VN", "TH", "ID", "CN", "US"], format_func={"VN": "Việt Nam", "TH": "Thái Lan",
                      "ID": "Indonesia", "CN": "Trung Quốc", "US": "Mỹ"}.get)
if c2.button("📈 Lấy xu hướng", type="primary", width="stretch"):
    st.session_state.tkt = run(svc.trends(region, "", ["tiktok", "douyin", "google"]), "Đang gom xu hướng...")

data = st.session_state.get("tkt")
if not data:
    st.stop()
for s, err in data["errors"].items():
    st.warning(f"{s}: {err}")
usage_caption(data.get("tikhub_usage", {}))
if data.get("cross_platform"):
    st.markdown("#### 🔗 Từ khoá xuất hiện nhiều nền tảng")
    chips([f"{r['term']} · {r['n_sources']}" for r in data["cross_platform"]])
vids = {k: data[k] for k in ("tiktok", "douyin") if isinstance(data.get(k), list)}
if vids:
    tabs = st.tabs([platform_label(k) for k in vids])
    for tab, k in zip(tabs, vids):
        with tab:
            render_video_table(data[k], key=f"tkt_{k}")
if data.get("google"):
    import pandas as pd
    st.markdown("#### 🔎 Google Trends")
    st.dataframe(pd.DataFrame([{"Từ khoá": g["keyword"], "Lượt tìm": g["traffic"]} for g in data["google"]]),
                 hide_index=True, width="stretch")
