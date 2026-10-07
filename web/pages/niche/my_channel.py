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

"""Kênh của tôi — track your own channels over time."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from web.components.niche_channel import render_channel_analysis
from web.components.niche_ui import get_service, page_header, require_youtube, run

page_header("Tối ưu kênh", "Kênh của tôi",
            "Lưu kênh của bạn, mỗi lần mở sẽ chụp lại số sub/view để vẽ đường tăng trưởng và so với chính kênh.")

if not require_youtube():
    st.stop()
svc = get_service()
mine = svc.storage.list_channels(mine_only=True)

with st.form("my_add"):
    c1, c2 = st.columns([4, 1])
    ref = c1.text_input("Thêm kênh của tôi", placeholder="@tenkenh hoặc link kênh", label_visibility="collapsed")
    if c2.form_submit_button("➕ Thêm", type="primary", width="stretch") and ref.strip():
        data = run(svc.channel_analysis(ref.strip(), 50, is_mine=True), "Đang tải kênh...")
        if data:
            st.session_state.my_data = data
            st.session_state.my_selected = data["channel"].channel_id
            st.rerun()

if not mine:
    st.info("Chưa có kênh nào. Thêm kênh của bạn ở trên.")
    st.stop()

ids = [m["channel_id"] for m in mine]
default = ids.index(st.session_state.get("my_selected")) if st.session_state.get("my_selected") in ids else 0
c1, c2, c3 = st.columns([4, 1, 1])
selected = c1.selectbox("Kênh", ids, index=default, format_func=lambda i: next(m["title"] for m in mine if m["channel_id"] == i),
                        label_visibility="collapsed")
refresh = c2.button("🔄 Cập nhật", width="stretch")
if c3.button("🗑️ Bỏ", width="stretch"):
    svc.storage.untrack_channel(selected)
    st.session_state.pop("my_data", None)
    st.rerun()

data = st.session_state.get("my_data")
if refresh or not data or data["channel"].channel_id != selected:
    data = run(svc.channel_analysis(selected, 50, is_mine=True), "Đang cập nhật số liệu kênh...")
    st.session_state.my_data = data
    st.session_state.my_selected = selected
if not data:
    st.stop()

snaps = data["snapshots"]
if len(snaps) >= 2:
    st.markdown("**Tăng trưởng theo các lần cập nhật**")
    df = pd.DataFrame([{"Thời điểm": s["ts"], "Sub": s["subscribers"], "Tổng view": s["total_views"]} for s in snaps])
    g1, g2 = st.columns(2)
    g1.line_chart(df, x="Thời điểm", y="Sub", height=220)
    g2.line_chart(df, x="Thời điểm", y="Tổng view", height=220)
else:
    st.caption("Mở lại trang này vào các ngày sau để có biểu đồ tăng trưởng (mỗi lần cập nhật lưu 1 snapshot).")

render_channel_analysis(data, "my")
st.page_link("pages/niche/channel_doctor.py", label="🩺 Khám kênh này ở Bác sĩ kênh", icon="➡️")
