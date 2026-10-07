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

"""Đào ngách đa nền tảng — multi-platform niche mining."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from pixelle_video.services.niche import SearchFilters
from pixelle_video.services.niche import ai as niche_ai
from pixelle_video.services.niche.sources import CHINA_PLATFORMS, PLATFORMS
from web.components.niche_ui import (
    DURATIONS,
    ORDERS,
    PERIODS,
    REGION_LANG,
    REGIONS,
    cfg,
    chips,
    download_excel,
    fmt_num,
    get_service,
    page_header,
    platform_label,
    render_api_settings,
    render_video_cards,
    render_video_table,
    require_llm,
    run,
    send_to_studio,
    usage_caption,
)

page_header("Tính năng số 1", "Đào ngách đa nền tảng",
            "Nhập một chủ đề — hệ thống quét đồng thời nhiều nền tảng, chấm điểm ngách, tìm video vượt trội "
            "và kênh nhỏ đang nổ view.")

svc = get_service()
ss = st.session_state

ALL = "Tất cả"
CHINA = "Bộ Trung Quốc"

with st.container(border=True):
    c1, c2 = st.columns([5, 1])
    query = c1.text_input("Chủ đề", value=ss.get("niche_query", ""), placeholder="vd: phim tổng tài",
                          label_visibility="collapsed")
    go = c2.button("⛏️ Đào ngay", type="primary", width="stretch")

    picked = st.pills("Nền tảng", list(PLATFORMS) + [ALL, CHINA], selection_mode="multi",
                      default=ss.get("niche_platforms", ["youtube"]),
                      format_func=lambda p: p if p in (ALL, CHINA) else platform_label(p),
                      label_visibility="collapsed")
    platforms = list(dict.fromkeys(
        p for sel in picked for p in (list(PLATFORMS) if sel == ALL else CHINA_PLATFORMS if sel == CHINA else [sel])))

    f1, f2 = st.columns([3, 2])
    period = f1.segmented_control("Thời gian", list(PERIODS), default="30d", format_func=PERIODS.get,
                                  label_visibility="collapsed") or "30d"
    duration = f2.segmented_control("Độ dài", list(DURATIONS), default="any", format_func=DURATIONS.get,
                                    label_visibility="collapsed") or "any"
    f3, f4, f5 = st.columns([3, 1.2, 0.8])
    order = f3.segmented_control("Sắp xếp", list(ORDERS), default="relevance", format_func=ORDERS.get,
                                 label_visibility="collapsed") or "relevance"
    region = f4.selectbox("Quốc gia", list(REGIONS), format_func=REGIONS.get, label_visibility="collapsed",
                          index=list(REGIONS).index(cfg().default_region) if cfg().default_region in REGIONS else 0)
    with_trends = f5.checkbox("Kèm Google Trends", value=False)

    o1, o2, o3, o4 = st.columns([2.5, 1.6, 1.4, 1.5])
    strict = o1.checkbox("Chỉ hiện nội dung đúng chủ đề", value=True)
    cap = o2.checkbox("Tối đa 3 video / kênh", value=True)
    hide_adult = o3.checkbox("Ẩn nội dung 18+", value=True)
    max_results = o4.select_slider("Số kết quả YouTube", [25, 50, 100, 150], value=50)

    filters = SearchFilters(query=query.strip() or "-", platforms=platforms or ["youtube"], period=period,
                            duration=duration, order=order, region=region,
                            language=REGION_LANG.get(region, "en"), max_results=max_results,
                            max_per_channel=3 if cap else 0, hide_adult=hide_adult, strict_topic=strict)
    est = svc.estimate_cost(filters)
    st.caption(f"Dự kiến ~{est['cost_vnd']:,}đ · {est['requests']} request · "
               f"{est['youtube_units']} units YouTube (quota miễn phí 10.000/ngày)")

render_api_settings()


def do_search(q: str):
    filters.query = q
    ss.niche_query = q
    ss.niche_platforms = picked
    res = run(svc.search(filters, with_trends=with_trends), f"Đang đào ngách “{q}” trên {len(filters.platforms)} nền tảng...")
    if res is not None:
        ss.niche_result = res
        ss.niche_insights = None
        ss.niche_translations = {}
        ss.setdefault("niche_drilled", [])


if go and query.strip():
    do_search(query.strip())

if ss.get("niche_rerun"):
    do_search(ss.pop("niche_rerun"))

if ss.get("niche_drill"):
    q = ss.pop("niche_drill")
    ss.setdefault("niche_drilled", [])
    if q not in ss.niche_drilled:
        ss.niche_drilled.append(q)
    do_search(q)

res = ss.get("niche_result")
if not res:
    st.stop()

for p, err in res.errors.items():
    st.warning(f"**{platform_label(p)}**: {err}")
usage_caption(res.usage)

# ---------------------------------------------------------------- toolbar
counts = " ".join(f"{platform_label(p)}: **{n}**" for p, n in res.platform_counts.items())
st.markdown(f"Tất cả **{len(res.videos)}** · {counts}")

t1, t2, t3, t4 = st.columns(4)
if t1.button("🈯 Dịch tiêu đề TQ", width="stretch"):
    cn = [v for v in res.videos if v.platform in CHINA_PLATFORMS]
    if not cn:
        st.info("Không có kết quả từ nền tảng Trung Quốc.")
    elif require_llm():
        out = run(niche_ai.translate_texts(svc.llm, [v.title for v in cn], "Vietnamese"), "Đang dịch...")
        if out:
            for v, tr_title in zip(cn, out):
                v.title = f"{tr_title}  ⟨{v.title}⟩"
            st.rerun()
if t2.button("🔖 Lưu ngách", width="stretch"):
    nid = svc.save_niche(res, ss.get("niche_insights").model_dump() if ss.get("niche_insights") else None)
    st.success(f"Đã lưu ngách #{nid} (xem ở trang Dữ liệu)")
with t3:
    download_excel({"Videos": res.videos, "Niche": [res.niche]}, f"niche_{res.filters.query}.xlsx")
if t4.button("✨ Phân tích AI", type="primary", width="stretch") and require_llm():
    ss.niche_insights = run(niche_ai.keyword_insights(svc.llm, res.filters.query, res.videos, res.filters.language),
                            "AI đang phân tích ngách...")

if res.hidden_off_topic or res.hidden_adult or res.hidden_channel_cap:
    st.caption(f"Đã ẩn {len(res.hidden_off_topic)} kết quả lạc đề · {res.hidden_adult} nội dung 18+ · "
               f"{res.hidden_channel_cap} video vượt giới hạn/kênh")
if ss.get("niche_drilled"):
    st.markdown("Đã đào sâu thêm:")
    chips(ss.niche_drilled)

# ---------------------------------------------------------------- niche score
n = res.niche
m = st.columns(6)
m[0].metric("Điểm ngách", f"{n.get('niche_score', 0):.0f}/100")
m[1].metric("Nhu cầu", f"{n.get('demand', 0):.0%}", help="Theo view trung vị (+ Google Trends nếu bật)")
m[2].metric("Cơ hội kênh nhỏ", f"{n.get('opportunity', 0):.0%}", help="% video của kênh <100K sub có views ≥ sub")
m[3].metric("Cạnh tranh", f"{n.get('competition', 0):.0%}", help="Tỷ trọng kênh ≥1M sub + sub trung vị")
m[4].metric("Độ mới", f"{n.get('freshness', 0):.0%}", help="% video đăng trong 30 ngày")
m[5].metric("View trung vị", fmt_num(n.get("median_views", 0)))
st.markdown(f"**{res.verdict}**" + (f" · Google Trends: {res.trend_interest:.0f}/100" if res.trend_interest else ""))

# ---------------------------------------------------------------- AI insights
ins = ss.get("niche_insights")
if ins:
    a, b, c = st.columns(3)
    with a.container(border=True):
        st.markdown("**Từ khoá ngắn**  \n<small>Lượng tìm lớn, cạnh tranh cao</small>", unsafe_allow_html=True)
        st.code("\n".join(ins.short_keywords), language=None)
    with b.container(border=True):
        st.markdown("**Từ khoá dài (long-tail)**  \n<small>Ít cạnh tranh, dễ lên top — nên làm trước</small>",
                    unsafe_allow_html=True)
        for i, kw in enumerate(ins.long_tail_keywords):
            if st.button(f"⛏️ {kw}", key=f"drill_{i}"):
                ss.niche_drill = kw
                st.rerun()
    with c.container(border=True):
        st.markdown("**Ngách con từ video đúng chủ đề**  \n<small>Chủ đề đang lặp lại ở video thắng</small>",
                    unsafe_allow_html=True)
        for sn in ins.sub_niches:
            st.markdown(f"- **{sn.name}** — {sn.description}")
    if ins.summary:
        st.info(ins.summary)

# ---------------------------------------------------------------- results
tab1, tab2, tab3, tab4 = st.tabs(["🔥 Video vượt trội", "📋 Bảng đầy đủ", "🌱 Kênh nhỏ nổ view", "🙈 Kết quả lạc đề"])
with tab1:
    render_video_cards(res.videos, limit=12,
                       action=("✍️ Viết kịch bản tương tự",
                               lambda v: send_to_studio(v.title, reference=f"{v.title} ({v.url})")), key="nf")
with tab2:
    render_video_table(res.videos, key="nf_table")
with tab3:
    small = [v for v in res.videos if 0 < v.channel_subscribers < 100_000 and v.scores.get("views_per_sub", 0) >= 1]
    st.caption("Video của kênh dưới 100K sub có views ≥ số sub — dấu hiệu ngách còn chỗ cho người mới.")
    render_video_table(small, key="nf_small", height=400)
with tab4:
    st.caption("Các video bị bộ lọc 'đúng chủ đề' ẩn đi — xem tất cả để kiểm tra.")
    render_video_table(res.hidden_off_topic, key="nf_hidden", height=400)
