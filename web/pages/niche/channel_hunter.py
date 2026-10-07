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

"""Săn kênh nổ view — find small channels that are breaking out."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from web.components.niche_ui import (
    DURATIONS,
    PERIODS,
    REGION_LANG,
    REGIONS,
    cfg,
    download_excel,
    get_service,
    page_header,
    require_youtube,
    run,
    usage_caption,
)

page_header("Nghiên cứu", "Săn kênh nổ view",
            "Tìm kênh nhỏ có video gần đây vượt xa số sub — dấu hiệu kênh đang được thuật toán đẩy. "
            "Mỗi lần quét sẽ lưu số sub để lần sau tính được tốc độ tăng trưởng thật.")

if not require_youtube():
    st.stop()
svc = get_service()

with st.form("hunt_form"):
    c1, c2 = st.columns([4, 1])
    query = c1.text_input("Chủ đề", placeholder="vd: review phim, kể chuyện lịch sử...", label_visibility="collapsed")
    submitted = c2.form_submit_button("🎯 Săn kênh", type="primary", width="stretch")
    f1, f2, f3, f4 = st.columns(4)
    period = f1.selectbox("Video đăng trong", ["7d", "30d", "90d", "1y"], index=1, format_func=PERIODS.get)
    max_subs = f2.selectbox("Sub tối đa", [10_000, 50_000, 100_000, 500_000], index=2, format_func=lambda x: f"{x:,}")
    duration = f3.selectbox("Định dạng", list(DURATIONS), format_func=DURATIONS.get)
    region = f4.selectbox("Quốc gia", list(REGIONS), format_func=REGIONS.get,
                          index=list(REGIONS).index(cfg().default_region) if cfg().default_region in REGIONS else 0)

if submitted and query.strip():
    st.session_state.hunt = run(svc.hunt_channels(query.strip(), period, max_subs, region,
                                                  REGION_LANG.get(region, "en"), duration),
                                "Đang quét video nhiều view và đánh giá từng kênh...")

data = st.session_state.get("hunt")
if not data:
    st.stop()

usage_caption(data["usage"])
rows = data["channels"]
st.markdown(f"Quét **{data['scanned_videos']}** video nhiều view → **{len(rows)}** kênh nhỏ ứng viên")
if not rows:
    st.info("Không có kênh nào dưới ngưỡng sub. Thử tăng 'Sub tối đa' hoặc đổi khoảng thời gian.")
    st.stop()

table = pd.DataFrame([{
    "Ảnh": r["channel"].thumbnail or None,
    "Điểm nổ": r["breakout_score"],
    "Kênh": r["channel"].title,
    "Sub": r["channel"].subscribers,
    "View TV gần đây": r["recent_median_views"],
    "View TV / Sub": r["recent_ratio"],
    "Tỷ lệ video > sub": r["hit_rate"],
    "Video/tuần": r["uploads_per_week"],
    "Tuổi kênh (ngày)": r["channel_age_days"],
    "Tăng sub/ngày": r["sub_growth_per_day"],
    "Video kích hoạt": r["trigger_video"].title if r["trigger_video"] else "",
    "Link": r["channel"].url,
} for r in rows])
st.dataframe(table, hide_index=True, height=560, width="stretch", column_config={
    "Ảnh": st.column_config.ImageColumn("", width="small"),
    "Điểm nổ": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.0f"),
    "Sub": st.column_config.NumberColumn(format="compact"),
    "View TV gần đây": st.column_config.NumberColumn(format="compact"),
    "Tỷ lệ video > sub": st.column_config.NumberColumn(format="percent"),
    "Tăng sub/ngày": st.column_config.NumberColumn(format="percent"),
    "Link": st.column_config.LinkColumn("Mở", display_text="↗"),
})
download_excel({"Channels": table.drop(columns=["Ảnh"])}, "san_kenh.xlsx")

st.caption("Điểm nổ = 100 × (0.30·f(view trung vị gần đây / sub) + 0.20·tỷ lệ video vượt sub + 0.15·độ trẻ kênh "
           "+ 0.15·độ nhỏ kênh + 0.20·tăng trưởng). Tăng trưởng dùng snapshot sub giữa các lần quét; lần đầu dùng "
           "tốc độ view của video tốt nhất.")

st.markdown("#### Theo dõi kênh")
pick = st.multiselect("Chọn kênh để theo dõi lâu dài", [r["channel"].channel_id for r in rows],
                      format_func=lambda cid: next(r["channel"].title for r in rows if r["channel"].channel_id == cid))
if st.button("➕ Theo dõi") and pick:
    for r in rows:
        if r["channel"].channel_id in pick:
            svc.storage.track_channel(r["channel"].channel_id, r["channel"].title,
                                      data={"url": r["channel"].url, "thumbnail": r["channel"].thumbnail})
    st.success(f"Đã thêm {len(pick)} kênh vào danh sách theo dõi (trang Dữ liệu).")
