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

"""Nghiên cứu từ khoá — keyword research."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from web.components.niche_ui import (
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

page_header("Nghiên cứu", "Nghiên cứu từ khoá",
            "Mở rộng từ khoá từ gợi ý tìm kiếm YouTube (miễn phí), sau đó chấm điểm cơ hội: nhu cầu cao, "
            "đối thủ yếu, ít bão hoà.")

svc = get_service()
with st.form("kw_form"):
    c1, c2 = st.columns([4, 1])
    seed = c1.text_input("Từ khoá gốc", placeholder="vd: phim tổng tài", label_visibility="collapsed")
    submitted = c2.form_submit_button("🔑 Nghiên cứu", type="primary", width="stretch")
    f1, f2, f3, f4 = st.columns(4)
    region = f1.selectbox("Quốc gia", list(REGIONS), format_func=REGIONS.get,
                          index=list(REGIONS).index(cfg().default_region) if cfg().default_region in REGIONS else 0)
    deep = f2.checkbox("Mở rộng A–Z", value=True, help="Gợi ý cho 'từ khoá + a…z' và các tiền tố câu hỏi")
    analyze = f3.number_input("Chấm điểm top N từ khoá", 0, 20, 5,
                              help="Mỗi từ khoá tốn ~102 units YouTube API. 0 = chỉ lấy gợi ý (miễn phí)")
    trends = f4.checkbox("Kèm Google Trends", value=False, help="Cần cài gói pytrends")

if submitted and seed.strip():
    if analyze and not cfg().youtube_api_key:
        st.warning("Chưa có YouTube API key → chỉ lấy gợi ý từ khoá.")
        analyze = 0
    st.session_state.kw = run(svc.keyword_research(seed.strip(), region, REGION_LANG.get(region, "en"),
                                                   int(analyze), deep, trends), "Đang mở rộng và chấm điểm từ khoá...")

data = st.session_state.get("kw")
if not data:
    if not cfg().youtube_api_key:
        require_youtube()
    st.stop()

usage_caption(data["usage"])
if data["analyzed"]:
    st.markdown("#### 🏆 Từ khoá đã chấm điểm")
    df = pd.DataFrame([{k: r.get(k) for k in ("keyword", "type", "keyword_score", "median_views", "median_subs",
                                              "total_results", "demand", "weakness", "saturation", "trend_interest",
                                              "error")} for r in data["analyzed"]])
    df["type"] = df["type"].map({"short": "Ngắn", "long_tail": "Dài"})
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "keyword": "Từ khoá", "type": "Loại",
        "keyword_score": st.column_config.ProgressColumn("Điểm cơ hội", min_value=0, max_value=100, format="%.0f"),
        "median_views": st.column_config.NumberColumn("View TV top 20", format="compact"),
        "median_subs": st.column_config.NumberColumn("Sub TV đối thủ", format="compact"),
        "total_results": st.column_config.NumberColumn("Số kết quả", format="compact"),
        "demand": st.column_config.NumberColumn("Nhu cầu", format="percent"),
        "weakness": st.column_config.NumberColumn("Đối thủ yếu", format="percent"),
        "saturation": st.column_config.NumberColumn("Bão hoà", format="percent"),
        "trend_interest": "Trends", "error": "Lỗi",
    })
    st.caption("Điểm = 100 × (0.45·nhu cầu + 0.35·độ yếu đối thủ + 0.20·(1 − bão hoà)). "
               "Nhu cầu = logistic(log10 view trung vị, tâm 10K); đối thủ yếu = 1 − logistic(log10 sub trung vị, tâm 100K).")
    for r in data["analyzed"][:5]:
        if r.get("top_titles"):
            with st.expander(f"Top video cho “{r['keyword']}”"):
                st.markdown("\n".join(f"- {t}" for t in r["top_titles"]))

sugg = pd.DataFrame(data["suggestions"])
if not sugg.empty:
    short = sugg[sugg["type"] == "short"]["keyword"].tolist()
    long_ = sugg[sugg["type"] == "long_tail"]["keyword"].tolist()
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown(f"**Từ khoá ngắn ({len(short)})**  \n<small>Lượng tìm lớn, cạnh tranh cao</small>", unsafe_allow_html=True)
        st.code("\n".join(short) or "—", language=None)
    with c2.container(border=True):
        st.markdown(f"**Từ khoá dài ({len(long_)})**  \n<small>Ít cạnh tranh — nên làm trước</small>", unsafe_allow_html=True)
        st.code("\n".join(long_) or "—", language=None)
download_excel({"Scored": data["analyzed"] or [{}], "Suggestions": data["suggestions"] or [{}]},
               f"keywords_{data['seed']}.xlsx")
