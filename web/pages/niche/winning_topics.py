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

"""Chủ đề thắng — derive winning formulas from outliers and propose new topics."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import datetime, timedelta

import streamlit as st

from pixelle_video.services.niche import SearchFilters
from pixelle_video.services.niche.sources import PLATFORMS
from web.components.niche_ui import (
    PERIODS,
    REGION_LANG,
    REGIONS,
    cfg,
    chips,
    get_service,
    page_header,
    platform_label,
    render_video_table,
    require_llm,
    require_youtube,
    run,
    send_to_studio,
    usage_caption,
)

page_header("Sáng tạo", "Chủ đề thắng",
            "Lấy các video vượt trội trong ngách, để AI rút ra công thức thắng và đề xuất chủ đề mới "
            "— bấm một chủ đề để viết kịch bản ngay.")

svc = get_service()
if not (require_youtube() and require_llm()):
    st.stop()

with st.form("wt_form"):
    c1, c2 = st.columns([4, 1])
    q = c1.text_input("Ngách", value=st.session_state.get("niche_query", ""), placeholder="vd: phim tổng tài",
                      label_visibility="collapsed")
    submitted = c2.form_submit_button("🏆 Tìm chủ đề", type="primary", width="stretch")
    f1, f2, f3, f4 = st.columns(4)
    platforms = f1.multiselect("Nền tảng", list(PLATFORMS), default=["youtube"], format_func=platform_label)
    period = f2.selectbox("Thời gian", ["7d", "30d", "90d", "1y"], index=1, format_func=PERIODS.get)
    region = f3.selectbox("Quốc gia", list(REGIONS), format_func=REGIONS.get,
                          index=list(REGIONS).index(cfg().default_region) if cfg().default_region in REGIONS else 0)
    count = f4.number_input("Số chủ đề", 5, 40, 15)

if submitted and q.strip():
    f = SearchFilters(query=q.strip(), platforms=platforms or ["youtube"], period=period, region=region,
                      language=REGION_LANG.get(region, "en"))
    st.session_state.wt = run(svc.winning_topics(q.strip(), f, int(count)), "Đang tìm video thắng và phân tích công thức...")

data = st.session_state.get("wt")
if not data:
    st.stop()
usage_caption(data["search"].usage)
t = data["topics"]

c1, c2 = st.columns(2)
with c1.container(border=True):
    st.markdown("**🧪 Công thức thắng**")
    st.markdown("\n".join(f"- {p}" for p in t.patterns))
with c2.container(border=True):
    st.markdown("**🏷️ Mẫu tiêu đề**")
    st.markdown("\n".join(f"- `{p}`" for p in t.title_formulas))

st.markdown(f"#### 💡 {len(t.topics)} chủ đề đề xuất")
for i, topic in enumerate(t.topics):
    with st.container(border=True):
        a, b, c = st.columns([6, 1.2, 1.2])
        a.markdown(f"**{topic.title}**  \n🎣 _{topic.hook}_  \n{topic.angle}")
        chips([topic.format, f"dựa trên: {topic.based_on[:60]}"] if topic.based_on else [topic.format])
        if b.button("✍️ Viết kịch bản", key=f"wt_s_{i}"):
            send_to_studio(topic.title, topic.hook, topic.based_on)
        if c.button("📅 Lên lịch", key=f"wt_c_{i}"):
            svc.storage.add_calendar(topic.title, datetime.now() + timedelta(days=1 + i), topic=topic.angle,
                                     notes=f"Hook: {topic.hook}")
            st.toast("Đã thêm vào Lịch đăng")

with st.expander(f"Video thắng dùng để phân tích ({len(data['winners'])})"):
    render_video_table(data["winners"], key="wt_winners", height=400)
