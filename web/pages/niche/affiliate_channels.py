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

"""Kênh affiliate làm tốt — TikTok sellers in a niche, ranked by real views."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from collections import defaultdict

import pandas as pd
import streamlit as st

from pixelle_video.services.niche import SearchFilters, formulas
from web.components.niche_ui import get_service, page_header, run

page_header("TikTok Affiliate", "Kênh affiliate làm tốt",
            "Tìm kênh TikTok đang bán tốt trong ngách: gom video theo kênh, xếp theo view thật và tỷ lệ view/follow.")

svc = get_service()
if not svc.cfg.tikhub_api_key:
    st.warning("⚠️ Cần **TikHub API key** để quét kênh TikTok. Cắm ở trang Kết nối API.")
    st.page_link("pages/niche/connect_api.py", label="🔌 Tới Kết nối API", icon="➡️")
    st.stop()

with st.form("afc_form"):
    c1, c2 = st.columns([4, 1])
    kw = c1.text_input("Ngách / sản phẩm", placeholder="vd: máy massage, mỹ phẩm...", label_visibility="collapsed")
    submitted = c2.form_submit_button("🔎 Tìm kênh", type="primary", width="stretch")

if submitted and kw.strip():
    f = SearchFilters(query=kw.strip(), platforms=["tiktok"], period="30d", max_results=50, strict_topic=False)
    st.session_state.afc = run(svc.search(f), "Đang quét video TikTok và gom theo kênh...")

res = st.session_state.get("afc")
if not res:
    st.stop()
for p, err in res.errors.items():
    st.warning(f"{p}: {err}")

groups = defaultdict(list)
for v in res.videos:
    groups[(v.channel_id or v.channel_title)].append(v)
rows = []
for key, vids in groups.items():
    subs = max((v.channel_subscribers for v in vids), default=0)
    med = formulas.median([v.views for v in vids])
    rows.append({"Kênh": vids[0].channel_title or key, "Số video (ngách)": len(vids),
                 "View trung vị": med, "Follower": subs or None,
                 "View/Follow": round(med / max(subs, 1), 2) if subs else None,
                 "Tổng view": sum(v.views for v in vids),
                 "Link": vids[0].url})
rows.sort(key=lambda r: r["Tổng view"], reverse=True)
st.markdown(f"Tìm thấy **{len(rows)}** kênh đang làm nội dung ngách này.")
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
    "View trung vị": st.column_config.NumberColumn(format="compact"),
    "Follower": st.column_config.NumberColumn(format="compact"),
    "Tổng view": st.column_config.NumberColumn(format="compact"),
    "Link": st.column_config.LinkColumn("Mở", display_text="↗")})
st.caption(f"Đã quét {len(res.videos)} video. View/Follow cao = kênh nhỏ nhưng bán/nổ tốt — mẫu để học.")
