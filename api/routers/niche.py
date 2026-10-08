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
Niche research endpoints: multi-platform niche mining, viral video scoring,
channel analytics, keyword research, trends, AI content and SEO helpers.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from loguru import logger
from pydantic import BaseModel, Field

from pixelle_video.services.niche import NicheService, SearchFilters
from pixelle_video.services.niche import ai as niche_ai
from pixelle_video.services.niche.export import to_excel

router = APIRouter(prefix="/niche", tags=["Niche Research"])

_service: Optional[NicheService] = None


def service() -> NicheService:
    global _service
    if _service is None:
        _service = NicheService()
    return _service


async def _run(coro):
    try:
        return await coro
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Niche API error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


class SearchRequest(SearchFilters):
    with_trends: bool = False
    with_insights: bool = False


class KeywordRequest(BaseModel):
    seed: str
    region: str = "VN"
    language: str = "vi"
    analyze_top: int = Field(default=5, ge=0, le=20)
    deep: bool = True
    with_trends: bool = False


class ChannelRequest(BaseModel):
    channel: str = Field(description="Channel URL, @handle, channel id or a video URL")
    max_videos: int = Field(default=50, ge=5, le=500)
    is_mine: bool = False


class MonetizationRequest(BaseModel):
    channel: str
    niche: str = "general"
    country: str = ""


class HuntRequest(BaseModel):
    query: str
    period: str = "30d"
    max_subs: int = 100_000
    region: str = "VN"
    language: str = "vi"
    duration: str = "any"


class MarketRequest(BaseModel):
    keyword: str
    regions: list[str] = Field(default_factory=lambda: ["VN", "US", "ID", "TH", "PH", "IN"])
    period: str = "30d"
    translate: bool = True


class TopicsRequest(BaseModel):
    query: str
    count: int = Field(default=15, ge=3, le=40)
    region: str = "VN"
    language: str = "vi"
    period: str = "30d"
    platforms: list[str] = Field(default_factory=lambda: ["youtube"])


class ScriptRequest(BaseModel):
    topic: str
    hook: str = ""
    duration_sec: int = Field(default=60, ge=15, le=1800)
    style: str = "kể chuyện cuốn hút"
    language: str = "vi"
    reference: str = ""


class DoctorRequest(BaseModel):
    channel: str
    competitors: list[str] = Field(default_factory=list)
    use_ai: bool = True


class SEORequest(BaseModel):
    video: str = ""
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    keyword: str = ""
    use_ai: bool = True


class CalendarItem(BaseModel):
    title: str
    scheduled_at: datetime
    platform: str = "youtube"
    status: str = "idea"
    topic: str = ""
    script: str = ""
    notes: str = ""


@router.get("/overview")
async def overview():
    return service().overview()


@router.post("/estimate")
async def estimate(request: SearchFilters):
    return service().estimate_cost(request)


@router.post("/search")
async def search(request: SearchRequest):
    svc = service()
    filters = SearchFilters(**request.model_dump(exclude={"with_trends", "with_insights"}))
    result = await _run(svc.search(filters, with_trends=request.with_trends))
    insights = None
    if request.with_insights and result.videos and svc.llm_ready():
        insights = await _run(niche_ai.keyword_insights(svc.llm, filters.query, result.videos, filters.language))
    return {"result": result, "insights": insights}


@router.post("/search/export")
async def search_export(request: SearchFilters):
    result = await _run(service().search(request))
    data = to_excel({"Videos": result.videos, "Niche": [result.niche]})
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="niche.xlsx"'},
    )


@router.post("/save")
async def save(request: SearchFilters):
    svc = service()
    result = await _run(svc.search(request))
    return {"id": svc.save_niche(result)}


@router.get("/saved")
async def saved():
    return service().storage.list_niches()


@router.delete("/saved/{niche_id}")
async def delete_saved(niche_id: int):
    service().storage.delete_niche(niche_id)
    return {"ok": True}


@router.post("/keywords")
async def keywords(request: KeywordRequest):
    return await _run(service().keyword_research(**request.model_dump()))


@router.post("/channel/analyze")
async def channel_analyze(request: ChannelRequest):
    return await _run(service().channel_analysis(request.channel, request.max_videos, is_mine=request.is_mine))


@router.post("/channel/monetization")
async def channel_monetization(request: MonetizationRequest):
    return await _run(service().monetization(request.channel, request.niche, request.country))


@router.post("/channel/doctor")
async def channel_doctor(request: DoctorRequest):
    return await _run(service().channel_doctor(request.channel, request.competitors, request.use_ai))


@router.post("/channels/hunt")
async def channels_hunt(request: HuntRequest):
    return await _run(service().hunt_channels(**request.model_dump()))


@router.post("/multi-market")
async def multi_market(request: MarketRequest):
    return await _run(service().multi_market(request.keyword, request.regions, request.period, request.translate))


@router.get("/trends")
async def trends(region: str = "VN", category_id: str = "", include: str = "youtube,google,reddit"):
    return await _run(service().trends(region, category_id, [p for p in include.split(",") if p]))


@router.post("/topics")
async def topics(request: TopicsRequest):
    f = SearchFilters(query=request.query, region=request.region, language=request.language,
                      period=request.period, platforms=request.platforms)
    res = await _run(service().winning_topics(request.query, f, request.count))
    return {"topics": res["topics"], "winners": res["winners"][:20]}


@router.post("/script")
async def script(request: ScriptRequest):
    return await _run(service().write_script(**request.model_dump()))


@router.post("/seo")
async def seo(request: SEORequest):
    return await _run(service().seo(request.video, request.title, request.description, request.tags,
                                    request.keyword, request.use_ai))


@router.get("/calendar")
async def calendar_list():
    return service().storage.list_calendar()


@router.post("/calendar")
async def calendar_add(item: CalendarItem):
    d = item.model_dump()
    return {"id": service().storage.add_calendar(d.pop("title"), d.pop("scheduled_at"), **d)}


@router.put("/calendar/{item_id}")
async def calendar_update(item_id: int, item: CalendarItem):
    service().storage.update_calendar(item_id, **item.model_dump())
    return {"ok": True}


@router.delete("/calendar/{item_id}")
async def calendar_delete(item_id: int):
    service().storage.delete_calendar(item_id)
    return {"ok": True}


# ---- Phase 2: teardown, media prompts, affiliate ----

class TeardownRequest(BaseModel):
    video: str
    language: str = "vi"


class MediaPromptRequest(BaseModel):
    title: str
    scenes: list[str]
    style: str = "cinematic"
    tool: str = "generic"


class ProductHuntRequest(BaseModel):
    keyword: str = ""
    region: str = "VN"
    limit: int = Field(default=40, ge=1, le=100)


class SalesScriptRequest(BaseModel):
    product: str
    pain_points: str = ""
    benefits: str = ""
    duration_sec: int = Field(default=45, ge=15, le=180)
    language: str = "vi"


@router.post("/teardown")
async def teardown(request: TeardownRequest):
    return await _run(service().teardown(request.video, request.language))


@router.post("/media-prompts")
async def media_prompts(request: MediaPromptRequest):
    return await _run(service().media_prompts(request.title, request.scenes, request.style, request.tool))


@router.post("/products/hunt")
async def products_hunt(request: ProductHuntRequest):
    return await _run(service().hunt_products(request.keyword, request.region, request.limit))


@router.post("/sales-script")
async def sales_script(request: SalesScriptRequest):
    return await _run(service().sales_script(request.product, request.pain_points, request.benefits,
                                             request.duration_sec, request.language))
