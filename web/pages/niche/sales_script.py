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

"""Kịch bản video bán hàng — short-form affiliate sales scripts."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_ui import (
    get_service,
    page_header,
    require_llm,
    run,
    send_to_video_generator,
)

page_header("TikTok Affiliate", "Kịch bản video bán hàng",
            "Viết kịch bản video ngắn bán hàng: hook nỗi đau → demo → lợi ích → xử lý phản đối → ưu đãi → "
            "bấm giỏ hàng, kèm chữ overlay và hashtag.")

svc = get_service()
ss = st.session_state
if not require_llm():
    st.stop()

with st.form("sscript_form"):
    product = st.text_input("Sản phẩm", value=ss.get("sales_product", ""))
    c1, c2 = st.columns(2)
    pains = c1.text_area("Điểm đau khách hàng (tuỳ chọn)", height=80)
    benefits = c2.text_area("Lợi ích chính (tuỳ chọn)", height=80)
    duration = st.select_slider("Thời lượng", [15, 30, 45, 60, 90], value=45, format_func=lambda s: f"{s}s")
    submitted = st.form_submit_button("✍️ Viết kịch bản", type="primary")

if submitted and product.strip():
    ss.sales_product = product
    ss.sscript = run(svc.sales_script(product.strip(), pains, benefits, duration), "AI đang viết kịch bản bán hàng...")

sc = ss.get("sscript")
if not sc:
    st.stop()

st.markdown(f"### {sc.title}")
st.markdown(f"🎣 **Hook:** {sc.hook}")
text = st.text_area("Kịch bản", value=sc.script, height=320, key="sscript_text")
c1, c2 = st.columns(2)
if sc.on_screen_text:
    c1.markdown("**📱 Chữ overlay**\n" + "\n".join(f"- {t}" for t in sc.on_screen_text))
if sc.scene_visuals:
    c2.markdown("**🎬 Hình ảnh từng cảnh**\n" + "\n".join(f"- {v}" for v in sc.scene_visuals))
st.markdown(f"📣 **CTA:** {sc.cta}  \n" + " ".join(sc.hashtags))

a, b = st.columns(2)
if a.button("🎬 Tạo video từ kịch bản", type="primary", width="stretch"):
    send_to_video_generator(text, sc.title, fixed=True)
b.download_button("⬇️ Tải .txt", f"{sc.title}\n\n{sc.hook}\n\n{text}\n\n{sc.cta}\n{' '.join(sc.hashtags)}",
                  file_name="kich_ban_ban_hang.txt", width="stretch")
