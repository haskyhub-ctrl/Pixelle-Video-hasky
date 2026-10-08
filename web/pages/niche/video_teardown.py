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

"""Mổ băng đối thủ — teardown a winning video into a reusable framework + 3 remakes."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_ui import (
    chips,
    fmt_num,
    get_service,
    page_header,
    require_llm,
    require_youtube,
    run,
    send_to_studio,
    usage_caption,
)

page_header("Nghiên cứu", "Mổ băng đối thủ",
            "Dán link một video đang thắng → AI mổ xẻ cái KHUNG (hook, cấu trúc, đòn tâm lý) rồi đề xuất "
            "3 bản làm lại khác biệt, đúng chính sách.")

if not (require_youtube() and require_llm()):
    st.stop()
svc = get_service()

with st.form("teardown"):
    ref = st.text_input("Link video YouTube", placeholder="https://www.youtube.com/watch?v=...")
    submitted = st.form_submit_button("🔬 Mổ băng", type="primary")

if submitted and ref.strip():
    st.session_state.teardown = run(svc.teardown(ref.strip()), "Đang tải video và mổ băng bằng AI...")

data = st.session_state.get("teardown")
if not data:
    st.stop()
usage_caption(data.get("usage", {}))
v = data["video"]
c1, c2 = st.columns([1, 3])
if v.thumbnail:
    c1.image(v.thumbnail, width="stretch")
c2.markdown(f"### [{v.title}]({v.url})\n{fmt_num(v.views)} views · outlier **{v.scores.get('outlier', 0):.1f}×** · "
            f"{v.duration_sec // 60}:{v.duration_sec % 60:02d} · {v.channel_title}")

t = data["teardown"]
if not t:
    st.stop()
st.info(f"**🧩 Khung thắng:** {t.framework}")
c1, c2 = st.columns(2)
with c1.container(border=True):
    st.markdown(f"**🎣 Hook (3 giây đầu)**\n\n{t.hook_breakdown}")
    st.markdown("**🏗️ Cấu trúc**\n" + "\n".join(f"{i}. {s}" for i, s in enumerate(t.structure, 1)))
with c2.container(border=True):
    st.markdown("**🧠 Đòn tâm lý**\n" + "\n".join(f"- {s}" for s in t.psychology))
    if t.audience:
        st.markdown(f"**👥 Khán giả:** {t.audience}")

st.markdown("#### 🔁 3 bản làm lại khác biệt")
for i, r in enumerate(t.remakes):
    with st.container(border=True):
        a, b = st.columns([6, 1.3])
        a.markdown(f"**{r.title}**  \n🎣 _{r.hook}_  \n{r.angle}")
        chips([r.format] + ([f"dựa trên: {r.based_on[:50]}"] if r.based_on else []))
        if b.button("✍️ Viết kịch bản", key=f"td_{i}"):
            send_to_studio(r.title, r.hook, f"Mổ băng: {v.title} ({v.url})")
