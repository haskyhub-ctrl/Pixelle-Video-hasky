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

"""
Pixelle-Video Web UI - Main Entry Point

This is the entry point for the Streamlit multi-page application.
Uses st.navigation to define pages and set the default page to Home.
"""

import sys
from pathlib import Path

# Add project root to sys.path for module imports
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

# Setup page config (must be first Streamlit command)
st.set_page_config(
    page_title="Pixelle-Video - AI Video Generator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main():
    """Main entry point with navigation"""
    # Define pages using st.Page
    home_page = st.Page(
        "pages/1_🎬_Home.py",
        title="Home",
        icon="🎬",
        default=True
    )
    
    history_page = st.Page(
        "pages/2_📚_History.py",
        title="History",
        icon="📚"
    )
    
    def niche(file: str, title: str, icon: str) -> st.Page:
        return st.Page(f"pages/niche/{file}", title=title, icon=icon)

    # Set up navigation (sidebar groups) and run
    pg = st.navigation({
        "Tạo video": [home_page, history_page],
        "Tổng quan": [
            niche("overview.py", "Tổng quan", "🏠"),
            niche("monetization.py", "Kiểm tra kiếm tiền", "💰"),
        ],
        "Nghiên cứu": [
            niche("niche_finder.py", "Đào ngách", "⛏️"),
            niche("multi_market.py", "Đào đa thị trường", "🌏"),
            niche("channel_hunter.py", "Săn kênh nổ view", "🎯"),
            niche("channel_analysis.py", "Phân tích kênh", "📊"),
            niche("trends.py", "Xu hướng đa nền tảng", "📈"),
            niche("keyword_research.py", "Nghiên cứu từ khoá", "🔑"),
        ],
        "Sáng tạo": [
            niche("winning_topics.py", "Chủ đề thắng", "🏆"),
            niche("script_studio.py", "Studio kịch bản", "✍️"),
            niche("content_calendar.py", "Lịch đăng", "📅"),
        ],
        "Tối ưu kênh": [
            niche("my_channel.py", "Kênh của tôi", "📺"),
            niche("channel_doctor.py", "Bác sĩ kênh", "🩺"),
            niche("seo_optimizer.py", "Tối ưu video (SEO)", "🚀"),
        ],
        "Dữ liệu": [
            niche("data_center.py", "Ngách đã lưu & kênh", "🗂️"),
        ],
    })
    pg.run()


if __name__ == "__main__":
    main()
