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

"""Excel / CSV export of scored videos."""

import io
from datetime import datetime
from typing import Sequence

import pandas as pd

from pixelle_video.services.niche.models import VideoItem

COLUMNS = {
    "platform": "Nền tảng", "title": "Tiêu đề", "channel_title": "Kênh", "url": "Link",
    "published_at": "Ngày đăng", "views": "Views", "likes": "Likes", "comments": "Bình luận",
    "channel_subscribers": "Sub kênh", "duration_sec": "Thời lượng (s)",
}
SCORE_COLUMNS = {
    "viral_score": "Điểm vượt trội", "outlier": "Outlier (x)", "views_per_sub": "Views/Sub",
    "vph": "Views/giờ", "engagement": "Tương tác", "age_days": "Tuổi (ngày)",
}


def videos_to_frame(videos: Sequence[VideoItem]) -> pd.DataFrame:
    rows = []
    for v in videos:
        row = {label: getattr(v, key) for key, label in COLUMNS.items()}
        if row["Ngày đăng"] is not None:
            row["Ngày đăng"] = row["Ngày đăng"].strftime("%Y-%m-%d %H:%M")
        row.update({label: v.scores.get(key) for key, label in SCORE_COLUMNS.items()})
        row["Nhãn"] = ", ".join(v.labels)
        rows.append(row)
    return pd.DataFrame(rows)


def _cell(value):
    if isinstance(value, (list, tuple, set)):
        return ", ".join(str(_cell(v)) for v in value)
    if isinstance(value, dict):
        return "; ".join(f"{k}: {_cell(v)}" for k, v in value.items())
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if hasattr(value, "model_dump"):
        return getattr(value, "title", None) or str(value.model_dump())
    return value


def to_excel(sheets: dict[str, "pd.DataFrame | Sequence[VideoItem] | list[dict]"]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, data in sheets.items():
            if isinstance(data, pd.DataFrame):
                df = data
            elif data and isinstance(data[0], VideoItem):
                df = videos_to_frame(data)
            else:
                df = pd.DataFrame(list(data))
            # openpyxl cannot write lists/dicts/models or tz-aware datetimes
            df = df.apply(lambda col: col.map(_cell))
            df.to_excel(writer, sheet_name=name[:31], index=False)
    return buf.getvalue()
