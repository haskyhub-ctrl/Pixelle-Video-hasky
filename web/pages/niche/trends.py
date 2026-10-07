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

"""Xu hướng đa nền tảng — cross-platform trends."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from pixelle_video.services.niche.sources import PLATFORMS
from web.components.niche_ui import (
    REGIONS,
    cfg,
    chips,
    get_service,
    page_header,
    platform_label,
    render_video_table,
    run,
    usage_caption,
)

page_header("Nghiên cứu", "Xu hướng đa nền tảng",
            "Gom xu hướng hôm nay từ YouTube Trending, Google Trends, Reddit và (nếu có TikHub) TikTok/Douyin… "
            "rồi tìm từ khoá xuất hiện trên nhiều nền tảng cùng lúc.")

svc = get_service()
YT_CATEGORIES = {"": "Tất cả", "1": "Phim & hoạt hình", "10": "Âm nhạc", "17": "Thể thao", "20": "Game",
                 "22": "Người & blog", "23": "Hài", "24": "Giải trí", "25": "Tin tức", "26": "Hướng dẫn",
                 "27": "Giáo dục", "28": "Khoa học & công nghệ"}
SOURCES = {"youtube": "YouTube Trending", "google": "Google Trends", "reddit": "Reddit"}
SOURCES.update({k: v["label"] for k, v in PLATFORMS.items() if v["source"] == "tikhub"})

with st.form("trends_form"):
    f1, f2 = st.columns(2)
    region = f1.selectbox("Quốc gia", list(REGIONS), format_func=REGIONS.get,
                          index=list(REGIONS).index(cfg().default_region) if cfg().default_region in REGIONS else 0)
    cat = f2.selectbox("Danh mục YouTube", list(YT_CATEGORIES), format_func=YT_CATEGORIES.get)
    include = st.multiselect("Nguồn", list(SOURCES), default=["youtube", "google", "reddit"], format_func=SOURCES.get)
    submitted = st.form_submit_button("📈 Lấy xu hướng", type="primary")

if submitted:
    st.session_state.trends = run(svc.trends(region, cat, include), "Đang gom xu hướng...")

data = st.session_state.get("trends")
if not data:
    st.stop()
for src, err in data["errors"].items():
    st.warning(f"**{SOURCES.get(src, src)}**: {err}")
usage_caption({**data.get("usage", {}), **data.get("tikhub_usage", {})})

if data.get("cross_platform"):
    st.markdown("#### 🔗 Từ khoá xuất hiện trên nhiều nền tảng")
    chips([f"{r['term']} · {r['n_sources']}" for r in data["cross_platform"]])

if data.get("google"):
    st.markdown("#### 🔎 Google Trends hôm nay")
    st.dataframe(pd.DataFrame([{"Từ khoá": g["keyword"], "Lượt tìm": g["traffic"], "Tin liên quan": " | ".join(g["news"])}
                               for g in data["google"]]), hide_index=True, width="stretch")

video_sources = [k for k in data if k not in ("errors", "usage", "tikhub_usage", "cross_platform", "google")]
if video_sources:
    tabs = st.tabs([SOURCES.get(k, platform_label(k)) for k in video_sources])
    for tab, k in zip(tabs, video_sources):
        with tab:
            render_video_table(data[k], key=f"tr_{k}")
