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

"""Trung tâm TikTok Affiliate — hub + 5-step roadmap."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_ui import get_service, page_header

page_header("TikTok Affiliate", "Trung tâm TikTok Affiliate",
            "Cho người làm affiliate TikTok Shop bằng video ngắn. Làm theo lộ trình 5 bước — mỗi bước đưa dữ liệu "
            "sang bước sau.")

svc = get_service()
ov = svc.overview()
if not ov["tikhub_ready"]:
    st.warning("⚠️ Chưa cấu hình nguồn TikTok Shop (TikHub). Các trang affiliate vẫn chạy bằng **dữ liệu mẫu** "
               "để bạn xem trước. Cắm key ở trang **Kết nối API**.")

STEPS = [
    ("pages/niche/product_hunter.py", "1", "Săn sản phẩm win",
     "Tìm sản phẩm TikTok Shop bằng số liệu thật: số đã bán, tốc độ bán/ngày, điểm Win 0–100."),
    ("pages/niche/affiliate_channels.py", "2", "Kênh affiliate làm tốt",
     "Tìm kênh TikTok đang bán tốt trong ngách: video có gắn giỏ, xếp theo view thật."),
    ("pages/niche/tiktok_channel_analysis.py", "3", "Phân tích kênh TikTok",
     "Mổ xẻ kênh đang bán: video nào nổ, đăng giờ nào, bao nhiêu video/ngày."),
    ("pages/niche/sales_teardown.py", "4", "Mổ băng video bán hàng",
     "Học công thức video gắn giỏ ra đơn: hook, demo, xử lý phản đối, kêu gọi bấm giỏ."),
    ("pages/niche/sales_script.py", "5", "Kịch bản video bán hàng",
     "Viết kịch bản video ngắn bán hàng, kèm chữ overlay và hashtag."),
]
st.markdown("#### 🧭 Lộ trình 5 bước")
cols = st.columns(5)
for col, (page, num, title, desc) in zip(cols, STEPS):
    with col.container(border=True):
        st.markdown(f"**Bước {num}**")
        st.page_link(page, label=title)
        st.caption(desc)

st.markdown("#### 🧰 Công cụ khác")
c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.page_link("pages/niche/tiktok_trends.py", label="📈 Xu hướng TikTok")
    st.caption("Bắt sản phẩm/hashtag đang nóng để chọn đúng thời điểm.")
with c2.container(border=True):
    st.page_link("pages/niche/affiliate_calendar.py", label="📅 Lịch đăng video")
    st.caption("Lên lịch 2–3 video/ngày cho mỗi sản phẩm theo giờ vàng.")
with c3.container(border=True):
    st.page_link("pages/niche/connect_api.py", label="🔌 Kết nối API")
    st.caption("Cắm nguồn TikTok Shop thật (TikHub/Kalodata) và các key khác.")
