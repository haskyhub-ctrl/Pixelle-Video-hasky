"""Tests for niche research formulas, parsers, storage and search pipeline."""

from datetime import datetime, timedelta, timezone

import pytest

from pixelle_video.services.niche import formulas
from pixelle_video.services.niche.models import ChannelItem, SearchFilters, VideoItem
from pixelle_video.services.niche.service import NicheService, is_adult, normalize_text, topic_match
from pixelle_video.services.niche.sources import iter_posts, post_to_video
from pixelle_video.services.niche.storage import NicheStorage
from pixelle_video.services.niche.youtube import (
    parse_channel_ref,
    parse_iso_duration,
    parse_video_ref,
)

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)


def vid(vid_id="v", views=1000, subs=1000, median=0.0, hours=48, likes=0, comments=0,
        duration=600, title="phim tổng tài hay", channel="c1"):
    return VideoItem(video_id=vid_id, views=views, channel_subscribers=subs, channel_median_views=median,
                     published_at=NOW - timedelta(hours=hours), likes=likes, comments=comments,
                     duration_sec=duration, title=title, channel_id=channel)


# ----------------------------------------------------------------- formulas

def test_outlier_uses_channel_median_then_subs():
    assert formulas.outlier_ratio(10_000, 1_000, 50_000) == 10
    assert formulas.outlier_ratio(10_000, 0, 5_000) == 2
    assert formulas.outlier_ratio(10_000, 0, 0) == 100  # floor of 100 subs


def test_momentum_compensates_age():
    young = formulas.momentum(10_000, 24)
    old = formulas.momentum(10_000 * 30, 24 * 30)
    # 30x the views over 30x the time should beat plain VPH comparison (equal VPH)
    assert old > young
    assert formulas.views_per_hour(10_000, 24) == pytest.approx(formulas.views_per_hour(300_000, 720))


def test_viral_score_ranks_outlier_above_normal():
    hit = vid("hit", views=500_000, subs=5_000, median=8_000, likes=20_000, comments=2_000)
    normal = vid("normal", views=8_000, subs=5_000, median=8_000, likes=200, comments=10)
    ranked = formulas.score_videos([normal, hit], NOW)
    assert ranked[0].video_id == "hit"
    assert ranked[0].scores["viral_score"] > 70
    assert ranked[1].scores["viral_score"] < 50
    assert "🔥 Nổ view" in ranked[0].labels


def test_viral_score_without_subscribers_is_bounded():
    s = formulas.viral_score(vid(views=1_000_000, subs=0, likes=50_000), NOW)
    assert 0 <= s["viral_score"] <= 100


def test_smallness_curve():
    assert formulas.smallness(1_000) == pytest.approx(0.5)
    assert formulas.smallness(1_000_000) == 0
    assert formulas.smallness(10) > formulas.smallness(10_000)


def test_niche_score_prefers_small_channel_wins():
    easy = [vid(str(i), views=50_000, subs=10_000, hours=24 * 5) for i in range(10)]
    hard = [vid(str(i), views=50_000, subs=5_000_000, hours=24 * 300) for i in range(10)]
    e, h = formulas.niche_score(easy, now=NOW), formulas.niche_score(hard, now=NOW)
    assert e["opportunity"] == 1.0 and h["opportunity"] == 0.0
    assert e["niche_score"] > h["niche_score"] + 20
    assert formulas.niche_score([], now=NOW)["niche_score"] == 0


def test_keyword_score_monotonic():
    weak = formulas.keyword_score(100_000, 5_000, 10_000)
    strong = formulas.keyword_score(100_000, 5_000_000, 10_000)
    assert weak["keyword_score"] > strong["keyword_score"]
    assert formulas.classify_keyword("phim tổng tài") == "short"
    assert formulas.classify_keyword("phim tổng tài bá đạo hay nhất") == "long_tail"


def test_breakout_channel_and_growth():
    ch = ChannelItem(channel_id="c", subscribers=2_000, published_at=NOW - timedelta(days=120))
    recent = [vid(str(i), views=40_000, subs=2_000, hours=24 * (i + 1) * 3) for i in range(10)]
    s = formulas.breakout_channel_score(ch, recent, NOW)
    assert s["hit_rate"] == 1.0 and s["breakout_score"] > 70
    g = formulas.sub_growth_rate([(NOW - timedelta(days=10), 1000), (NOW, 2000)])
    assert g == pytest.approx(2 ** 0.1 - 1)
    assert formulas.sub_growth_rate([(NOW, 1)]) is None


def test_monetization_check():
    ch = ChannelItem(channel_id="c", subscribers=1500, country="VN")
    # 10 long videos, 20 min, 10k views each, in the last year → 10*10000*1200*0.35/3600 ≈ 11,667 h
    videos = [vid(str(i), views=10_000, duration=1200, hours=24 * 30 * (i + 1)) for i in range(10)]
    res = formulas.monetization_check(ch, videos, 0.35, "VN", "general", NOW)
    assert res["est_watch_hours_12m"] == pytest.approx(11_667, rel=0.01)
    assert res["ypp_full_eligible"] is True
    small = formulas.monetization_check(ChannelItem(channel_id="x", subscribers=800), videos, now=NOW)
    assert small["ypp_full_eligible"] is False
    assert res["est_monthly_revenue_usd"] > 0


def test_seo_audit_scores_good_metadata_higher():
    good = formulas.seo_audit(
        "Phim tổng tài hay nhất 2026: 10 bộ xem là nghiện ngay",
        "Phim tổng tài hay nhất được tổng hợp...\n" + "x " * 150 +
        "\n00:00 Mở đầu\n01:00 Phần 1\n02:00 Phần 2\n#phim #tongtai #review",
        ["phim tổng tài", "phim", "tổng tài", "ngôn tình", "review phim"], "phim tổng tài")
    bad = formulas.seo_audit("PHIM", "", [], "phim tổng tài")
    assert good["seo_score"] >= 90
    assert bad["seo_score"] < 20


