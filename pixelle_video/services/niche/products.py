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
TikTok Shop / affiliate product data sources.

Real sources (TikHub, Kalodata, EchoTik) are plugged in via adapters; until a
key is configured the service falls back to clearly-labelled SAMPLE data so the
whole affiliate UI is usable end to end. Swap `provider` for a real one later.
"""

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from loguru import logger

from pixelle_video.services.niche.models import ProductItem
from pixelle_video.services.niche.sources import _counts, iter_posts

AFFILIATE_REGIONS = {
    "VN": "Việt Nam", "TH": "Thái Lan", "ID": "Indonesia", "MY": "Malaysia",
    "PH": "Philippines", "SG": "Singapore", "JP": "Nhật Bản", "MX": "Mexico",
}
CURRENCY = {"VN": "VND", "TH": "THB", "ID": "IDR", "MY": "MYR", "PH": "PHP",
            "SG": "SGD", "JP": "JPY", "MX": "MXN"}

# Default TikHub TikTok-Shop endpoints (overridable via niche.tikhub_endpoints).
# Keys are prefixed "shop_" so they don't collide with the video-search ones.
TIKHUB_SHOP_ENDPOINTS = {
    "shop_search": ("/api/v1/tiktok/app/v3/fetch_product_search", "keyword"),
    "shop_hot": ("/api/v1/tiktok/app/v3/fetch_hot_products", "keyword"),
}

PROD_ID = ("product_id", "id", "pid")
PROD_TITLE = ("title", "product_name", "name", "desc")
PROD_SOLD = ("sold_count", "sale_cnt", "sales", "sold", "order_count", "sold_total")
PROD_PRICE = ("price", "min_price", "sale_price")
PROD_RATING = ("rating", "review_rating", "avg_rating", "star")
PROD_REVIEWS = ("review_count", "reviews", "comment_count")
PROD_COMM = ("commission_rate", "commission", "commission_ratio")


def _f(d: dict, keys, default=0.0) -> float:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            try:
                return float(str(d[k]).replace(",", "").replace("%", ""))
            except ValueError:
                pass
    return default


class ProductProvider:
    """Base interface. `available` tells the UI whether it's real or sample."""

    name = "base"
    available = False

    async def search(self, keyword: str, region: str = "VN", limit: int = 40) -> list[ProductItem]:
        raise NotImplementedError

    async def trending(self, region: str = "VN", limit: int = 40) -> list[ProductItem]:
        return await self.search("", region, limit)


class TikHubProductProvider(ProductProvider):
    name = "tikhub"
    BASE = "https://api.tikhub.io"

    def __init__(self, api_key: str, endpoints: Optional[dict] = None, timeout: float = 30.0):
        self.api_key = api_key
        self.available = bool(api_key)
        self.endpoints = dict(TIKHUB_SHOP_ENDPOINTS)
        for k, v in (endpoints or {}).items():
            if k.startswith("shop_"):
                self.endpoints[k] = tuple(v) if isinstance(v, (list, tuple)) else (v, "keyword")
        self.timeout = timeout
        self.requests = 0

    async def _call(self, which: str, keyword: str, region: str, limit: int) -> list[ProductItem]:
        path, param = self.endpoints[which]
        params = {param: keyword or "hot", "region": region, "count": min(limit, 50)}
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            r = await c.get(self.BASE + path, params=params,
                            headers={"Authorization": f"Bearer {self.api_key}"})
        self.requests += 1
        if r.status_code != 200:
            raise RuntimeError(f"TikHub shop {r.status_code}: {r.text[:200]}")
        return self._parse(r.json(), region)

    async def search(self, keyword: str, region: str = "VN", limit: int = 40) -> list[ProductItem]:
        return await self._call("shop_search", keyword, region, limit)

    async def trending(self, region: str = "VN", limit: int = 40) -> list[ProductItem]:
        try:
            return await self._call("shop_hot", "", region, limit)
        except Exception:
            return await self._call("shop_search", "hot", region, limit)

    @staticmethod
    def _parse(payload, region: str) -> list[ProductItem]:
        out, seen = [], set()
        for node in iter_posts(payload):
            pid = None
            for k in PROD_ID:
                if node.get(k):
                    pid = str(node[k])
                    break
            if not pid or pid in seen:
                continue
            title = next((str(node[k]) for k in PROD_TITLE if node.get(k)), "")
            if not title:
                continue
            seen.add(pid)
            comm = _f(node, PROD_COMM)
            out.append(ProductItem(
                product_id=pid, title=title[:300], region=region, currency=CURRENCY.get(region, ""),
                price=_f(node, PROD_PRICE), rating=_f(node, PROD_RATING),
                reviews=int(_f(node, PROD_REVIEWS)), sold_total=int(_f(node, PROD_SOLD)),
                commission_rate=comm / 100 if comm > 1 else comm,
                videos_with_cart=_counts(node, ("video_count", "related_videos")),
                url=str(node.get("product_url") or node.get("url") or ""),
                image=str(node.get("cover") or node.get("image") or ""),
                shop_name=str(node.get("shop_name") or node.get("seller_name") or ""),
            ))
        return out


