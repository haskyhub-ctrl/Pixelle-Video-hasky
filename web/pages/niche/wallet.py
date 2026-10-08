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

"""Ví / chi phí API — local usage & cost tracking (self-hosted, no payment)."""

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[3]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import pandas as pd
import streamlit as st

from web.components.niche_ui import get_service, page_header

page_header("Tài khoản", "Chi phí API", "Bản self-hosted: bạn trả thẳng cho nhà cung cấp API. "
            "Trang này theo dõi lượng dùng & chi phí ước tính hôm nay, không có thanh toán.")

svc = get_service()
usage = svc.storage.usage_today()
yt = usage.get("youtube", {})
th = usage.get("tikhub", {})
m = st.columns(3)
m[0].metric("YouTube units hôm nay", f"{int(yt.get('units') or 0):,} / 10,000",
            help="Quota miễn phí mặc định 10.000 units/ngày")
m[1].metric("TikHub request hôm nay", int(th.get("requests") or 0))
m[2].metric("Chi phí TikHub hôm nay", f"{(th.get('cost_usd') or 0) * svc.cfg.usd_to_vnd:,.0f}đ")
if usage:
    st.markdown("#### Chi tiết hôm nay")
    st.dataframe(pd.DataFrame(usage.values()), hide_index=True, width="stretch")
else:
    st.info("Chưa có lượt dùng API nào hôm nay.")
st.caption("YouTube: 10.000 units/ngày miễn phí (~60 lần đào ngách). TikHub: trả theo request. "
           "LLM: theo token của nhà cung cấp bạn dùng.")
