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

"""Tổng quan — dashboard of the niche research workspace."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_ui import get_service, page_header, render_api_settings

page_header("Bảng điều khiển", "Tổng quan",
            "Toàn bộ công cụ nghiên cứu ngách, sáng tạo nội dung và tối ưu kênh trong một nơi.")

svc = get_service()
ov = svc.overview()

c1, c2, c3 = st.columns(3)
c1.markdown(("✅" if ov["youtube_ready"] else "⚠️") + " **YouTube API** " + ("đã kết nối" if ov["youtube_ready"] else "chưa có key"))
c2.markdown(("✅" if ov["tikhub_ready"] else "➖") + " **TikHub** " + ("đã kết nối" if ov["tikhub_ready"] else "chưa có key (tuỳ chọn)"))
c3.markdown(("✅" if ov["llm_ready"] else "⚠️") + " **LLM (AI)** " + ("đã cấu hình" if ov["llm_ready"] else "chưa cấu hình"))
render_api_settings(expanded=not ov["youtube_ready"])

yt_today = ov["usage_today"].get("youtube", {})
th_today = ov["usage_today"].get("tikhub", {})
m = st.columns(5)
m[0].metric("Quota YouTube hôm nay", f"{int(yt_today.get('units') or 0):,} / 10,000")
m[1].metric("Chi phí TikHub hôm nay", f"{(th_today.get('cost_usd') or 0) * svc.cfg.usd_to_vnd:,.0f}đ")
m[2].metric("Ngách đã lưu", len(ov["saved_niches"]))
m[3].metric("Kênh theo dõi", len(ov["tracked_channels"]))
m[4].metric("Nội dung trong lịch", ov["calendar_total"])

st.markdown("#### Bắt đầu nhanh")
FLOW = [
    ("pages/niche/niche_finder.py", "⛏️", "Đào ngách", "Tìm ngách và video vượt trội đa nền tảng"),
    ("pages/niche/winning_topics.py", "🏆", "Chủ đề thắng", "AI rút công thức và đề xuất chủ đề"),
    ("pages/niche/script_studio.py", "✍️", "Studio kịch bản", "Viết kịch bản → tạo video"),
    ("pages/niche/content_calendar.py", "📅", "Lịch đăng", "Lên lịch và theo dõi tiến độ"),
    ("pages/niche/monetization.py", "💰", "Kiểm tra kiếm tiền", "Điều kiện YPP và ước tính thu nhập"),
    ("pages/niche/channel_doctor.py", "🩺", "Bác sĩ kênh", "Chẩn đoán và kế hoạch 30 ngày"),
]
cols = st.columns(3)
for i, (page, icon, label, desc) in enumerate(FLOW):
    with cols[i % 3].container(border=True):
        st.page_link(page, label=label, icon=icon)
        st.caption(desc)

left, right = st.columns(2)
with left:
    st.markdown("#### 🔖 Ngách đã lưu gần đây")
    for n in ov["saved_niches"][:6]:
        st.markdown(f"- **{n['query']}** — {n['niche_score']:.0f}/100 · {n['summary'].get('verdict', '')}")
    if not ov["saved_niches"]:
        st.caption("Chưa có. Lưu từ trang Đào ngách.")
with right:
    st.markdown("#### 📅 Sắp đăng")
    for c in ov["upcoming"][:6]:
        st.markdown(f"- {c['scheduled_at'][:16].replace('T', ' ')} · **{c['title']}** ({c['status']})")
    if not ov["upcoming"]:
        st.caption("Lịch trống.")
