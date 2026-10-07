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

"""Phân tích kênh — channel analytics."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from web.components.niche_channel import render_channel_analysis
from web.components.niche_ui import get_service, page_header, require_youtube, run

page_header("Nghiên cứu", "Phân tích kênh",
            "Mổ xẻ một kênh bất kỳ: video vượt trội so với chính kênh, tần suất, khung giờ đăng, tỷ lệ hit/flop "
            "và chiến lược nội dung.")
if require_youtube():
    svc = get_service()
    with st.form("ca_form"):
        c1, c2 = st.columns([4, 1])
        ref = c1.text_input("Kênh", placeholder="@tenkenh, link kênh hoặc link video", label_visibility="collapsed")
        n = c2.selectbox("Số video", [30, 50, 100, 200], index=1, label_visibility="collapsed")
        if st.form_submit_button("🔍 Phân tích", type="primary") and ref.strip():
            st.session_state.ca_data = run(svc.channel_analysis(ref, n), "Đang tải video của kênh...")
            st.session_state.pop("ca_report", None)
    if st.session_state.get("ca_data"):
        render_channel_analysis(st.session_state.ca_data, "ca")