class SampleProductProvider(ProductProvider):
    """Deterministic fake data so the affiliate UI is fully demoable offline."""

    name = "sample"
    available = True

    CATALOG = {
        "VN": ["Máy massage cổ mini", "Serum dưỡng ẩm B5", "Bàn phím cơ không dây", "Đèn ngủ cảm ứng",
               "Tai nghe gaming RGB", "Bình giữ nhiệt 1L", "Giá đỡ điện thoại nam châm", "Máy xay cầm tay",
               "Gối cao su non", "Dép massage chân", "Son kem lì", "Máy hút bụi mini ô tô"],
    }

    async def search(self, keyword: str, region: str = "VN", limit: int = 40) -> list[ProductItem]:
        names = self.CATALOG.get(region, self.CATALOG["VN"])
        if keyword:
            names = [f"{keyword} — {n}" for n in names]
        out = []
        now = datetime.now(timezone.utc)
        for i, name in enumerate(names[:limit]):
            seed = int(hashlib.md5(f"{region}{name}".encode()).hexdigest(), 16)
            rnd = random.Random(seed)
            spd = rnd.choice([20, 55, 90, 140, 220, 380, 610])
            age = rnd.randint(15, 400)
            out.append(ProductItem(
                product_id=f"sample_{region}_{i}", title=name, region=region,
                currency=CURRENCY.get(region, "VND"), price=rnd.randint(49, 890) * 1000,
                rating=round(rnd.uniform(4.1, 4.95), 1), reviews=rnd.randint(30, 5200),
                sold_total=spd * age, sold_per_day=spd, revenue_total=spd * age * rnd.randint(49, 300) * 1000,
                commission_rate=round(rnd.uniform(0.08, 0.28), 2),
                videos_with_cart=rnd.randint(3, 180), influencers=rnd.randint(2, 90),
                published_at=now - timedelta(days=age),
                shop_name=rnd.choice(["Official Store", "Shop Chính Hãng", "TikTok Shop Mall"]),
                image="", url="",
            ))
        return out


def get_provider(tikhub_key: str = "", endpoints: Optional[dict] = None) -> ProductProvider:
    if tikhub_key:
        return TikHubProductProvider(tikhub_key, endpoints)
    logger.info("No TikTok Shop source configured — using SAMPLE products")
    return SampleProductProvider()


def fill_derived(products: list[ProductItem], now: Optional[datetime] = None) -> list[ProductItem]:
    """Compute sold_per_day from totals when the source only gives lifetime sales."""
    now = now or datetime.now(timezone.utc)
    for p in products:
        if not p.sold_per_day and p.sold_total and p.published_at:
            days = max((now - p.published_at).days, 1)
            p.sold_per_day = p.sold_total / days
    return products
