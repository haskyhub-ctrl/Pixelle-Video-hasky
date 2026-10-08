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
Normalized data models shared by every niche-research source and feature.

Every platform adapter converts its raw payload into VideoItem / ChannelItem
so scoring, filtering and export never need to know where data came from.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ChannelItem(BaseModel):
    platform: str = "youtube"
    channel_id: str
    title: str = ""
    handle: str = ""
    description: str = ""
    country: str = ""
    published_at: Optional[datetime] = None
    subscribers: int = 0
    total_views: int = 0
    video_count: int = 0
    thumbnail: str = ""
    uploads_playlist: str = ""
    url: str = ""

    def age_days(self, now: Optional[datetime] = None) -> float:
        if not self.published_at:
            return 0.0
        now = now or datetime.now(timezone.utc)
        return max((now - self.published_at).total_seconds() / 86400, 0.0)


class VideoItem(BaseModel):
    platform: str = "youtube"
    video_id: str
    title: str = ""
    description: str = ""
    url: str = ""
    thumbnail: str = ""
    channel_id: str = ""
    channel_title: str = ""
    published_at: Optional[datetime] = None
    duration_sec: int = 0
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    tags: list[str] = Field(default_factory=list)
    language: str = ""
    category_id: str = ""
    made_for_kids: bool = False
    age_restricted: bool = False

    # Filled by enrichment (channel lookup) — 0 means unknown
    channel_subscribers: int = 0
    channel_median_views: float = 0.0

    # Filled by scoring
    scores: dict[str, float] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)

    def age_hours(self, now: Optional[datetime] = None) -> float:
        if not self.published_at:
            return 0.0
        now = now or datetime.now(timezone.utc)
        return max((now - self.published_at).total_seconds() / 3600, 0.0)

    @property
    def is_short(self) -> bool:
        # YouTube Shorts can be up to 3 minutes since Oct 2024
        return 0 < self.duration_sec <= 180


class SearchFilters(BaseModel):
    """Filters shared by the niche search UI, API and service."""

    query: str
    platforms: list[str] = Field(default_factory=lambda: ["youtube"])
    period: str = "30d"  # 24h | 7d | 30d | 1y | all
    duration: str = "any"  # any | short | long
    order: str = "relevance"  # relevance | viewCount | date
    region: str = "VN"
    language: str = "vi"
    max_results: int = 50
    max_per_channel: int = 3
    hide_adult: bool = True
    strict_topic: bool = True


class ProductItem(BaseModel):
    """A TikTok Shop / affiliate product (normalized across data sources)."""
    platform: str = "tiktok_shop"
    product_id: str
    title: str = ""
    url: str = ""
    image: str = ""
    shop_name: str = ""
    category: str = ""
    region: str = "VN"
    price: float = 0.0
    currency: str = "VND"
    commission_rate: float = 0.0  # 0..1
    rating: float = 0.0
    reviews: int = 0
    sold_total: int = 0
    sold_per_day: float = 0.0
    revenue_total: float = 0.0
    videos_with_cart: int = 0
    influencers: int = 0
    published_at: Optional[datetime] = None
    scores: dict[str, float] = Field(default_factory=dict)
    labels: list[str] = Field(default_factory=list)
