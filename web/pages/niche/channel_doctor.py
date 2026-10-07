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

"""Bác sĩ kênh — rule-based + AI channel diagnosis with competitor benchmark."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from web.components.niche_ui import (
    fmt_num,
    get_service,
    page_header,
    render_video_table,
    require_youtube,
    run,
    usage_caption,
)

page_header("Tối ưu kênh", "Bác sĩ kênh",
            "Khám tổng quát kênh: tần suất, độ đều, tỷ lệ flop, xu hướng view, tương tác, metadata — so với đối thủ "
            "và kê đơn kế hoạch 30 ngày.")

if not require_youtube():
    st.stop()
svc = get_service()
mine = svc.storage.list_channels(mine_only=True)
default_ref = st.session_state.get("my_data", {}).get("channel").url if st.session_state.get("my_data") else (
    mine[0]["data"].get("url", "") if mine else "")

with st.form("doctor_form"):
    ref = st.text_input("Kênh cần khám", value=default_ref, placeholder="@tenkenh hoặc link kênh")
    comps = st.text_area("Kênh đối thủ (mỗi dòng một kênh, tuỳ chọn)", height=90)
    use_ai = st.checkbox("Kèm chẩn đoán AI", value=True)
    submitted = st.form_submit_button("🩺 Khám kênh", type="primary")

if submitted and ref.strip():
    st.session_state.doctor = run(svc.channel_doctor(ref.strip(), [c for c in comps.splitlines() if c.strip()], use_ai),
                                  "Đang khám kênh và đối thủ...")

data = st.session_state.get("doctor")
if not data:
    st.stop()
usage_caption(data.get("usage", {}))
ch = data["channel"]
score = data["health_score"]
color = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
st.markdown(f"### {color} Sức khoẻ kênh **{ch.title}**: {score}/100")
st.progress(score / 100)

SEV = {"high": "🔴 Nặng", "medium": "🟠 Vừa", "low": "🟡 Nhẹ"}
if data["checks"]:
    st.markdown("#### Kết quả kiểm tra tự động")
    st.dataframe(pd.DataFrame([{"Mức độ": SEV.get(c["severity"], c["severity"]), "Vấn đề": c["problem"],
                                "Số liệu": c["metric"], "Cách sửa": c["fix"]} for c in data["checks"]]),
                 hide_index=True, width="stretch")
else:
    st.success("Không phát hiện vấn đề nào từ kiểm tra tự động 👏")

if data["competitors"]:
    st.markdown("#### So với đối thủ")
    rows = [{"Kênh": ch.title + " (bạn)", **data["stats"]}] + [{"Kênh": c["title"], **c} for c in data["competitors"]]
    cols = ["Kênh", "subscribers", "median_views", "uploads_per_week", "avg_engagement", "hit_rate_2x", "flop_rate",
            "shorts_share", "avg_duration_sec"]
    df = pd.DataFrame(rows)[cols].rename(columns={
        "subscribers": "Sub", "median_views": "View TV", "uploads_per_week": "Video/tuần", "avg_engagement": "Tương tác",
        "hit_rate_2x": "Tỷ lệ hit", "flop_rate": "Tỷ lệ flop", "shorts_share": "Tỷ lệ Shorts", "avg_duration_sec": "Thời lượng TB (s)"})
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Sub": st.column_config.NumberColumn(format="compact"), "View TV": st.column_config.NumberColumn(format="compact"),
        "Tương tác": st.column_config.NumberColumn(format="percent"), "Tỷ lệ hit": st.column_config.NumberColumn(format="percent"),
        "Tỷ lệ flop": st.column_config.NumberColumn(format="percent"), "Tỷ lệ Shorts": st.column_config.NumberColumn(format="percent")})

rep = data.get("report")
if rep:
    st.markdown("#### 🤖 Chẩn đoán AI")
    st.info(rep.diagnosis)
    for issue in rep.issues:
        with st.container(border=True):
            st.markdown(f"{SEV.get(issue.severity, issue.severity)} **{issue.problem}**  \n"
                        f"<small>{issue.evidence}</small>  \n💊 {issue.fix}", unsafe_allow_html=True)
    if rep.action_plan_30_days:
        st.markdown("#### 📋 Kế hoạch 30 ngày")
        st.markdown("\n".join(f"{i}. {x}" for i, x in enumerate(rep.action_plan_30_days, 1)))

with st.expander("Video kém nhất (so với trung vị kênh)"):
    render_video_table(data["flops"], key="doc_flops", height=360)
st.caption(f"Đã phân tích {data['stats']['sample_size']} video gần nhất · view trung vị {fmt_num(data['stats']['median_views'])}. "
           "Điểm sức khoẻ = 100 − 20/vấn đề nặng − 10/vừa − 4/nhẹ.")
