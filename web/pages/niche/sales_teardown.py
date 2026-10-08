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

"""Mổ băng video bán hàng — teardown a selling TikTok video into a reusable framework."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from pixelle_video.services.niche import ai
from pixelle_video.services.niche.models import VideoItem
from web.components.niche_ui import chips, get_service, page_header, require_llm, run

page_header("TikTok Affiliate", "Mổ băng video bán hàng",
            "Dán nội dung một video gắn giỏ đang ra đơn → AI học công thức (hook, demo, xử lý phản đối, kêu gọi "
            "bấm giỏ) rồi đề xuất 3 bản làm lại.")

svc = get_service()
if not require_llm():
    st.stop()

with st.form("std_form"):
    caption = st.text_area("Lời thoại / caption của video bán hàng", height=160,
                           placeholder="Dán nội dung video đối thủ đang ra đơn...")
    c1, c2, c3 = st.columns(3)
    views = c1.number_input("Views", 0, step=1000, value=0)
    likes = c2.number_input("Likes", 0, step=100, value=0)
    duration = c3.number_input("Thời lượng (giây)", 0, 600, 45)
    submitted = st.form_submit_button("🔬 Mổ băng", type="primary")

if submitted and caption.strip():
    v = VideoItem(platform="tiktok", video_id="manual", title=caption.strip()[:120],
                  description=caption.strip(), views=int(views), likes=int(likes), duration_sec=int(duration))
    v.scores = {"outlier": 0}
    st.session_state.std = run(ai.video_teardown(svc.llm, v, [], "vi"), "AI đang mổ băng video bán hàng...")

t = st.session_state.get("std")
if not t:
    st.stop()
st.info(f"**🧩 Khung thắng:** {t.framework}")
c1, c2 = st.columns(2)
with c1.container(border=True):
    st.markdown(f"**🎣 Hook:** {t.hook_breakdown}")
    st.markdown("**🏗️ Cấu trúc**\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(t.structure, 1)))
with c2.container(border=True):
    st.markdown("**🧠 Đòn tâm lý**\n" + "\n".join(f"- {s}" for s in t.psychology))
    if t.audience:
        st.markdown(f"**👥 Khán giả:** {t.audience}")
st.markdown("#### 🔁 3 bản làm lại")
for i, r in enumerate(t.remakes):
    with st.container(border=True):
        a, b = st.columns([6, 1.3])
        a.markdown(f"**{r.title}**  \n🎣 _{r.hook}_  \n{r.angle}")
        chips([r.format])
        if b.button("✍️ Viết kịch bản", key=f"std_{i}"):
            st.session_state["sales_product"] = r.title
            st.switch_page("pages/niche/sales_script.py")
