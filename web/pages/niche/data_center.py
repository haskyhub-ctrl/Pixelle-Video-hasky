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

"""Dữ liệu — saved niches, tracked channels, API usage and settings."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from pixelle_video.services.niche import formulas
from web.components.niche_ui import (
    download_excel,
    get_service,
    page_header,
    render_api_settings,
    run,
)

page_header("Dữ liệu", "Ngách đã lưu & kênh theo dõi",
            "Kho dữ liệu cục bộ (SQLite): ngách đã lưu, kênh theo dõi kèm lịch sử sub, lịch sử dùng API.")

svc = get_service()
tab1, tab2, tab3 = st.tabs(["🔖 Ngách đã lưu", "📡 Kênh theo dõi", "⚙️ Cài đặt"])

with tab1:
    niches = svc.storage.list_niches()
    if not niches:
        st.info("Chưa lưu ngách nào.")
    for n in niches:
        with st.expander(f"{n['query']} — {n['niche_score']:.0f}/100 · {n['created_at'][:10]} · {n['platforms']}"):
            s = n["summary"]
            st.markdown(s.get("verdict", ""))
            st.json(s.get("niche", {}), expanded=False)
            if s.get("top"):
                st.dataframe(pd.DataFrame(s["top"]), hide_index=True, width="stretch",
                             column_config={"url": st.column_config.LinkColumn("Link")})
            ins = s.get("insights") or {}
            if ins.get("long_tail_keywords"):
                st.markdown("**Từ khoá dài:** " + ", ".join(ins["long_tail_keywords"]))
            a, b = st.columns(2)
            if a.button("⛏️ Đào lại", key=f"redo_{n['id']}"):
                st.session_state.niche_query = n["query"]
                st.session_state.niche_rerun = n["query"]
                st.switch_page("pages/niche/niche_finder.py")
            if b.button("🗑️ Xoá", key=f"del_{n['id']}"):
                svc.storage.delete_niche(n["id"])
                st.rerun()
    if niches:
        download_excel({"Niches": [{"query": n["query"], "score": n["niche_score"], "created": n["created_at"],
                                    **n["summary"].get("niche", {})} for n in niches]}, "ngach_da_luu.xlsx")

with tab2:
    chans = svc.storage.list_channels()
    if not chans:
        st.info("Chưa theo dõi kênh nào (thêm từ Săn kênh nổ view, Phân tích kênh hoặc Kênh của tôi).")
    rows = []
    for c in chans:
        snaps = svc.storage.snapshots(c["channel_id"])
        growth = formulas.sub_growth_rate([(s["ts"], s["subscribers"]) for s in snaps])
        rows.append({"Kênh": c["title"], "Của tôi": bool(c["is_mine"]), "Sub mới nhất": snaps[-1]["subscribers"] if snaps else None,
                     "Số snapshot": len(snaps), "Tăng sub/ngày": growth, "Link": c["data"].get("url"),
                     "channel_id": c["channel_id"]})
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df.drop(columns=["channel_id"]), hide_index=True, width="stretch", column_config={
            "Sub mới nhất": st.column_config.NumberColumn(format="compact"),
            "Tăng sub/ngày": st.column_config.NumberColumn(format="percent"),
            "Link": st.column_config.LinkColumn(display_text="↗")})
        a, b = st.columns(2)
        if a.button("🔄 Cập nhật snapshot tất cả kênh", help="~1 unit YouTube / 50 kênh"):
            async def refresh():
                yt = svc.youtube()
                for ch in await yt.channels([r["channel_id"] for r in rows]):
                    svc.storage.add_snapshot(ch.channel_id, ch.subscribers, ch.total_views, ch.video_count)
                return svc._log_yt(yt)
            if run(refresh(), "Đang cập nhật...") is not None:
                st.rerun()
        with b.popover("🗑️ Bỏ theo dõi"):
            pick = st.selectbox("Kênh", [r["channel_id"] for r in rows],
                                format_func=lambda i: next(r["Kênh"] for r in rows if r["channel_id"] == i))
            if st.button("Bỏ theo dõi"):
                svc.storage.untrack_channel(pick)
                st.rerun()

with tab3:
    render_api_settings(expanded=True)
    st.caption(f"Cơ sở dữ liệu: `{svc.cfg.db_path}`")
    usage = svc.storage.usage_today()
    if usage:
        st.markdown("**API đã dùng hôm nay (UTC)**")
        st.dataframe(pd.DataFrame(usage.values()), hide_index=True)
