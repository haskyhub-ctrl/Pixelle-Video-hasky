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

"""Kiểm tra kiếm tiền — YouTube Partner Program eligibility and revenue estimate."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from pixelle_video.services.niche import formulas
from web.components.niche_ui import (
    NICHES,
    REGIONS,
    cfg,
    fmt_num,
    get_service,
    page_header,
    require_youtube,
    run,
    usage_caption,
)

page_header("Miễn phí", "Kiểm tra kiếm tiền",
            "Dán link kênh YouTube để kiểm tra điều kiện bật kiếm tiền (YPP) và ước tính thu nhập theo ngách, quốc gia.")

if not require_youtube():
    st.stop()

svc = get_service()
with st.form("monet"):
    ref = st.text_input("Kênh", placeholder="https://www.youtube.com/@tenkenh hoặc @tenkenh hoặc link video")
    c1, c2 = st.columns(2)
    niche = c1.selectbox("Ngách", list(NICHES), format_func=NICHES.get)
    country = c2.selectbox("Quốc gia khán giả chính", ["auto"] + list(REGIONS),
                           format_func=lambda x: "Tự nhận theo kênh" if x == "auto" else REGIONS[x])
    submitted = st.form_submit_button("🔍 Kiểm tra", type="primary")

if submitted and ref.strip():
    st.session_state.monet_result = run(svc.monetization(ref, niche, "" if country == "auto" else country),
                                        "Đang tải dữ liệu kênh...")

data = st.session_state.get("monet_result")
if not data:
    st.stop()

ch, chk = data["channel"], data["check"]
usage_caption(data["usage"])
h1, h2 = st.columns([1, 6])
if ch.thumbnail:
    h1.image(ch.thumbnail, width=80)
h2.markdown(f"### [{ch.title}]({ch.url})\n{fmt_num(ch.subscribers)} sub · {fmt_num(ch.total_views)} views · "
            f"{ch.video_count} video · quốc gia tính RPM: **{data['country']}** · đã quét {data['videos']} video gần nhất")

if chk["ypp_full_eligible"]:
    st.success("✅ Kênh đủ điều kiện **YPP đầy đủ** (chia sẻ doanh thu quảng cáo).")
elif chk["ypp_early_eligible"]:
    st.info("🟡 Kênh đủ điều kiện **YPP giai đoạn đầu** (Super Thanks, hội viên, Shopping) — chưa có doanh thu quảng cáo.")
else:
    st.warning("⏳ Kênh chưa đủ điều kiện kiếm tiền.")

full = formulas.YPP_FULL
c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.markdown("**Người đăng ký**")
    st.progress(chk["progress_subs"], text=f"{chk['subscribers']:,} / {full['subs']:,}")
with c2.container(border=True):
    st.markdown("**Giờ xem 12 tháng (ước tính)**")
    st.progress(chk["progress_watch_hours"], text=f"{chk['est_watch_hours_12m']:,} / {full['watch_hours']:,} giờ")
with c3.container(border=True):
    st.markdown("**View Shorts 90 ngày**")
    st.progress(chk["progress_shorts"], text=f"{fmt_num(chk['shorts_views_90d'])} / {fmt_num(full['shorts_views_90d'])}")
st.caption(f"Cần: ≥1.000 sub VÀ (≥4.000 giờ xem 12 tháng HOẶC ≥10M view Shorts 90 ngày). "
           f"Giờ xem ước tính = Σ views × thời lượng × AVD {cfg().avd_ratio:.0%} của video dài đăng trong 12 tháng "
           f"(dữ liệu công khai, chỉ mang tính tham khảo). Đã đăng {chk['uploads_90d']} video trong 90 ngày.")

fx = chk["usd_to_vnd"]
lo, hi = chk["est_monthly_revenue_range"]
r1, r2, r3 = st.columns(3)
r1.metric("RPM ước tính", f"${chk['rpm_usd']:.2f}", help="Doanh thu nhà sáng tạo / 1000 view video dài")
r2.metric("Thu nhập / tháng (ước tính)", f"${chk['est_monthly_revenue_usd']:,.0f}",
          f"≈ {chk['est_monthly_revenue_usd'] * fx:,.0f}đ", delta_color="off")
r3.metric("Khoảng dao động", f"${lo:,.0f} – ${hi:,.0f}", f"{lo * fx:,.0f}đ – {hi * fx:,.0f}đ", delta_color="off")
st.caption("Công thức: (view video dài 30 ngày / 1000 × RPM) + (view Shorts 30 ngày / 1000 × RPM × 6%). "
           "RPM = RPM quốc gia × hệ số ngách.")
