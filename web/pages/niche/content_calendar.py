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

"""Lịch đăng — content calendar with best posting slots and .ics export."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from datetime import datetime, time, timedelta

import pandas as pd
import streamlit as st

from pixelle_video.services.niche.service import WEEKDAYS_VI
from pixelle_video.services.niche.sources import PLATFORMS
from web.components.niche_ui import (
    get_service,
    page_header,
    platform_label,
    send_to_video_generator,
)

page_header("Sáng tạo", "Lịch đăng",
            "Quản lý ý tưởng → kịch bản → đã quay → đã đăng. Gợi ý khung giờ vàng lấy từ kênh bạn đã phân tích.")

svc = get_service()
STATUSES = {"idea": "💡 Ý tưởng", "script": "✍️ Có kịch bản", "production": "🎬 Đang làm", "scheduled": "⏰ Đã hẹn giờ",
            "published": "✅ Đã đăng"}

# Best slots from the last analysed channel (Phân tích kênh / Kênh của tôi)
slots = (st.session_state.get("my_data") or st.session_state.get("ca_data") or {}).get("posting_slots") or []
if slots:
    st.info("🕒 Khung giờ vàng (theo kênh đã phân tích): " + ", ".join(
        f"{WEEKDAYS_VI[s['weekday']]} {s['hour']:02d}:00" for s in slots[:3]))

with st.expander("➕ Thêm nội dung", expanded=False):
    with st.form("cal_add", clear_on_submit=True):
        title = st.text_input("Tiêu đề")
        c1, c2, c3, c4 = st.columns(4)
        d = c1.date_input("Ngày", datetime.now().date() + timedelta(days=1))
        default_hour = slots[0]["hour"] if slots else 19
        t = c2.time_input("Giờ", time(default_hour, 0))
        platform = c3.selectbox("Nền tảng", list(PLATFORMS), format_func=platform_label)
        status = c4.selectbox("Trạng thái", list(STATUSES), format_func=STATUSES.get)
        notes = st.text_area("Ghi chú", height=80)
        if st.form_submit_button("Lưu", type="primary") and title.strip():
            svc.storage.add_calendar(title.strip(), datetime.combine(d, t), platform, status, notes=notes)
            st.rerun()

items = svc.storage.list_calendar()
if not items:
    st.info("Lịch trống. Thêm từ trang Chủ đề thắng / Studio kịch bản hoặc thêm thủ công.")
    st.stop()

df = pd.DataFrame(items)
df["scheduled_at"] = pd.to_datetime(df["scheduled_at"], format="ISO8601")
edited = st.data_editor(
    df[["id", "scheduled_at", "title", "platform", "status", "notes"]],
    hide_index=True, width="stretch", key="cal_editor", disabled=["id"],
    column_config={
        "id": st.column_config.NumberColumn("#", width="small"),
        "scheduled_at": st.column_config.DatetimeColumn("Lịch", format="ddd DD/MM HH:mm"),
        "title": st.column_config.TextColumn("Tiêu đề", width="large"),
        "platform": st.column_config.SelectboxColumn("Nền tảng", options=list(PLATFORMS)),
        "status": st.column_config.SelectboxColumn("Trạng thái", options=list(STATUSES)),
        "notes": "Ghi chú",
    },
)
a, b, c = st.columns(3)
if a.button("💾 Lưu thay đổi", type="primary"):
    for row in edited.to_dict("records"):
        svc.storage.update_calendar(int(row["id"]), title=row["title"], platform=row["platform"],
                                    status=row["status"], notes=row["notes"] or "",
                                    scheduled_at=pd.Timestamp(row["scheduled_at"]).to_pydatetime())
    st.success("Đã lưu")
    st.rerun()


def to_ics(rows) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Pixelle-Video//Lich dang//VI"]
    for r in rows:
        start = pd.Timestamp(r["scheduled_at"]).to_pydatetime()
        lines += ["BEGIN:VEVENT", f"UID:pixelle-{r['id']}@pixelle-video",
                  f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{start + timedelta(minutes=30):%Y%m%dT%H%M%S}",
                  f"SUMMARY:[{r['platform']}] {r['title']}",
                  f"DESCRIPTION:{(r.get('notes') or '').replace(chr(10), ' ')}", "END:VEVENT"]
    return "\r\n".join(lines + ["END:VCALENDAR"])


b.download_button("📆 Xuất .ics (Google Calendar)", to_ics(items), file_name="lich_dang.ics", mime="text/calendar")
with c.popover("🗑️ Xoá / 🎬 Tạo video"):
    pick = st.selectbox("Mục", [i["id"] for i in items],
                        format_func=lambda i: next(x["title"] for x in items if x["id"] == i))
    item = next(x for x in items if x["id"] == pick)
    if st.button("🎬 Tạo video từ mục này", disabled=not (item.get("script") or item.get("title"))):
        send_to_video_generator(item.get("script") or item["title"], item["title"], fixed=bool(item.get("script")))
    if st.button("🗑️ Xoá"):
        svc.storage.delete_calendar(pick)
        st.rerun()

st.markdown("#### Tuần này")
week_start = datetime.now().date() - timedelta(days=datetime.now().weekday())
cols = st.columns(7)
for i, col in enumerate(cols):
    day = week_start + timedelta(days=i)
    with col.container(border=True):
        st.markdown(f"**{WEEKDAYS_VI[i]}**  \n{day:%d/%m}")
        for r in items:
            dt = pd.Timestamp(r["scheduled_at"]).to_pydatetime()
            if dt.date() == day:
                st.caption(f"{dt:%H:%M} {STATUSES.get(r['status'], '')[:2]} {r['title'][:40]}")
