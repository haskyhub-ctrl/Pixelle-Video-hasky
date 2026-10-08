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

"""Lịch đăng video (affiliate) — same calendar, TikTok default, golden-hours hint."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from web.components.niche_ui import get_service, page_header

page_header("TikTok Affiliate", "Lịch đăng video",
            "Lên lịch 2–3 video/ngày cho mỗi sản phẩm theo giờ vàng TikTok Shop, theo dõi từ ý tưởng tới đã đăng.")

svc = get_service()
STATUSES = {"idea": "💡 Ý tưởng", "script": "✍️ Có kịch bản", "production": "🎬 Đang quay",
            "scheduled": "⏰ Đã hẹn giờ", "published": "✅ Đã đăng"}
st.info("🕒 Giờ vàng TikTok Shop VN (tham khảo): 11h–13h, 19h–23h. Khung 21h–23h thường view gấp ~2× trung bình.")

with st.expander("➕ Thêm video", expanded=False):
    with st.form("afcal_add", clear_on_submit=True):
        title = st.text_input("Sản phẩm / tiêu đề video")
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Ngày", datetime.now().date() + timedelta(days=1))
        t = c2.time_input("Giờ", time(21, 0))
        status = c3.selectbox("Trạng thái", list(STATUSES), format_func=STATUSES.get)
        notes = st.text_area("Ghi chú", height=70)
        if st.form_submit_button("Lưu", type="primary") and title.strip():
            svc.storage.add_calendar(title.strip(), datetime.combine(d, t), "tiktok", status, notes=notes)
            st.rerun()

items = [c for c in svc.storage.list_calendar() if c["platform"] in ("tiktok", "tiktok_shop")]
all_items = svc.storage.list_calendar()
if not all_items:
    st.info("Lịch trống. Thêm từ Kịch bản video bán hàng hoặc thêm thủ công ở trên.")
    st.stop()
show = items or all_items
df = pd.DataFrame(show)
df["scheduled_at"] = pd.to_datetime(df["scheduled_at"], format="ISO8601")
st.dataframe(df[["scheduled_at", "title", "platform", "status", "notes"]].sort_values("scheduled_at"),
             hide_index=True, width="stretch", column_config={
                 "scheduled_at": st.column_config.DatetimeColumn("Lịch", format="ddd DD/MM HH:mm"),
                 "title": "Sản phẩm / video", "platform": "Nền tảng", "status": "Trạng thái", "notes": "Ghi chú"})
st.page_link("pages/niche/content_calendar.py", label="📅 Mở lịch đầy đủ (mọi nền tảng)", icon="➡️")
