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

"""Reusable channel analytics view (Phân tích kênh, Kênh của tôi, Bác sĩ kênh)."""

import pandas as pd
import streamlit as st

from pixelle_video.services.niche.service import WEEKDAYS_VI
from web.components.niche_ui import (
    download_excel,
    fmt_num,
    get_service,
    render_video_cards,
    render_video_table,
    require_llm,
    run,
    send_to_studio,
    usage_caption,
)


def render_channel_analysis(data: dict, key: str = "ca") -> None:
    svc = get_service()
    ch, s, b = data["channel"], data["stats"], data["breakout"]
    usage_caption(data.get("usage", {}))
    h1, h2 = st.columns([1, 6])
    if ch.thumbnail:
        h1.image(ch.thumbnail, width=88)
    h2.markdown(f"### [{ch.title}]({ch.url})\n{ch.handle} · {ch.country or '—'} · "
                f"tạo {ch.published_at:%d/%m/%Y}" if ch.published_at else f"### [{ch.title}]({ch.url})")

    m = st.columns(6)
    m[0].metric("Sub", fmt_num(ch.subscribers),
                f"{data['sub_growth_per_day']:+.2%}/ngày" if data.get("sub_growth_per_day") is not None else None)
    m[1].metric("Tổng view", fmt_num(ch.total_views))
    m[2].metric("View trung vị", fmt_num(s["median_views"]))
    m[3].metric("Video/tuần", s["uploads_per_week"])
    m[4].metric("Tỷ lệ hit (≥2x)", f"{s['hit_rate_2x']:.0%}")
    m[5].metric("Điểm tăng trưởng", f"{b['breakout_score']:.0f}/100")
    m2 = st.columns(6)
    m2[0].metric("Tỷ lệ Shorts", f"{s['shorts_share']:.0%}")
    m2[1].metric("Thời lượng TB", f"{s['avg_duration_sec'] // 60}:{s['avg_duration_sec'] % 60:02d}")
    m2[2].metric("Tương tác TB", f"{s['avg_engagement']:.2%}")
    m2[3].metric("View/Sub trung vị", s["views_per_sub_median"])
    m2[4].metric("Ngày đăng nhiều nhất", s["top_weekday"] or "—")
    m2[5].metric("Ngày từ video cuối", s["days_since_last_upload"] if s["days_since_last_upload"] is not None else "—")

    videos = data["videos"]
    if videos:
        df = pd.DataFrame([{"Ngày": v.published_at, "Views": v.views, "Outlier": v.scores.get("outlier"),
                            "Loại": "Shorts" if v.is_short else "Dài"} for v in videos if v.published_at])
        st.markdown("**Views theo thời gian**")
        st.scatter_chart(df, x="Ngày", y="Views", color="Loại", size="Outlier", height=280)

    tabs = st.tabs(["🏆 Video vượt trội", "📉 Video kém", "📋 Tất cả video", "🕒 Khung giờ đăng tốt", "🤖 AI phân tích"])
    with tabs[0]:
        render_video_cards(data["top"], limit=8, key=f"{key}_top",
                           action=("✍️ Làm chủ đề tương tự", lambda v: send_to_studio(v.title, reference=v.url)))
    with tabs[1]:
        render_video_table(data["flops"], key=f"{key}_flops", height=360)
    with tabs[2]:
        render_video_table(videos, key=f"{key}_all")
        download_excel({"Videos": videos, "Stats": [s]}, f"channel_{ch.channel_id}.xlsx", key=f"{key}_xlsx")
    with tabs[3]:
        from web.components.niche_ui import render_heatmap
        render_heatmap(svc.posting_heatmap(videos), key=f"{key}_heat")
        slots = data["posting_slots"]
        if slots:
            st.dataframe(pd.DataFrame([{"Ngày": WEEKDAYS_VI[x["weekday"]], "Giờ (GMT+7)": f"{x['hour']:02d}:00",
                                        "Số video": x["n"], "Điểm khung giờ": x["slot_score"]} for x in slots]),
                         hide_index=True)
            st.caption("Điểm khung giờ = trung vị outlier của video đăng ở khung đó × log2(1 + số video).")
    with tabs[4]:
        if require_llm() and st.button("✨ Phân tích chiến lược kênh", key=f"{key}_ai"):
            st.session_state[f"{key}_report"] = run(svc.channel_ai_report(data), "AI đang phân tích kênh...")
        rep = st.session_state.get(f"{key}_report")
        if rep:
            st.markdown(f"**Định vị:** {rep.positioning}")
            c1, c2 = st.columns(2)
            c1.markdown("**Trụ cột nội dung**\n" + "\n".join(f"- {x}" for x in rep.content_pillars))
            c1.markdown("**Điều hiệu quả**\n" + "\n".join(f"- {x}" for x in rep.what_works))
            c2.markdown("**Điều thất bại**\n" + "\n".join(f"- {x}" for x in rep.what_fails))
            c2.markdown("**Cơ hội**\n" + "\n".join(f"- {x}" for x in rep.opportunities))
