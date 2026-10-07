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

"""Đào đa thị trường — compare one niche across countries/languages."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from pixelle_video.services.niche.service import MARKETS
from web.components.niche_ui import (
    PERIODS,
    download_excel,
    get_service,
    page_header,
    render_video_table,
    require_youtube,
    run,
    usage_caption,
)

page_header("Nghiên cứu", "Đào đa thị trường",
            "Một chủ đề, nhiều quốc gia: AI dịch từ khoá sang ngôn ngữ bản địa, chấm điểm ngách từng thị trường "
            "và nhân với RPM để tìm nơi đáng làm nhất (re-up, dịch, lồng tiếng).")

if not require_youtube():
    st.stop()
svc = get_service()

with st.form("mm_form"):
    c1, c2 = st.columns([4, 1])
    kw = c1.text_input("Chủ đề", placeholder="vd: phim tổng tài", label_visibility="collapsed")
    submitted = c2.form_submit_button("🌏 So sánh", type="primary", width="stretch")
    regions = st.multiselect("Thị trường", list(MARKETS), default=["VN", "US", "ID", "TH", "PH", "IN"],
                             format_func=lambda r: f"{MARKETS[r][1]} ({r})")
    f1, f2 = st.columns(2)
    period = f1.selectbox("Khoảng thời gian", ["7d", "30d", "90d", "1y"], index=1, format_func=PERIODS.get)
    translate = f2.checkbox("AI dịch từ khoá theo từng thị trường", value=True)
    st.caption(f"Ước tính ~{len(regions) * 122} units YouTube API.")

if submitted and kw.strip() and regions:
    st.session_state.mm = run(svc.multi_market(kw.strip(), regions, period, translate),
                              f"Đang quét {len(regions)} thị trường...")

data = st.session_state.get("mm")
if not data:
    st.stop()
usage_caption(data["usage"])
rows = data["markets"]
df = pd.DataFrame([{
    "Thị trường": r.get("market", r["region"]), "Từ khoá": r.get("keyword"), "Điểm thị trường": r.get("market_score"),
    "Điểm ngách": r.get("niche_score"), "Nhu cầu": r.get("demand"), "Cơ hội": r.get("opportunity"),
    "Cạnh tranh": r.get("competition"), "View TV": r.get("median_views"), "RPM ($)": r.get("rpm_usd"),
    "Lỗi": r.get("error", ""),
} for r in rows])
st.dataframe(df, hide_index=True, width="stretch", column_config={
    "Điểm thị trường": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
    "Nhu cầu": st.column_config.NumberColumn(format="percent"),
    "Cơ hội": st.column_config.NumberColumn(format="percent"),
    "Cạnh tranh": st.column_config.NumberColumn(format="percent"),
    "View TV": st.column_config.NumberColumn(format="compact"),
})
st.caption("Điểm thị trường = điểm ngách × (0.6 + 0.4 × min(RPM/5$, 1)) — ưu tiên thị trường vừa dễ vừa trả tiền cao.")
valid = [r for r in rows if "niche_score" in r]
if valid:
    st.bar_chart(pd.DataFrame({"Thị trường": [r["market"] for r in valid],
                               "Điểm thị trường": [r["market_score"] for r in valid]}),
                 x="Thị trường", y="Điểm thị trường", height=260)
for r in valid:
    with st.expander(f"Top video — {r['market']} · “{r['keyword']}”"):
        render_video_table(r["top"], key=f"mm_{r['region']}", height=230)
download_excel({"Markets": df}, f"markets_{data['keyword']}.xlsx")
