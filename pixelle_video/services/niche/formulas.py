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
Scoring formulas for niche research.

All functions are pure (no I/O) so they can be unit tested and reused by the
web UI, the API and batch jobs. See docs/niche_research.md for the rationale
behind every constant.

Notation used below:
    V   views of a video            S   subscribers of its channel
    M   median views of the channel's recent uploads (excluding this video)
    t   video age in hours          L,C likes, comments
"""

import math
import statistics
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Sequence

from pixelle_video.services.niche.models import ChannelItem, VideoItem

# Floors avoid division blow-ups for brand-new channels / videos
MIN_SUBS = 100
MIN_HOURS = 1.0


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def logistic(x: float, center: float, scale: float) -> float:
    """Squash x to (0, 1); returns 0.5 at `center`, ~0.73 at center+scale."""
    z = (x - center) / scale
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-z))


def safe_log10(x: float, floor: float = 1e-9) -> float:
    return math.log10(max(x, floor))


def median(values: Iterable[float]) -> float:
    vals = [v for v in values if v is not None]
    return float(statistics.median(vals)) if vals else 0.0


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Video-level metrics
# ---------------------------------------------------------------------------

def outlier_ratio(views: float, channel_median: float, subscribers: float) -> float:
    """
    Outlier = V / M  — how many times better than the channel's usual video.

    If the channel median is unknown, fall back to V / max(S, 100) which is a
    weaker but always-available baseline.
    """
    if channel_median and channel_median > 0:
        return views / channel_median
    return views / max(subscribers, MIN_SUBS)


def views_per_sub(views: float, subscribers: float) -> float:
    """R = V / max(S, 100) — >1 means the video escaped the subscriber base."""
    return views / max(subscribers, MIN_SUBS)


def views_per_hour(views: float, age_hours: float) -> float:
    """VPH = V / max(t, 1)."""
    return views / max(age_hours, MIN_HOURS)


def momentum(views: float, age_hours: float, alpha: float = 0.7) -> float:
    """
    Age-adjusted velocity = V / t^alpha.

    Views accumulate sub-linearly (most arrive in the first days), so plain
    VPH punishes older videos. alpha=0.7 roughly flattens the typical decay
    curve so a 1-day and a 30-day video can be compared fairly.
    """
    return views / (max(age_hours, MIN_HOURS) ** alpha)


def engagement_rate(views: float, likes: float, comments: float, shares: float = 0) -> float:
    """ER = (L + 2C + 3Sh) / V — comments/shares weigh more than likes."""
    if views <= 0:
        return 0.0
    return (likes + 2 * comments + 3 * shares) / views


def smallness(subscribers: float) -> float:
    """
    1.0 for tiny channels, 0.0 for 1M+ subs: 1 - log10(S)/6, clamped.
    0.67 at 100 subs, 0.5 at 1k, 0.33 at 10k, 0.17 at 100k.
    """
    if subscribers <= 0:
        return 0.5  # unknown
    return clamp(1 - safe_log10(subscribers) / 6)


# Weights of the composite viral score (sum = 1)
VIRAL_WEIGHTS = {
    "outlier": 0.35,
    "views_per_sub": 0.25,
    "momentum": 0.20,
    "engagement": 0.10,
    "smallness": 0.10,
}


def viral_score(video: VideoItem, now: Optional[datetime] = None) -> dict[str, float]:
    """
    Composite 0–100 "video vượt trội" score.

        score = 100 × Σ w_i × f_i
        f_outlier  = logistic(log10(V/M),     center=log10(2),  scale=0.25)
        f_vps      = logistic(log10(V/S),     center=0,         scale=0.40)
        f_momentum = logistic(log10(V/t^0.7), center=2.5,       scale=0.50)
        f_engage   = logistic(ER,             center=0.04,      scale=0.015)
        f_small    = 1 - log10(S)/6

    Returns every intermediate metric so the UI can show *why* a video ranks.
    """
    age = video.age_hours(now)
    subs = video.channel_subscribers
    out = outlier_ratio(video.views, video.channel_median_views, subs)
    vps = views_per_sub(video.views, subs)
    mom = momentum(video.views, age)
    er = engagement_rate(video.views, video.likes, video.comments, video.shares)
    small = smallness(subs)

    f = {
        "outlier": logistic(safe_log10(out), math.log10(2), 0.25),
        "views_per_sub": logistic(safe_log10(vps), 0.0, 0.40),
        "momentum": logistic(safe_log10(mom), 2.5, 0.50),
        "engagement": logistic(er, 0.04, 0.015),
        "smallness": small,
    }
    if subs <= 0:
        # Platforms without subscriber data: redistribute the sub-based weights
        weights = {"outlier": 0.0, "views_per_sub": 0.0, "momentum": 0.6,
                   "engagement": 0.3, "smallness": 0.1}
    else:
        weights = VIRAL_WEIGHTS
    score = 100 * sum(weights[k] * f[k] for k in weights)

    return {
        "viral_score": round(score, 1),
        "outlier": round(out, 2),
        "views_per_sub": round(vps, 2),
        "vph": round(views_per_hour(video.views, age), 1),
        "momentum": round(mom, 1),
        "engagement": round(er, 4),
        "smallness": round(small, 2),
        "age_days": round(age / 24, 1),
    }


def video_labels(scores: dict[str, float], subscribers: int) -> list[str]:
    """Human-readable badges derived from the scores."""
    labels = []
    if scores.get("outlier", 0) >= 5 or (subscribers and scores.get("views_per_sub", 0) >= 3):
        labels.append("🔥 Nổ view")
    elif scores.get("outlier", 0) >= 2:
        labels.append("🚀 Vượt trội")
    if subscribers and subscribers < 10_000 and scores.get("views_per_sub", 0) >= 1:
        labels.append("🌱 Kênh nhỏ ăn view")
    if scores.get("age_days", 999) <= 7 and scores.get("vph", 0) >= 500:
        labels.append("⚡ Đang lên nhanh")
    if scores.get("engagement", 0) >= 0.08:
        labels.append("💬 Tương tác cao")
    return labels


def score_videos(videos: Sequence[VideoItem], now: Optional[datetime] = None) -> list[VideoItem]:
    """Score in place and return videos sorted by viral score (desc)."""
    for v in videos:
        v.scores = viral_score(v, now)
        v.labels = video_labels(v.scores, v.channel_subscribers)
    return sorted(videos, key=lambda v: v.scores.get("viral_score", 0), reverse=True)


# ---------------------------------------------------------------------------
# Channel-level metrics
# ---------------------------------------------------------------------------

def channel_median_views(videos: Sequence[VideoItem], exclude_id: str = "") -> float:
    return median(v.views for v in videos if v.video_id != exclude_id)


def upload_gaps_days(videos: Sequence[VideoItem]) -> list[float]:
    dates = sorted(v.published_at for v in videos if v.published_at)
    return [(b - a).total_seconds() / 86400 for a, b in zip(dates, dates[1:])]


def breakout_channel_score(
    channel: ChannelItem,
    recent_videos: Sequence[VideoItem],
    now: Optional[datetime] = None,
    sub_growth_per_day: Optional[float] = None,
) -> dict[str, float]:
    """
    "Kênh nhỏ đang nổ view" score (0–100).

        recent_ratio = median(V of last uploads) / S
        hit_rate     = share of recent uploads with V > S
        youth        = 1 - age_days/730 (channels < 2 years favoured)
        small        = 1 - log10(S)/6
        growth       = logistic(daily sub growth %, center=1%, scale=0.7%)
                       (only when snapshots exist, else replaced by momentum
                       of the best recent video)

        score = 100 × (0.30 f(recent_ratio) + 0.20 hit_rate + 0.15 youth
                       + 0.15 small + 0.20 growth)
    """
    now = now or datetime.now(timezone.utc)
    subs = max(channel.subscribers, 0)
    views = [v.views for v in recent_videos]
    med = median(views)
    recent_ratio = med / max(subs, MIN_SUBS)
    hit_rate = (sum(1 for x in views if x > max(subs, MIN_SUBS)) / len(views)) if views else 0.0
    age_days = channel.age_days(now)
    youth = clamp(1 - age_days / 730) if age_days else 0.5
    small = smallness(subs)

    if sub_growth_per_day is not None:
        growth = logistic(sub_growth_per_day * 100, 1.0, 0.7)
    else:
        best_mom = max((momentum(v.views, v.age_hours(now)) for v in recent_videos), default=0)
        growth = logistic(safe_log10(best_mom), 2.5, 0.5)

    f_ratio = logistic(safe_log10(recent_ratio), 0.0, 0.4)
    score = 100 * (0.30 * f_ratio + 0.20 * hit_rate + 0.15 * youth + 0.15 * small + 0.20 * growth)
    gaps = upload_gaps_days(recent_videos)
    return {
        "breakout_score": round(score, 1),
        "recent_median_views": round(med),
        "recent_ratio": round(recent_ratio, 2),
        "hit_rate": round(hit_rate, 2),
        "channel_age_days": round(age_days),
        "uploads_per_week": round(7 / statistics.mean(gaps), 2) if gaps and statistics.mean(gaps) > 0 else 0.0,
        "growth_signal": round(growth, 2),
    }


def sub_growth_rate(snapshots: Sequence[tuple[datetime, int]]) -> Optional[float]:
    """Daily relative subscriber growth from (time, subs) snapshots, oldest first."""
    if len(snapshots) < 2:
        return None
    (t0, s0), (t1, s1) = snapshots[0], snapshots[-1]
    days = (t1 - t0).total_seconds() / 86400
    if days <= 0 or s0 <= 0:
        return None
    return (s1 / s0) ** (1 / days) - 1


# ---------------------------------------------------------------------------
# Niche-level metrics
# ---------------------------------------------------------------------------

def niche_score(videos: Sequence[VideoItem], trend_interest: Optional[float] = None,
                now: Optional[datetime] = None) -> dict[str, float]:
    """
    Niche opportunity score (0–100) from a keyword's search results.

        demand      = logistic(log10(median V), center=4 (10k), scale=0.6)
                      blended 70/30 with Google Trends interest/100 if given
        opportunity = share of results where S < 100k AND V/S >= 1
        competition = share of results from channels with S >= 1M
                      blended with logistic(log10(median S), 5, 0.6)
        freshness   = share of results published in the last 30 days

        score = 100 × (0.35 demand + 0.30 opportunity
                       + 0.20 (1 - competition) + 0.15 freshness)
    """
    now = now or datetime.now(timezone.utc)
    if not videos:
        return {"niche_score": 0.0, "demand": 0.0, "opportunity": 0.0,
                "competition": 0.0, "freshness": 0.0, "median_views": 0, "median_subs": 0}

    med_views = median(v.views for v in videos)
    known_subs = [v.channel_subscribers for v in videos if v.channel_subscribers > 0]
    med_subs = median(known_subs)

    demand = logistic(safe_log10(med_views), 4.0, 0.6)
    if trend_interest is not None:
        demand = 0.7 * demand + 0.3 * clamp(trend_interest / 100)

    if known_subs:
        small_wins = sum(1 for v in videos if 0 < v.channel_subscribers < 100_000
                         and v.views >= v.channel_subscribers)
        opportunity = small_wins / len(known_subs)
        big_share = sum(1 for s in known_subs if s >= 1_000_000) / len(known_subs)
        competition = 0.5 * big_share + 0.5 * logistic(safe_log10(med_subs), 5.0, 0.6)
    else:
        # No subscriber data (e.g. TikTok search): use view dispersion instead
        top = max(v.views for v in videos)
        opportunity = clamp(1 - med_views / top) if top else 0.0
        competition = 0.5

    fresh_cut = now - timedelta(days=30)
    dated = [v for v in videos if v.published_at]
    freshness = (sum(1 for v in dated if v.published_at >= fresh_cut) / len(dated)) if dated else 0.0

    score = 100 * (0.35 * demand + 0.30 * opportunity + 0.20 * (1 - competition) + 0.15 * freshness)
    return {
        "niche_score": round(score, 1),
        "demand": round(demand, 2),
        "opportunity": round(opportunity, 2),
        "competition": round(competition, 2),
        "freshness": round(freshness, 2),
        "median_views": round(med_views),
        "median_subs": round(med_subs),
    }


def niche_verdict(score: float) -> str:
    if score >= 70:
        return "🟢 Ngách rất tiềm năng — nên làm ngay"
    if score >= 55:
        return "🟡 Ngách khá — cần góc nhìn khác biệt"
    if score >= 40:
        return "🟠 Cạnh tranh cao hoặc nhu cầu thấp"
    return "🔴 Không nên vào lúc này"


def keyword_score(median_views: float, median_subs: float, total_results: int,
                  trend_interest: Optional[float] = None) -> dict[str, float]:
    """
    Keyword opportunity (0–100) — high demand, beatable competitors.

        demand      = logistic(log10(median V of top results), 4, 0.6)
        weakness    = 1 - logistic(log10(median S of top results), 5, 0.6)
        saturation  = logistic(log10(total results), 5.5, 0.7)
        score = 100 × (0.45 demand + 0.35 weakness + 0.20 (1 - saturation))
    """
    demand = logistic(safe_log10(median_views), 4.0, 0.6)
    if trend_interest is not None:
        demand = 0.7 * demand + 0.3 * clamp(trend_interest / 100)
    weakness = 1 - logistic(safe_log10(median_subs), 5.0, 0.6) if median_subs > 0 else 0.5
    saturation = logistic(safe_log10(max(total_results, 1)), 5.5, 0.7)
    score = 100 * (0.45 * demand + 0.35 * weakness + 0.20 * (1 - saturation))
    return {
        "keyword_score": round(score, 1),
        "demand": round(demand, 2),
        "weakness": round(weakness, 2),
        "saturation": round(saturation, 2),
    }


def classify_keyword(keyword: str) -> str:
    """Short head term (≤3 words) vs long-tail."""
    return "short" if len(keyword.split()) <= 3 else "long_tail"


# ---------------------------------------------------------------------------
# Monetization
# ---------------------------------------------------------------------------

# Approximate long-form RPM in USD (creator revenue per 1000 views) by country
RPM_BY_COUNTRY = {
    "US": 5.0, "AU": 5.0, "CA": 4.5, "GB": 4.5, "DE": 4.0, "JP": 2.5, "KR": 2.5,
    "FR": 3.0, "TW": 1.5, "SG": 3.0, "TH": 0.6, "ID": 0.4, "PH": 0.3, "IN": 0.5,
    "VN": 0.5, "BR": 0.8, "MX": 0.8, "CN": 1.0, "OTHER": 1.0,
}

# Niche multiplier on top of country RPM
NICHE_RPM_MULTIPLIER = {
    "finance": 3.0, "business": 2.5, "tech": 2.0, "education": 1.6, "health": 1.6,
    "real_estate": 2.5, "gaming": 0.7, "entertainment": 0.6, "film": 0.6,
    "music": 0.4, "kids": 0.3, "vlog": 0.8, "food": 0.9, "beauty": 1.0,
    "news": 0.9, "sport": 0.8, "general": 1.0,
}

SHORTS_RPM_FACTOR = 0.06  # Shorts pay roughly 3–10% of long-form RPM

YPP_FULL = {"subs": 1000, "watch_hours": 4000, "shorts_views_90d": 10_000_000}
YPP_EARLY = {"subs": 500, "watch_hours": 3000, "shorts_views_90d": 3_000_000, "uploads_90d": 3}


def estimate_watch_hours(videos: Sequence[VideoItem], avd_ratio: float = 0.35,
                         now: Optional[datetime] = None) -> float:
    """
    Public-data estimate of 12-month watch hours for long-form videos:

        Σ_{long videos published ≤ 365d} V × duration × AVD% / 3600

    AVD% (average view duration ratio) defaults to 35%. Lifetime views are used
    as a proxy for 12-month views, so the estimate is optimistic for old videos.
    """
    now = now or datetime.now(timezone.utc)
    cut = now - timedelta(days=365)
    total = 0.0
    for v in videos:
        if v.is_short or not v.published_at or v.published_at < cut:
            continue
        total += v.views * v.duration_sec * avd_ratio / 3600
    return total


def shorts_views_90d(videos: Sequence[VideoItem], now: Optional[datetime] = None) -> int:
    now = now or datetime.now(timezone.utc)
    cut = now - timedelta(days=90)
    return sum(v.views for v in videos if v.is_short and v.published_at and v.published_at >= cut)


def monetization_check(channel: ChannelItem, videos: Sequence[VideoItem], avd_ratio: float = 0.35,
                       country: str = "VN", niche: str = "general",
                       now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    hours = estimate_watch_hours(videos, avd_ratio, now)
    shorts90 = shorts_views_90d(videos, now)
    uploads90 = sum(1 for v in videos if v.published_at and v.published_at >= now - timedelta(days=90))
    subs = channel.subscribers

    full_ok = subs >= YPP_FULL["subs"] and (
        hours >= YPP_FULL["watch_hours"] or shorts90 >= YPP_FULL["shorts_views_90d"])
    early_ok = subs >= YPP_EARLY["subs"] and uploads90 >= YPP_EARLY["uploads_90d"] and (
        hours >= YPP_EARLY["watch_hours"] or shorts90 >= YPP_EARLY["shorts_views_90d"])

    rpm = RPM_BY_COUNTRY.get(country.upper(), RPM_BY_COUNTRY["OTHER"]) * NICHE_RPM_MULTIPLIER.get(niche, 1.0)
    cut30 = now - timedelta(days=30)
    recent = [v for v in videos if v.published_at and v.published_at >= cut30]
    long_views_30 = sum(v.views for v in recent if not v.is_short)
    short_views_30 = sum(v.views for v in recent if v.is_short)
    # Fallback when nothing was uploaded in 30 days: average monthly views of the sample
    if not recent and videos:
        span_days = max((now - min(v.published_at for v in videos if v.published_at)).days, 30) \
            if any(v.published_at for v in videos) else 365
        factor = 30 / span_days
        long_views_30 = sum(v.views for v in videos if not v.is_short) * factor
        short_views_30 = sum(v.views for v in videos if v.is_short) * factor
    monthly_usd = long_views_30 / 1000 * rpm + short_views_30 / 1000 * rpm * SHORTS_RPM_FACTOR

    return {
        "subscribers": subs,
        "est_watch_hours_12m": round(hours),
        "shorts_views_90d": shorts90,
        "uploads_90d": uploads90,
        "ypp_full_eligible": full_ok,
        "ypp_early_eligible": early_ok,
        "progress_subs": round(clamp(subs / YPP_FULL["subs"]), 2),
        "progress_watch_hours": round(clamp(hours / YPP_FULL["watch_hours"]), 2),
        "progress_shorts": round(clamp(shorts90 / YPP_FULL["shorts_views_90d"]), 2),
        "rpm_usd": round(rpm, 2),
        "est_monthly_revenue_usd": round(monthly_usd, 2),
        "est_monthly_revenue_range": [round(monthly_usd * 0.5, 2), round(monthly_usd * 1.6, 2)],
    }


# ---------------------------------------------------------------------------
# Posting time & SEO heuristics
# ---------------------------------------------------------------------------

def best_posting_slots(videos: Sequence[VideoItem], tz_offset_hours: int = 7,
                       top_n: int = 5) -> list[dict]:
    """
    Rank (weekday, hour) slots by the median outlier score of videos published
    there, weighted by sample size: slot_score = median(outlier) × log2(1 + n).
    """
    buckets: dict[tuple[int, int], list[float]] = {}
    for v in videos:
        if not v.published_at:
            continue
        local = v.published_at + timedelta(hours=tz_offset_hours)
        key = (local.weekday(), local.hour)
        buckets.setdefault(key, []).append(v.scores.get("outlier") or outlier_ratio(
            v.views, v.channel_median_views, v.channel_subscribers))
    ranked = sorted(
        ({"weekday": k[0], "hour": k[1], "n": len(vals),
          "slot_score": round(median(vals) * math.log2(1 + len(vals)), 2)}
         for k, vals in buckets.items()),
        key=lambda x: x["slot_score"], reverse=True)
    return ranked[:top_n]


def seo_audit(title: str, description: str, tags: Sequence[str], keyword: str = "") -> dict:
    """Rule-based YouTube SEO checklist. Each passed check adds its weight."""
    kw = keyword.lower().strip()
    t = title.strip()
    d = description.strip()
    first_lines = "\n".join(d.splitlines()[:2]).lower()
    hashtags = [w for w in d.split() if w.startswith("#")]
    has_chapters = sum(1 for line in d.splitlines() if line.strip()[:5].count(":") >= 1
                       and line.strip()[:1].isdigit()) >= 3
    checks = [
        ("Tiêu đề dài 40–70 ký tự", 15, 40 <= len(t) <= 70),
        ("Từ khoá nằm trong tiêu đề", 20, bool(kw) and kw in t.lower()),
        ("Từ khoá nằm trong 40 ký tự đầu tiêu đề", 10, bool(kw) and kw in t.lower()[:40]),
        ("Mô tả ≥ 200 ký tự", 10, len(d) >= 200),
        ("Từ khoá trong 2 dòng đầu mô tả", 10, bool(kw) and kw in first_lines),
        ("Có 5–15 tags", 10, 5 <= len(tags) <= 15),
        ("Có tag chứa từ khoá", 5, bool(kw) and any(kw in tg.lower() for tg in tags)),
        ("Có 3–5 hashtag", 5, 3 <= len(hashtags) <= 5),
        ("Có chapters (mốc thời gian)", 10, has_chapters),
        ("Tiêu đề không viết HOA toàn bộ", 5, not t.isupper()),
    ]
    score = sum(w for _, w, ok in checks if ok)
    return {
        "seo_score": score,
        "checks": [{"check": name, "weight": w, "passed": ok} for name, w, ok in checks],
    }
