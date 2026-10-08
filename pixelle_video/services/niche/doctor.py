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
Connection doctor — makes one small REAL call to every configured API and
reports whether it works, so you can confirm the app runs on live data.

Run locally after setting your keys:
    uv run python -m pixelle_video.services.niche.doctor
    uv run python -m pixelle_video.services.niche.doctor --platform douyin
"""

import argparse
import asyncio

from pixelle_video.config import config_manager
from pixelle_video.services.niche.sources import PLATFORMS

OK, FAIL, SKIP = "✅", "❌", "➖"


async def _check_youtube(cfg) -> tuple[str, str]:
    if not cfg.youtube_api_key:
        return SKIP, "chưa cấu hình YOUTUBE_API_KEY"
    from pixelle_video.services.niche.youtube import YouTubeClient, YouTubeError
    yt = YouTubeClient(cfg.youtube_api_key)
    try:
        ids, total = await yt.search_video_ids("test", max_results=1, period="all")
        vids = await yt.videos(ids) if ids else []
        sample = vids[0].title if vids else "(không có kết quả)"
        return OK, f"{yt.units_used} units · ví dụ: {sample[:50]}"
    except YouTubeError as e:
        return FAIL, str(e)


async def _check_llm(cfg_root) -> tuple[str, str]:
    if not cfg_root.is_llm_configured():
        return SKIP, "chưa cấu hình LLM (api_key/base_url/model)"
    from pixelle_video.services.llm_service import LLMService
    try:
        out = await LLMService({})("Trả lời đúng một từ: OK", max_tokens=10)
        return OK, f"model trả lời: {str(out).strip()[:40]}"
    except Exception as e:
        return FAIL, str(e)[:120]


async def _check_reddit() -> tuple[str, str]:
    from pixelle_video.services.niche.sources import reddit_search
    try:
        res = await reddit_search("news", "week", 1)
        return OK, f"{len(res)} kết quả"
    except Exception as e:
        return FAIL, str(e)[:120]


async def _check_trends(cfg) -> tuple[str, str]:
    from pixelle_video.services.niche.sources import google_trending
    try:
        res = await google_trending(cfg.default_region)
        return OK, f"{len(res)} xu hướng ({cfg.default_region})"
    except Exception as e:
        return FAIL, str(e)[:120]


async def _check_tikhub(cfg, platform: str) -> tuple[str, str]:
    if not cfg.tikhub_api_key:
        return SKIP, "chưa cấu hình TIKHUB_API_KEY"
    from pixelle_video.services.niche.sources import TikHubClient
    th = TikHubClient(cfg.tikhub_api_key, cfg.tikhub_endpoints)
    try:
        res = await th.search(platform, "test")
        return OK, f"{len(res)} bài"
    except Exception as e:
        return FAIL, str(e)[:160]


async def run(platforms: list[str]) -> bool:
    cfg = config_manager.config.niche
    cfg_root = config_manager.config
    print("===== KIỂM TRA KẾT NỐI API (số liệu thật) =====\n")
    rows = [
        ("YouTube Data API", await _check_youtube(cfg)),
        ("LLM (AI)", await _check_llm(cfg_root)),
        ("Reddit", await _check_reddit()),
        ("Google Trends", await _check_trends(cfg)),
    ]
    for p in platforms:
        if PLATFORMS.get(p, {}).get("source") == "tikhub":
            rows.append((f"TikHub · {PLATFORMS[p]['label']}", await _check_tikhub(cfg, p)))
    ok = True
    for name, (status, detail) in rows:
        if status == FAIL:
            ok = False
        print(f"{status}  {name:<28} {detail}")
    print("\nMẹo: key có thể nhập ở file .env, config.yaml, hoặc trong giao diện (Cài đặt API nghiên cứu).")
    return ok


def main():
    ap = argparse.ArgumentParser(description="Kiểm tra kết nối API cho bộ nghiên cứu ngách")
    ap.add_argument("--platform", action="append", default=[],
                    help="Nền tảng TikHub muốn test (vd: douyin, tiktok). Lặp lại được.")
    args = ap.parse_args()
    ok = asyncio.run(run(args.platform or ["tiktok"]))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
