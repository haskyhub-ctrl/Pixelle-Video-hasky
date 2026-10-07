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

"""Tối ưu video (SEO) — audit and rewrite title/description/tags."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_ui import cfg, get_service, page_header, require_llm, run, usage_caption

page_header("Tối ưu kênh", "Tối ưu video (SEO)",
            "Chấm điểm SEO tiêu đề, mô tả, tags theo 10 tiêu chí, rồi để AI viết lại dựa trên tiêu đề top đối thủ.")

svc = get_service()
mode = st.segmented_control("Nguồn", ["link", "manual"], default="link",
                            format_func={"link": "🔗 Từ link YouTube", "manual": "✏️ Nhập tay"}.get) or "link"

with st.form("seo_form"):
    video_ref = title = description = ""
    tags: list[str] = []
    if mode == "link":
        video_ref = st.text_input("Link video", placeholder="https://www.youtube.com/watch?v=...")
        if not cfg().youtube_api_key:
            st.caption("⚠️ Cần YouTube API key để đọc video từ link — hoặc chọn Nhập tay.")
    else:
        title = st.text_input("Tiêu đề")
        description = st.text_area("Mô tả", height=160)
        tags = [t.strip() for t in st.text_input("Tags (cách nhau bằng dấu phẩy)").split(",") if t.strip()]
    keyword = st.text_input("Từ khoá chính", placeholder="vd: phim tổng tài")
    use_ai = st.checkbox("AI viết lại", value=True)
    submitted = st.form_submit_button("🔍 Chấm điểm & tối ưu", type="primary")

if submitted:
    if use_ai:
        use_ai = require_llm()
    st.session_state.seo = run(svc.seo(video_ref.strip(), title, description, tags, keyword.strip(), use_ai),
                               "Đang phân tích SEO...")

data = st.session_state.get("seo")
if not data:
    st.stop()
usage_caption(data.get("usage", {}))
if data["video"]:
    v = data["video"]
    st.markdown(f"**[{v.title}]({v.url})** · {v.views:,} views")

audit = data["audit"]
s = audit["seo_score"]
st.markdown(f"### {'🟢' if s >= 75 else '🟡' if s >= 50 else '🔴'} Điểm SEO: {s}/100")
st.progress(s / 100)
for c in audit["checks"]:
    st.markdown(f"{'✅' if c['passed'] else '❌'} {c['check']} <small>(+{c['weight']})</small>", unsafe_allow_html=True)

sug = data.get("suggestion")
if sug:
    st.markdown("#### ✨ Đề xuất từ AI")
    st.markdown("**Tiêu đề**")
    for t in sug.titles:
        st.code(t, language=None)
        st.caption(f"{len(t)} ký tự")
    st.markdown("**Mô tả**")
    st.code(sug.description, language=None)
    c1, c2 = st.columns(2)
    c1.markdown("**Tags**")
    c1.code(", ".join(sug.tags), language=None)
    c2.markdown("**Hashtag & chữ trên thumbnail**")
    c2.code(" ".join(sug.hashtags) + "\n\n" + "\n".join(sug.thumbnail_text), language=None)

if data["competitor_titles"]:
    with st.expander("Tiêu đề top đối thủ cùng từ khoá"):
        st.markdown("\n".join(f"- {t}" for t in data["competitor_titles"]))