def test_best_posting_slots():
    vids = [vid(str(i), views=10_000 * (i + 1), subs=1000) for i in range(5)]
    for v in vids:
        v.scores = formulas.viral_score(v, NOW)
    slots = formulas.best_posting_slots(vids)
    assert slots and {"weekday", "hour", "slot_score"} <= slots[0].keys()


# ------------------------------------------------------------------ parsers

def test_youtube_parsers():
    assert parse_iso_duration("PT1H2M3S") == 3723
    assert parse_iso_duration("PT45S") == 45
    assert parse_iso_duration("P1DT1S") == 86401
    assert parse_channel_ref("@abc") == {"handle": "@abc"}
    assert parse_channel_ref("https://www.youtube.com/@abc/videos") == {"handle": "@abc"}
    assert parse_channel_ref("https://youtube.com/channel/UC" + "a" * 22) == {"id": "UC" + "a" * 22}
    assert parse_channel_ref("https://youtu.be/dQw4w9WgXcQ") == {"video_id": "dQw4w9WgXcQ"}
    assert parse_video_ref("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert parse_video_ref("dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_tikhub_generic_parser_douyin_and_tiktok():
    douyin = {"data": {"data": [{"type": 1, "aweme_info": {
        "aweme_id": "123", "desc": "霸道总裁 短剧", "create_time": 1759000000,
        "statistics": {"play_count": 0, "digg_count": 5000, "comment_count": 300, "share_count": 40},
        "author": {"nickname": "abc", "sec_uid": "u1", "follower_count": 20000},
        "video": {"duration": 61000}}}]}}
    posts = [post_to_video(p, "douyin") for p in iter_posts(douyin)]
    assert len(posts) == 1
    p = posts[0]
    assert p.video_id == "123" and p.likes == 5000 and p.views == 5000 * 20
    assert p.duration_sec == 61 and p.channel_subscribers == 20000 and p.published_at.year == 2025

    tiktok = {"data": [{"item": {"id": "9", "desc": "ceo drama", "createTime": "1759000000",
                                 "stats": {"playCount": 1_200_000, "diggCount": 1000},
                                 "author": {"uniqueId": "x"}, "authorStats": {"followerCount": "1.2m"}}}]}
    t = post_to_video(next(iter_posts(tiktok)), "tiktok")
    assert t.views == 1_200_000 and t.channel_subscribers == 1_200_000 and t.channel_title == "x"


def test_topic_match_and_adult():
    assert normalize_text("Phim Tổng Tài Đỉnh") == "phim tong tai dinh"
    assert topic_match("phim tổng tài", vid(title="Top phim tong tai hay nhat"))
    assert not topic_match("phim tổng tài", vid(title="Hướng dẫn nấu phở bò"))
    assert topic_match("霸道总裁", vid(title="霸道总裁爱上我"))
    assert is_adult(vid(title="clip 18+ nóng"))
    assert not is_adult(vid(title="phim gia đình"))


# --------------------------------------------------------- storage/service

def test_storage_roundtrip(tmp_path):
    s = NicheStorage(str(tmp_path / "n.db"))
    nid = s.save_niche("q", ["youtube"], 66.5, {"a": 1})
    assert s.list_niches()[0]["summary"] == {"a": 1}
    s.delete_niche(nid)
    assert s.list_niches() == []
    s.track_channel("c1", "Chan", is_mine=True)
    s.track_channel("c1", "Chan 2")
    assert s.list_channels(mine_only=True)[0]["title"] == "Chan 2"
    s.add_snapshot("c1", 10, 100, 1)
    assert s.snapshots("c1")[0]["subscribers"] == 10
    cid = s.add_calendar("Video 1", NOW)
    s.update_calendar(cid, status="done")
    assert s.list_calendar()[0]["status"] == "done"
    s.log_usage("youtube", 2, 200)
    assert s.usage_today()["youtube"]["units"] == 200


async def test_search_pipeline_filters_and_caps(tmp_path, monkeypatch):
    svc = NicheService(storage=NicheStorage(str(tmp_path / "n.db")))
    data = [vid(f"a{i}", views=100_000 - i, subs=2_000, channel="same") for i in range(5)]
    data += [vid("off", title="cách nấu phở"), vid("adult", title="phim tổng tài 18+"),
             vid("short", duration=30, channel="c2")]

    async def fake_fetch(platform, f, yt, th):
        return [v.model_copy(deep=True) for v in data]

    monkeypatch.setattr(svc, "_fetch_platform", fake_fetch)
    f = SearchFilters(query="phim tổng tài", platforms=["reddit"], duration="long", max_per_channel=3)
    res = await svc.search(f)
    ids = [v.video_id for v in res.videos]
    assert len(ids) == 3 and all(i.startswith("a") for i in ids)
    assert res.hidden_channel_cap == 2 and res.hidden_adult == 1
    assert [v.video_id for v in res.hidden_off_topic] == ["off"]
    assert res.niche["niche_score"] > 0


def test_doctor_checks_flags_inactive_channel(tmp_path):
    svc = NicheService(storage=NicheStorage(str(tmp_path / "n.db")))
    checks = svc.doctor_checks({"days_since_last_upload": 40, "uploads_per_week": 0.2, "flop_rate": 0.5,
                                "avg_engagement": 0.01, "median_views": 100},
                               [{"median_views": 10_000, "uploads_per_week": 3}])
    problems = {c["problem"] for c in checks}
    assert "Kênh ngừng đăng quá lâu" in problems and "Thua đối thủ về view" in problems
    assert svc.health_score(checks) < 50
