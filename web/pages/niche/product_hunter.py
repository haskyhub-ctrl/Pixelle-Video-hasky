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

"""Săn sản phẩm win — TikTok Shop affiliate product hunting by real sales data."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_ui import (
    AFFILIATE_REGIONS,
    download_excel,
    fmt_num,
    get_service,
    page_header,
    products_frame,
    render_product_table,
    run,
    usage_caption,
)

page_header("TikTok Affiliate", "Săn sản phẩm win",
            "Tìm sản phẩm TikTok Shop đáng làm affiliate bằng SỐ LIỆU THẬT: số đã bán, tốc độ bán/ngày, "
            "đánh giá, số video gắn giỏ — chấm điểm Win 0–100.")

svc = get_service()
with st.form("ph_form"):
    c1, c2, c3 = st.columns([3, 1.3, 1])
    kw = c1.text_input("Từ khoá / ngành hàng (để trống = đang nóng)", placeholder="vd: máy massage, serum...",
                       label_visibility="collapsed")
    region = c2.selectbox("Nước", list(AFFILIATE_REGIONS), format_func=AFFILIATE_REGIONS.get, label_visibility="collapsed")
    submitted = c3.form_submit_button("🛒 Săn", type="primary", width="stretch")

if submitted:
    st.session_state.ph = run(svc.hunt_products(kw.strip(), region, 40), "Đang quét sản phẩm TikTok Shop...")

data = st.session_state.get("ph")
if not data:
    st.caption("Điểm Win = 100 × (0.35·tốc độ bán + 0.20·bằng chứng đánh giá + 0.20·mật độ video + 0.15·hoa hồng + 0.10·sao).")
    st.stop()

if data["is_sample"]:
    st.warning("⚠️ Đang dùng **dữ liệu mẫu** (chưa cấu hình nguồn TikTok Shop). Cắm TikHub/Kalodata ở trang "
               "**Kết nối API** để chạy số liệu thật — toàn bộ giao diện và công thức giữ nguyên.")
usage_caption({"tikhub_requests": 0} if data["is_sample"] else {})

prods = data["products"]
wins = [p for p in prods if p.scores.get("win_score", 0) >= 70]
m = st.columns(4)
m[0].metric("Sản phẩm", len(prods))
m[1].metric("Đạt điểm Win (≥70)", len(wins))
m[2].metric("Bán/ngày cao nhất", fmt_num(max((p.sold_per_day for p in prods), default=0)))
m[3].metric("Hoa hồng cao nhất", f"{max((p.commission_rate for p in prods), default=0):.0%}")

render_product_table(prods, key="ph_table")
st.caption("🌱 'Ít video, còn chỗ' = sản phẩm bán tốt nhưng ít người làm video → cơ hội cho người mới.")

st.markdown("#### Làm nội dung cho sản phẩm")
pick = st.selectbox("Chọn sản phẩm", [p.product_id for p in prods],
                    format_func=lambda i: next(p.title for p in prods if p.product_id == i))
chosen = next(p for p in prods if p.product_id == pick)
a, b = st.columns(2)
if a.button("✍️ Viết kịch bản bán hàng", type="primary"):
    st.session_state["sales_product"] = chosen.title
    st.switch_page("pages/niche/sales_script.py")
with b:
    download_excel({"Products": products_frame(prods)}, f"san_pham_{data['region']}.xlsx")
