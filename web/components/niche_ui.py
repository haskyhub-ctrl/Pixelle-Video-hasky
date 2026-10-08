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
Shared UI building blocks for the niche research pages.
"""

from typing import Callable, Optional, Sequence

import pandas as pd
import streamlit as st

from pixelle_video.config import config_manager
from pixelle_video.services.niche import NicheService, VideoItem
from pixelle_video.services.niche.sources import PLATFORMS
from web.utils.async_helpers import run_async

PERIODS = {"24h": "24h", "7d": "7 ngày", "30d": "30 ngày", "90d": "90 ngày", "1y": "1 năm", "all": "Mọi lúc"}
DURATIONS = {"any": "Mọi độ dài", "short": "Shorts (≤3 phút)", "long": "Video dài"}
ORDERS = {"relevance": "Liên quan", "viewCount": "Nhiều view", "date": "Mới nhất"}
REGIONS = {
    "VN": "Việt Nam", "US": "Mỹ", "GB": "Anh", "IN": "Ấn Độ", "ID": "Indonesia", "TH": "Thái Lan",
    "PH": "Philippines", "JP": "Nhật Bản", "KR": "Hàn Quốc", "TW": "Đài Loan", "BR": "Brazil",
    "MX": "Mexico", "DE": "Đức", "FR": "Pháp", "ES": "Tây Ban Nha",
}
REGION_LANG = {"VN": "vi", "US": "en", "GB": "en", "IN": "hi", "ID": "id", "TH": "th", "PH": "en",
               "JP": "ja", "KR": "ko", "TW": "zh-Hant", "BR": "pt", "MX": "es", "DE": "de", "FR": "fr", "ES": "es"}
NICHES = {
    "general": "Chung", "finance": "Tài chính", "business": "Kinh doanh", "tech": "Công nghệ",
    "education": "Giáo dục", "health": "Sức khoẻ", "real_estate": "Bất động sản", "gaming": "Game",
    "entertainment": "Giải trí", "film": "Phim / review phim", "music": "Âm nhạc", "kids": "Trẻ em",
    "vlog": "Vlog", "food": "Ẩm thực", "beauty": "Làm đẹp", "news": "Tin tức", "sport": "Thể thao",
}

_CSS = """
<style>
.niche-kicker{color:#d4a24c;font-size:.78rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase;margin-bottom:.1rem}
.niche-title{font-size:1.9rem;font-weight:800;margin:0 0 .2rem 0}
.niche-desc{opacity:.75;margin-bottom:1rem;max-width:820px}
.niche-chip{display:inline-block;padding:2px 10px;border-radius:999px;border:1px solid rgba(212,162,76,.5);
 margin:2px 4px 2px 0;font-size:.8rem}
</style>
"""


def page_header(kicker: str, title: str, desc: str = "") -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(f'<div class="niche-kicker">{kicker}</div><div class="niche-title">{title}</div>'
                f'<div class="niche-desc">{desc}</div>', unsafe_allow_html=True)


def chips(items: Sequence[str]) -> None:
    if items:
        st.markdown("".join(f'<span class="niche-chip">{i}</span>' for i in items), unsafe_allow_html=True)


def get_service() -> NicheService:
    if "niche_service" not in st.session_state:
        st.session_state.niche_service = NicheService()
    return st.session_state.niche_service


def cfg():
    return config_manager.config.niche


def run(coro, spinner: str = "Đang xử lý..."):
    """Run a coroutine with a spinner and show errors instead of crashing the page."""
    with st.spinner(spinner):
        try:
            return run_async(coro)
        except Exception as e:
            st.error(f"❌ {e}")
            return None


def render_api_settings(expanded: bool = False) -> None:
    c = cfg()
    with st.expander("⚙️ Cài đặt API nghiên cứu", expanded=expanded):
        with st.form("niche_settings"):
            yt = st.text_input("YouTube Data API v3 key", value=c.youtube_api_key, type="password",
                               help="Google Cloud Console → APIs & Services → bật YouTube Data API v3 → "
                                    "Credentials → API key. Miễn phí 10.000 units/ngày.")
            th = st.text_input("TikHub API key (TikTok, Douyin, Xiaohongshu, Kuaishou...)",
                               value=c.tikhub_api_key, type="password", help="https://tikhub.io")
            col1, col2, col3, col4 = st.columns(4)
            region = col1.selectbox("Quốc gia mặc định", list(REGIONS), format_func=REGIONS.get,
                                    index=list(REGIONS).index(c.default_region) if c.default_region in REGIONS else 0)
            avd = col2.number_input("AVD giả định (%)", 5, 100, int(c.avd_ratio * 100),
                                    help="Tỷ lệ thời lượng xem trung bình, dùng để ước tính giờ xem")
            cost = col3.number_input("Giá TikHub / request (USD)", 0.0, 1.0, float(c.tikhub_cost_per_request_usd),
                                     step=0.0005, format="%.4f")
            fx = col4.number_input("Tỷ giá USD→VND", 1000, 100000, int(c.usd_to_vnd), step=500)
            if st.form_submit_button("💾 Lưu cài đặt", type="primary"):
                config_manager.update({"niche": {
                    "youtube_api_key": yt.strip(), "tikhub_api_key": th.strip(), "default_region": region,
                    "default_language": REGION_LANG.get(region, "en"), "avd_ratio": avd / 100,
                    "tikhub_cost_per_request_usd": cost, "usd_to_vnd": fx,
                }})
                config_manager.save()
                st.success("Đã lưu vào config.yaml")
                st.rerun()


def require_youtube() -> bool:
    if cfg().youtube_api_key:
        return True
    st.warning("Chức năng này cần **YouTube Data API key**. Nhập key ở mục cài đặt bên dưới.")
    render_api_settings(expanded=True)
    return False


def require_llm() -> bool:
    if config_manager.config.is_llm_configured():
        return True
    st.info("💡 Phần phân tích AI cần cấu hình LLM ở trang **Tạo video → Cài đặt nâng cao**.")
    return False


def fmt_num(n: float) -> str:
    n = float(n or 0)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= div:
            return f"{n / div:.1f}{suf}"
    return f"{n:.0f}"


def platform_label(p: str) -> str:
    return PLATFORMS.get(p, {}).get("label", p)


def videos_frame(videos: Sequence[VideoItem]) -> pd.DataFrame:
    return pd.DataFrame([{
        "thumb": v.thumbnail or None,
        "Điểm": v.scores.get("viral_score", 0),
        "Tiêu đề": v.title,
        "Nhãn": " ".join(v.labels),
        "Nền tảng": platform_label(v.platform),
        "Kênh": v.channel_title,
        "Views": v.views,
        "Sub kênh": v.channel_subscribers or None,
        "Outlier": v.scores.get("outlier"),
        "Views/Sub": v.scores.get("views_per_sub"),
        "Views/giờ": v.scores.get("vph"),
        "Tương tác": v.scores.get("engagement"),
        "Tuổi (ngày)": v.scores.get("age_days"),
        "Thời lượng": f"{v.duration_sec // 60}:{v.duration_sec % 60:02d}" if v.duration_sec else "",
        "Link": v.url or None,
    } for v in videos])


def render_video_table(videos: Sequence[VideoItem], key: str = "videos", height: int = 520) -> None:
    if not videos:
        st.info("Không có video nào.")
        return
    st.dataframe(
        videos_frame(videos),
        key=key,
        height=height,
        hide_index=True,
        width="stretch",
        column_config={
            "thumb": st.column_config.ImageColumn("", width="small"),
            "Điểm": st.column_config.ProgressColumn("Điểm vượt trội", min_value=0, max_value=100, format="%.0f"),
            "Tiêu đề": st.column_config.TextColumn(width="large"),
            "Views": st.column_config.NumberColumn(format="compact"),
            "Sub kênh": st.column_config.NumberColumn(format="compact"),
            "Outlier": st.column_config.NumberColumn(format="%.1fx", help="Views / view trung vị của kênh"),
            "Views/Sub": st.column_config.NumberColumn(format="%.2f"),
            "Views/giờ": st.column_config.NumberColumn(format="compact"),
            "Tương tác": st.column_config.NumberColumn(format="percent"),
            "Link": st.column_config.LinkColumn("Mở", display_text="▶"),
        },
    )


def render_video_cards(videos: Sequence[VideoItem], cols: int = 4, limit: int = 8,
                       action: Optional[tuple[str, Callable[[VideoItem], None]]] = None, key: str = "card") -> None:
    columns = st.columns(cols)
    for i, v in enumerate(videos[:limit]):
        with columns[i % cols].container(border=True):
            if v.thumbnail:
                st.image(v.thumbnail, width="stretch")
            st.markdown(f"**[{v.title[:90]}]({v.url})**" if v.url else f"**{v.title[:90]}**")
            st.caption(f"{platform_label(v.platform)} · {v.channel_title} · "
                       f"{fmt_num(v.views)} views · {fmt_num(v.channel_subscribers)} sub")
            s = v.scores
            st.markdown(f"🏆 **{s.get('viral_score', 0):.0f}** · outlier **{s.get('outlier', 0):.1f}x** · "
                        f"{fmt_num(s.get('vph', 0))}/giờ")
            chips(v.labels)
            if action:
                label, fn = action
                if st.button(label, key=f"{key}_{i}_{v.video_id}"):
                    fn(v)


def usage_caption(usage: dict) -> None:
    if not usage:
        return
    parts = []
    if usage.get("youtube_units"):
        parts.append(f"YouTube: {usage['youtube_units']} units / {usage.get('youtube_requests', 0)} request")
    if usage.get("tikhub_requests"):
        parts.append(f"TikHub: {usage['tikhub_requests']} request ≈ {usage.get('tikhub_cost_vnd', 0):,}đ")
    if parts:
        st.caption("Đã dùng — " + " · ".join(parts))


def download_excel(sheets: dict, filename: str, label: str = "⬇️ Xuất Excel", key: str = "xlsx") -> None:
    from pixelle_video.services.niche.export import to_excel
    try:
        data = to_excel(sheets)
    except Exception as e:
        st.caption(f"Không xuất được Excel: {e}")
        return
    st.download_button(label, data, file_name=filename, key=key,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def send_to_studio(topic: str, hook: str = "", reference: str = "") -> None:
    st.session_state["studio_topic"] = topic
    st.session_state["studio_hook"] = hook
    st.session_state["studio_reference"] = reference
    st.switch_page("pages/niche/script_studio.py")


def send_to_video_generator(text: str, title: str = "", fixed: bool = True) -> None:
    st.session_state["niche_prefill_text"] = text
    st.session_state["niche_prefill_title"] = title
    st.session_state["niche_prefill_mode"] = "fixed" if fixed else "generate"
    st.switch_page("pages/1_🎬_Home.py")


AFFILIATE_REGIONS = {"VN": "Việt Nam", "TH": "Thái Lan", "ID": "Indonesia", "MY": "Malaysia",
                     "PH": "Philippines", "SG": "Singapore", "JP": "Nhật Bản", "MX": "Mexico"}


def products_frame(products):
    import pandas as pd
    return pd.DataFrame([{
        "Ảnh": p.image or None,
        "Win": p.scores.get("win_score", 0),
        "Sản phẩm": p.title,
        "Nhãn": " ".join(p.labels),
        "Bán/ngày": p.sold_per_day,
        "Đã bán": p.sold_total,
        "Đánh giá": p.rating or None,
        "Lượt đánh giá": p.reviews or None,
        "Hoa hồng": p.commission_rate or None,
        "Giá": p.price or None,
        "Video gắn giỏ": p.videos_with_cart or None,
        "Shop": p.shop_name,
        "Link": p.url or None,
    } for p in products])


def render_product_table(products, key="products", height=520):
    import streamlit as st
    if not products:
        st.info("Không có sản phẩm nào.")
        return
    st.dataframe(products_frame(products), key=key, height=height, hide_index=True, width="stretch",
                 column_config={
                     "Ảnh": st.column_config.ImageColumn("", width="small"),
                     "Win": st.column_config.ProgressColumn("Điểm Win", min_value=0, max_value=100, format="%.0f"),
                     "Sản phẩm": st.column_config.TextColumn(width="large"),
                     "Bán/ngày": st.column_config.NumberColumn(format="%.0f"),
                     "Đã bán": st.column_config.NumberColumn(format="compact"),
                     "Đánh giá": st.column_config.NumberColumn(format="%.1f ⭐"),
                     "Lượt đánh giá": st.column_config.NumberColumn(format="compact"),
                     "Hoa hồng": st.column_config.NumberColumn(format="percent"),
                     "Giá": st.column_config.NumberColumn(format="compact"),
                     "Link": st.column_config.LinkColumn("Mở", display_text="🛒"),
                 })


def render_heatmap(hm, key="heatmap"):
    """7×24 posting heatmap of view-vs-typical ratio (Altair, no matplotlib dep)."""
    import altair as alt
    import pandas as pd
    import streamlit as st
    if not hm or not hm.get("n"):
        st.caption("Chưa đủ dữ liệu để vẽ giờ vàng.")
        return
    weekdays = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    rows = [{"Thứ": weekdays[wd], "wd": wd, "Giờ": hr, "ratio": hm["grid"][wd][hr],
             "n": hm["counts"][wd][hr]}
            for wd in range(7) for hr in range(24)]
    df = pd.DataFrame(rows)
    chart = (
        alt.Chart(df).mark_rect().encode(
            x=alt.X("Giờ:O", title="Giờ (GMT+7)"),
            y=alt.Y("Thứ:O", sort=weekdays, title=None),
            color=alt.Color("ratio:Q", scale=alt.Scale(scheme="yelloworangered"),
                            legend=alt.Legend(title="× trung vị")),
            tooltip=["Thứ", "Giờ", alt.Tooltip("ratio:Q", title="× trung vị", format=".1f"),
                     alt.Tooltip("n:Q", title="Số video")],
        ).properties(height=240)
    )
    st.altair_chart(chart, width="stretch", key=key)
    if hm.get("best"):
        from pixelle_video.services.niche.service import WEEKDAYS_VI
        slots = " · ".join(f"{WEEKDAYS_VI[s['weekday']]} {s['hour']:02d}:00" for s in hm["best"])
        st.markdown(f"🕒 **Giờ vàng:** {slots}")
    st.caption(f"Màu đậm = view cao hơn mức chung (dựa trên {hm['n']} video). Số là bội số so với trung vị.")
