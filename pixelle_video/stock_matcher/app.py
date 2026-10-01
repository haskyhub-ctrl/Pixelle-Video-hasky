"""
Module D (UI) - Streamlit dashboard for script-to-stock matching (Vietnamese UI).

Desktop:     python -m pixelle_video.stock_matcher.desktop   (own window)
Standalone:  streamlit run pixelle_video/stock_matcher/app.py
Embedded:    web/pages/3_🎞️_Stock_Matcher.py calls render()

All work lives in a project saved on disk (see project_store.py) and is saved
after every change, so nothing is lost when the window or browser tab closes.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    # Allow `streamlit run pixelle_video/stock_matcher/app.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from pixelle_video.stock_matcher.auth_manager import PROVIDER_ENV_VARS, AuthManager
from pixelle_video.stock_matcher.downloader import CustomClip, Downloader
from pixelle_video.stock_matcher.llm_extractor import check_connection
from pixelle_video.stock_matcher.models import (
    DownloadItem,
    SceneAnalysis,
    SearchOutcome,
    StockVideoResult,
)
from pixelle_video.stock_matcher.nlp_parser import ScriptParser
from pixelle_video.stock_matcher.project_store import ProjectState, ProjectStore
from pixelle_video.stock_matcher.stock_searcher import (
    DEFAULT_PROVIDERS,
    PROVIDER_CLASSES,
    StockSearchEngine,
)
from pixelle_video.stock_matcher.vision_ranker import rerank_outcomes

PREFIX = "sm_"
GRID_COLUMNS = 3
# Clips fetched per query and provider; only the best few are shown
FETCH_PER_QUERY = 8
SETTINGS_FILE = "ui_settings.json"
EXAMPLE_SCRIPT = (
    "An engineer is working late at night, coding on a laptop.\n"
    "The city lights shine through the office window.\n"
    "In the morning, the team celebrates a successful product launch."
)
DEFAULT_SETTINGS = {
    "providers": None,
    "orientation": "any",
    "min_duration": 0.0,
    "clips_per_scene": 3,
    "use_llm": True,
    "ai_rerank": False,
    "ai_top_n": 6,
    "wps": 2.5,
    "show_video": False,
}
ORIENTATION_LABELS = {"any": "Bất kỳ", "landscape": "Ngang (16:9)",
                      "portrait": "Dọc (9:16)", "square": "Vuông"}


# ------------------------------------------------------------------ state


def _key(name: str) -> str:
    return PREFIX + name


def _run(coro):
    try:
        from web.utils.async_helpers import run_async

        return run_async(coro)
    except ImportError:
        return asyncio.run(coro)


def _store() -> ProjectStore:
    if _key("store") not in st.session_state:
        st.session_state[_key("store")] = ProjectStore()
    return st.session_state[_key("store")]


def _auth() -> AuthManager:
    if _key("auth") not in st.session_state:
        st.session_state[_key("auth")] = AuthManager()
    return st.session_state[_key("auth")]


def _clear_widget_state() -> None:
    """Forget per-scene widget values when switching / re-analysing a project."""
    widget_prefixes = tuple(_key(p) for p in ("q_", "inc_", "up_", "play_", "more_",
                                              "script_box", "report"))
    for k in [k for k in st.session_state if k.startswith(widget_prefixes)]:
        del st.session_state[k]


def _project() -> ProjectState:
    """Current project; on first load reopen the most recent one."""
    if _key("project") not in st.session_state:
        store = _store()
        names = store.list_projects()
        project = store.load(names[0]) if names else None
        if project is None:
            project = ProjectState(name=store.new_name(), script=EXAMPLE_SCRIPT)
            store.save(project)
        st.session_state[_key("project")] = project
    return st.session_state[_key("project")]


def _open_project(name: str) -> None:
    project = _store().load(name)
    if project:
        st.session_state[_key("project")] = project
        _clear_widget_state()


def _save() -> None:
    _store().save(_project())


def _load_settings() -> dict:
    if _key("settings") not in st.session_state:
        settings = dict(DEFAULT_SETTINGS)
        file = _store().root / SETTINGS_FILE
        try:
            settings.update(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        st.session_state[_key("settings")] = settings
    return st.session_state[_key("settings")]


def _save_settings(values: dict) -> None:
    settings = _load_settings()
    if any(settings.get(k) != v for k, v in values.items()):
        settings.update(values)
        try:
            (_store().root / SETTINGS_FILE).write_text(json.dumps(settings, indent=1),
                                                       encoding="utf-8")
        except OSError:
            pass


def _effective_clip(scene_index: int) -> Optional[StockVideoResult]:
    """The clip that will be downloaded: the user's pick, else the best match."""
    project = _project()
    outcome = project.outcomes.get(scene_index)
    if not outcome or not outcome.results:
        return None
    uid = project.selections.get(scene_index)
    return next((r for r in outcome.results if r.uid == uid), outcome.results[0])


def _custom_clip(scene_index: int) -> Optional[Path]:
    path = _project().uploads.get(scene_index)
    return Path(path) if path and Path(path).exists() else None


# ------------------------------------------------------------------ sidebar


def _render_project_bar() -> None:
    store, project = _store(), _project()
    with st.sidebar:
        st.header("📁 Dự án")
        names = store.list_projects()
        if project.name not in names:
            names.insert(0, project.name)
        choice = st.selectbox("Mở dự án", names, index=names.index(project.name),
                              help="Mọi thứ được tự động lưu sau mỗi bước.")
        if choice != project.name:
            _open_project(choice)
            st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("➕ Dự án mới", use_container_width=True):
            new = ProjectState(name=store.new_name(), script="")
            store.save(new)
            st.session_state[_key("project")] = new
            _clear_widget_state()
            st.rerun()
        with c2.popover("✏️ Đổi tên", use_container_width=True):
            new_name = st.text_input("Tên mới", value=project.name)
            if st.button("Lưu tên") and new_name.strip() and new_name != project.name:
                try:
                    project.name = store.rename(project.name, new_name)
                    _save()
                    st.rerun()
                except OSError as e:
                    st.error(str(e))
        if project.updated_at:
            st.caption(f"💾 Đã lưu lúc {project.updated_at.replace('T', ' ')}")


def _render_sidebar(auth: AuthManager) -> dict:
    saved = _load_settings()
    with st.sidebar:
        st.header("Nguồn video")
        status = auth.status()
        labels = {k: cls.name + (" 💎" if cls.is_premium else "")
                  for k, cls in PROVIDER_CLASSES.items()}
        default_providers = [p for p in (saved["providers"] or DEFAULT_PROVIDERS)
                             if p in PROVIDER_CLASSES]
        if saved["providers"] is None:
            default_providers = [p for p in DEFAULT_PROVIDERS if status[p]["configured"]] \
                or DEFAULT_PROVIDERS
        providers = st.multiselect(
            "Tìm trên",
            options=list(PROVIDER_CLASSES),
            default=default_providers,
            format_func=lambda k: labels[k] + ("" if status[k]["configured"] else " ⚠️"),
        )
        for p in providers:
            if not status[p]["configured"]:
                st.warning(f"{labels[p]}: thiếu {', '.join(status[p]['missing'])} trong .env")

        with st.expander("🔑 API key (chỉ cho phiên này)"):
            st.caption("Nên điền vào file `.env`. Giá trị nhập ở đây không được lưu.")
            for env_vars in PROVIDER_ENV_VARS.values():
                for var in env_vars:
                    value = st.text_input(var, type="password", key=_key(f"key_{var}"))
                    if value:
                        auth.set_override(var, value)

        st.header("Tùy chọn tìm kiếm")
        clips_per_scene = st.slider("Số clip hiện mỗi cảnh", 1, 10,
                                    int(saved["clips_per_scene"]),
                                    help="Clip khớp nhất hiện trước; bấm 'Xem thêm' dưới "
                                         "mỗi cảnh để xem các clip tiếp theo.")
        orientations = list(ORIENTATION_LABELS)
        orientation = st.selectbox("Khung hình", orientations,
                                   format_func=ORIENTATION_LABELS.get,
                                   index=orientations.index(saved["orientation"])
                                   if saved["orientation"] in orientations else 0)
        min_duration = st.number_input("Độ dài clip tối thiểu (giây)", 0.0, 60.0,
                                       float(saved["min_duration"]), step=1.0)

        st.header("AI phân tích")
        llm = auth.llm_settings()
        use_llm = st.toggle(
            "Dùng LLM để phân tích / dịch kịch bản",
            value=bool(saved["use_llm"]) and llm.enabled,
            disabled=not llm.enabled,
            help="Cấu hình STOCK_LLM_BACKEND / STOCK_LLM_MODEL / STOCK_LLM_API_KEY trong .env",
        )
        if llm.enabled:
            st.caption(f"{llm.backend} · {llm.model} · {llm.base_url or 'URL mặc định'}")
            if st.button("🔌 Kiểm tra kết nối LLM"):
                _test_llm(llm)
        else:
            st.caption("Chưa cấu hình LLM: chỉ phân tích bằng quy tắc. Có LLM sẽ hiểu "
                       "kịch bản tốt hơn nhiều, nhất là tiếng Việt.")
        ai_rerank = st.toggle(
            "AI chấm điểm qua ảnh thumbnail",
            value=bool(saved["ai_rerank"]) and llm.enabled,
            disabled=not llm.enabled,
            help="Sau khi tìm, một LLM đọc được ảnh xem thumbnail các clip đầu của mỗi cảnh "
                 "và chấm độ phù hợp. Chính xác nhất; tốn token LLM. Đặt "
                 "STOCK_LLM_VISION_MODEL nếu model chính không đọc được ảnh.",
        )
        ai_top_n = st.slider("Số clip AI chấm mỗi cảnh", 3, 12, int(saved["ai_top_n"]),
                             disabled=not ai_rerank)

        st.header("Lưu file")
        project = _project()
        output_dir = st.text_input("Thư mục lưu clip", f"output/stock_clips/{project.name}",
                                   key=_key(f"outdir_{project.name}"))
        wps = st.number_input("Tốc độ đọc (từ / giây)", 1.0, 5.0, float(saved["wps"]),
                              step=0.1, help="Dùng để ước tính thời lượng mỗi cảnh trong "
                                             "manifest.json")
        show_video = st.toggle(
            "Tự phát mọi video xem trước (nặng)", value=bool(saved["show_video"]),
            help="Tải mọi video xem trước cùng lúc, có thể làm treo cửa sổ. "
                 "Nên để tắt và bấm ▶ ở clip muốn xem.",
        )

    _save_settings({
        "providers": providers, "orientation": orientation, "min_duration": min_duration,
        "clips_per_scene": clips_per_scene, "use_llm": use_llm, "ai_rerank": ai_rerank,
        "ai_top_n": ai_top_n, "wps": wps, "show_video": show_video,
    })
    return {
        "providers": providers,
        "orientation": None if orientation == "any" else orientation,
        "min_duration": min_duration,
        "clips_per_scene": clips_per_scene,
        "use_llm": use_llm,
        "output_dir": output_dir,
        "wps": wps,
        "show_video": show_video,
        "ai_rerank": ai_rerank and llm.enabled,
        "ai_top_n": ai_top_n,
    }


def _test_llm(llm) -> None:
    try:
        with st.spinner("Đang hỏi LLM…"):
            reply = check_connection(llm)
        st.success(f"LLM trả lời: {reply[:80] or '(trống)'}")
    except Exception as e:
        hint = ""
        if "connection" in str(e).lower():
            hint = (" — LLM server (vd. 9Router) đã bật chưa, STOCK_LLM_BASE_URL đúng chưa?")
        elif "401" in str(e) or "auth" in str(e).lower():
            hint = " — kiểm tra STOCK_LLM_API_KEY"
        elif "404" in str(e) or "model" in str(e).lower():
            hint = " — kiểm tra STOCK_LLM_MODEL có đúng tên model / combo không"
        st.error(f"Lỗi LLM: {e}{hint}")


# ------------------------------------------------------------------ search


def _engine(auth: AuthManager, opts: dict) -> StockSearchEngine:
    return StockSearchEngine(auth, providers=opts["providers"], orientation=opts["orientation"],
                             min_duration=opts["min_duration"], words_per_second=opts["wps"],
                             cache_dir=Path("output") / ".stock_cache")


async def _search(auth, opts, scenes: list[SceneAnalysis], overrides: dict[int, str],
                  on_scene_done=None):
    async with _engine(auth, opts) as engine:
        outcomes = await engine.search_scenes(scenes, per_page=FETCH_PER_QUERY,
                                              overrides=overrides, on_scene_done=on_scene_done)
        return outcomes, engine.skipped


def _search_and_store(auth, opts, scenes: list[SceneAnalysis]) -> None:
    project = _project()
    overrides = {s.index: q for s in scenes
                 if (q := project.queries.get(s.index, "").strip()) and q != s.query}
    bar = st.progress(0.0, text=f"Đang tìm {len(scenes)} cảnh…")

    def on_scene_done(outcome: SearchOutcome, finished: int, total: int):
        bar.progress(finished / total,
                     text=f"Đã tìm {finished}/{total} · cảnh {outcome.scene.index:02d}: "
                          f"{len(outcome.results)} clip ứng viên")

    try:
        outcomes, skipped = _run(_search(auth, opts, scenes, overrides, on_scene_done))
    except Exception as e:
        bar.empty()
        st.error(str(e))
        return
    bar.empty()
    for name, reason in skipped.items():
        st.warning(f"Bỏ qua {name}: {reason}")

    # Save the text-ranked results right away, before the slower AI step
    for o in outcomes:
        project.outcomes[o.scene.index] = o
        # A new search invalidates an old manual pick that is no longer listed
        if project.selections.get(o.scene.index) not in {r.uid for r in o.results}:
            project.selections.pop(o.scene.index, None)
    _save()

    if opts["ai_rerank"]:
        bar = st.progress(0.0, text="AI đang chấm thumbnail…")
        failures: list[str] = []

        def on_rated(outcome: SearchOutcome, finished: int, total: int, error: str):
            if error:
                failures.append(f"cảnh {outcome.scene.index:02d}: {error}")
            bar.progress(finished / max(1, total), text=f"AI đã chấm {finished}/{total} cảnh")

        try:
            _run(rerank_outcomes(_auth().llm_settings(), outcomes, top_n=opts["ai_top_n"],
                                 on_done=on_rated))
        except Exception as e:
            failures.append(str(e))
        bar.empty()
        if failures:
            st.warning("AI chấm ảnh lỗi ở một số cảnh (vẫn giữ điểm theo từ khóa). Model có "
                       "đọc được ảnh không?\n\n" + "\n".join(failures[:5]))
        _save()


# ------------------------------------------------------------------ scenes


def _scene_context_line(scene: SceneAnalysis) -> str:
    def mark(dim: str, value: str) -> str:
        return f"{value} ↩" if dim in scene.inherited else value

    parts = [
        ("👤", mark("subject", ", ".join(scene.subjects))),
        ("🏃", ", ".join(scene.actions)),
        ("📍", mark("setting", ", ".join(scene.setting))),
        ("🕒", mark("time_of_day", scene.time_of_day)),
        ("🌦️", mark("weather", scene.weather)),
        ("🍂", mark("season", scene.season)),
        ("🎭", ", ".join(scene.mood)),
    ]
    text = " · ".join(f"{icon} {value}" for icon, value in parts if value.strip(" ↩"))
    return f"{text or 'chưa nhận ra bối cảnh'} · phân tích bằng {scene.source}" + \
        (" · ↩ = kế thừa từ cảnh trước" if scene.inherited else "")


def _on_query_change(index: int) -> None:
    project = _project()
    project.queries[index] = st.session_state.get(_key(f"q_{index}"), "")
    _save()


def _on_include_change(index: int) -> None:
    project = _project()
    included = st.session_state.get(_key(f"inc_{index}"), True)
    project.excluded = [i for i in project.excluded if i != index]
    if not included:
        project.excluded.append(index)
    _save()


def _pick_clip(index: int, uid: str) -> None:
    project = _project()
    project.selections[index] = uid
    if index in project.excluded:  # picking a clip means you want this scene
        project.excluded.remove(index)
        st.session_state.pop(_key(f"inc_{index}"), None)
    _save()


def _set_all_included(included: bool) -> None:
    project = _project()
    project.excluded = [] if included else [s.index for s in project.scenes]
    for s in project.scenes:
        st.session_state.pop(_key(f"inc_{s.index}"), None)
    _save()


def _render_clip(scene: SceneAnalysis, r: StockVideoResult, rank: int, opts: dict,
                 chosen: bool) -> None:
    play_key = _key(f"play_{scene.index}_{r.uid}")
    if opts["show_video"] or st.session_state.get(play_key):
        st.video(r.preview_url, muted=True, loop=True, autoplay=True)
    else:
        if r.thumbnail_url.startswith("http"):
            st.image(r.thumbnail_url, width="stretch")
        else:
            st.caption("(không có ảnh)")
        st.button("▶ Xem thử", key=f"{play_key}_btn",
                  on_click=lambda k=play_key: st.session_state.update({k: True}))
    if chosen:
        st.button("✅ Clip sẽ tải", key=_key(f"sel_{scene.index}_{r.uid}"), disabled=True,
                  use_container_width=True)
    else:
        st.button("Chọn clip này", key=_key(f"sel_{scene.index}_{r.uid}"),
                  use_container_width=True, on_click=_pick_clip, args=(scene.index, r.uid))
    badge = "💎 " if r.is_premium else ""
    ai = f" · 🤖 {r.ai_score:.0f}/10" if r.ai_score is not None else ""
    lines = [f"**#{rank} · ⭐ {r.score:.0f}**{ai} · {badge}{r.provider} · "
             f"{r.duration:.0f}s · {r.width}x{r.height}"]
    if r.matched_terms:
        lines.append("✅ khớp: " + ", ".join(r.matched_terms))
    if r.conflicts:
        lines.append("⚠️ lệch: " + ", ".join(r.conflicts))
    if r.ai_reason:
        lines.append(f"🤖 {r.ai_reason}")
    lines.append(r.title[:70])
    st.caption("\n\n".join(lines))


def _render_scene(scene: SceneAnalysis, opts: dict, auth) -> None:
    project = _project()
    outcome = project.outcomes.get(scene.index)
    with st.container(border=True):
        head, action = st.columns([5, 1])
        head.checkbox(
            f"**Cảnh {scene.index:02d}** — {scene.sentence}",
            value=scene.index not in project.excluded,
            key=_key(f"inc_{scene.index}"),
            on_change=_on_include_change, args=(scene.index,),
            help="Tích để đưa cảnh này vào danh sách tải",
        )
        head.caption(_scene_context_line(scene))
        if scene.visual_description:
            head.caption(f"🎬 {scene.visual_description}")
        if scene.index in project.downloads:
            head.caption(f"💾 Đã tải: `{Path(project.downloads[scene.index]).name}`")
        st.text_input("Từ khóa tìm (sửa rồi bấm Tìm lại)",
                      value=project.queries.get(scene.index, scene.query),
                      key=_key(f"q_{scene.index}"),
                      on_change=_on_query_change, args=(scene.index,))
        if action.button("🔄 Tìm lại", key=_key(f"re_{scene.index}")):
            _search_and_store(auth, opts, [scene])
            st.rerun()

        if _custom_clip(scene.index) is None:
            if outcome is None:
                st.caption("Chưa tìm.")
            else:
                _render_results(scene, outcome, opts)
        _render_upload(scene)


def _render_results(scene: SceneAnalysis, outcome: SearchOutcome, opts: dict) -> None:
    st.caption("🔎 Đã tìm với: " + " · ".join(f"`{q}`" for q in outcome.tried_queries))
    for provider, err in outcome.errors.items():
        st.warning(f"{provider}: {err}")
    if not outcome.results:
        st.error("Không tìm thấy clip — sửa từ khóa rồi Tìm lại, hoặc tải clip của bạn lên.")
        return

    more_key = _key(f"more_{scene.index}")
    shown_n = opts["clips_per_scene"] + st.session_state.get(more_key, 0)
    chosen = _effective_clip(scene.index)
    shown = outcome.results[:shown_n]
    if chosen and chosen not in shown:
        shown.append(chosen)  # picked earlier from "Xem thêm"
    rank = {r.uid: i + 1 for i, r in enumerate(outcome.results)}
    cols = st.columns(GRID_COLUMNS)
    for i, r in enumerate(shown):
        with cols[i % GRID_COLUMNS]:
            _render_clip(scene, r, rank[r.uid], opts, chosen is not None and r.uid == chosen.uid)
    if len(outcome.results) > shown_n:
        st.button(f"➕ Xem thêm ({len(outcome.results) - shown_n} clip nữa)",
                  key=f"{more_key}_btn",
                  on_click=lambda: st.session_state.update(
                      {more_key: st.session_state.get(more_key, 0) + opts["clips_per_scene"]}))


def _render_upload(scene: SceneAnalysis) -> None:
    project = _project()
    existing = _custom_clip(scene.index)
    if existing:
        c1, c2 = st.columns([5, 1])
        c1.info(f"📎 Dùng clip của bạn: `{existing.name}` (thay cho clip stock)")
        if c2.button("✖ Bỏ", key=_key(f"rmup_{scene.index}")):
            project.uploads.pop(scene.index, None)
            _save()
            st.rerun()
        return
    upload = st.file_uploader("…hoặc tải clip của bạn lên", type=["mp4", "mov", "webm", "mkv"],
                              key=_key(f"up_{scene.index}"))
    if upload is not None:
        path = _store().uploads_dir(project.name) / \
            f"scene_{scene.index:02d}{Path(upload.name).suffix.lower()}"
        path.write_bytes(upload.getbuffer())
        project.uploads[scene.index] = str(path)
        _save()
        st.rerun()


# ------------------------------------------------------------------ download


async def _download(auth, opts, items, customs, scenes, on_progress):
    async with _engine(auth, opts) as engine:
        downloader = Downloader(engine, Path(opts["output_dir"]), words_per_second=opts["wps"])
        results = await downloader.download(items, on_progress=on_progress, custom_clips=customs)
        manifest = downloader.write_manifest(results, all_scenes=scenes)
        return results, manifest


def _download_plan(indices: list[int]) -> tuple[list[DownloadItem], list[CustomClip], list[int]]:
    """Items to fetch for these scenes, custom clips to copy, scenes with nothing to get."""
    project = _project()
    by_index = {s.index: s for s in project.scenes}
    items, customs, missing = [], [], []
    for i in indices:
        scene = by_index[i]
        custom = _custom_clip(i)
        if custom:
            customs.append(CustomClip(scene, custom))
            continue
        clip = _effective_clip(i)
        if clip:
            keyword = project.queries.get(i) or scene.query
            items.append(DownloadItem(scene, clip, keyword=keyword))
        else:
            missing.append(i)
    return items, customs, missing


def _open_folder(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(folder.resolve()))  # noqa: S606 - local desktop app
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except Exception as e:
        st.warning(f"Không mở được thư mục: {e}")


def _run_download(auth, opts, indices: list[int], label: str, position: str) -> None:
    project = _project()
    items, customs, missing = _download_plan(indices)
    if not (items or customs):
        st.warning("Không có cảnh nào có clip để tải. Hãy bấm 'Tìm tất cả các cảnh' trước.")
        return
    # A different clip was picked since the last download: replace the old file
    for item in items:
        i = item.scene.index
        old = project.downloads.get(i)
        if old and project.download_uids.get(i) != item.video.uid:
            Path(old).unlink(missing_ok=True)
            project.downloads.pop(i, None)
    bar = st.progress(0.0, text=f"{label}: chuẩn bị…")
    per_scene: dict[int, float] = {}

    def on_progress(scene_index: int, done: int, total: int):
        per_scene[scene_index] = done / total if total else 0.5
        overall = sum(per_scene.values()) / max(1, len(items))
        bar.progress(min(1.0, overall),
                     text=f"{label}: cảnh {scene_index:02d} · {done / 1e6:.1f} MB")

    try:
        results, manifest = _run(_download(auth, opts, items, customs, project.scenes,
                                           on_progress))
    except Exception as e:
        bar.empty()
        st.error(f"Tải thất bại: {e}")
        return
    bar.empty()
    for r in results:
        if r.ok:
            project.downloads[r.scene.index] = str(r.path)
            project.download_uids[r.scene.index] = r.video.uid if r.video else "custom"
    _save()
    st.session_state[_key("report")] = {
        "ok": sum(r.ok for r in results),
        "total": len(results),
        "errors": [f"Cảnh {r.scene.index:02d}: {r.error}" for r in results if not r.ok],
        "missing": missing,
        "folder": opts["output_dir"],
        "manifest": str(manifest),
        "position": position,
    }
    st.rerun()


def _render_download_bar(auth, opts, position: str) -> None:
    project = _project()
    scenes = project.scenes
    ready = [s.index for s in scenes
             if _custom_clip(s.index) or _effective_clip(s.index)]
    chosen = [i for i in ready if i not in project.excluded]
    searched = any(project.outcomes.values()) or project.uploads

    with st.container(border=True):
        st.markdown(f"**⬇️ Tải clip** · {len(chosen)}/{len(scenes)} cảnh được chọn · "
                    f"{len(project.downloads)} cảnh đã tải · lưu vào `{opts['output_dir']}`")
        if searched and len(ready) < len(scenes):
            st.caption(f"{len(scenes) - len(ready)} cảnh chưa có clip (chưa tìm hoặc không "
                       "tìm thấy) sẽ bị bỏ qua.")
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1.4, 1.4, 1])
        c1.button("☑ Chọn tất cả", key=_key(f"all_{position}"), use_container_width=True,
                  on_click=_set_all_included, args=(True,))
        c2.button("☐ Bỏ chọn tất cả", key=_key(f"none_{position}"),
                  use_container_width=True, on_click=_set_all_included, args=(False,))
        if c3.button(f"⬇️ Tải tất cả cảnh ({len(ready)})", key=_key(f"dlall_{position}"),
                     use_container_width=True, disabled=not ready):
            _run_download(auth, opts, ready, "Tải tất cả", position)
        if c4.button(f"⬇️ Tải cảnh đã chọn ({len(chosen)})", key=_key(f"dlsel_{position}"),
                     type="primary", use_container_width=True, disabled=not chosen):
            _run_download(auth, opts, chosen, "Tải cảnh đã chọn", position)
        if c5.button("📂 Mở thư mục", key=_key(f"open_{position}"), use_container_width=True):
            _open_folder(Path(opts["output_dir"]))

        premium = sum(1 for i in chosen
                      if (c := _effective_clip(i)) and c.is_premium and not _custom_clip(i))
        if premium:
            st.warning(f"{premium} clip trả phí sẽ được mua bản quyền và trừ vào gói của bạn.")

        report = st.session_state.get(_key("report"))
        if report and report.get("position") == position:
            if report["ok"]:
                st.success(f"Đã lưu {report['ok']}/{report['total']} clip vào "
                           f"`{report['folder']}` (kèm manifest.json). Cảnh đã tải đúng clip này "
                           "trước đó thì không tải lại.")
            for err in report["errors"]:
                st.error(err)
            if report["missing"]:
                st.info("Bỏ qua (chưa có clip): cảnh " +
                        ", ".join(f"{i:02d}" for i in report["missing"]))


# ------------------------------------------------------------------ page


def render() -> None:
    project = _project()
    auth = _auth()
    _render_project_bar()
    opts = _render_sidebar(auth)

    st.title("🎞️ Tìm video stock theo kịch bản")
    st.caption(f"Dự án **{project.name}** · dán kịch bản → phân tích → tìm clip → chọn → tải. "
               "Mọi thứ được lưu tự động.")

    script = st.text_area("Kịch bản", value=project.script, height=180,
                          key=_key("script_box"),
                          help="Mỗi câu hoặc mỗi dòng là một cảnh. Hỗ trợ tiếng Việt "
                               "(tốt nhất khi có LLM).")
    if script != project.script:
        project.script = script
        _save()

    c1, c2 = st.columns(2)
    if c1.button("1️⃣ Phân tích kịch bản", use_container_width=True,
                 disabled=not script.strip()):
        if project.outcomes and not st.session_state.get(_key("confirm_reanalyze")):
            st.session_state[_key("confirm_reanalyze")] = True
            st.warning("Phân tích lại sẽ xóa kết quả tìm và lựa chọn của dự án này. "
                       "Bấm **Phân tích kịch bản** lần nữa để xác nhận.")
        else:
            st.session_state.pop(_key("confirm_reanalyze"), None)
            try:
                with st.spinner("Đang phân tích kịch bản…"):
                    parser = ScriptParser(llm=auth.llm_settings())
                    scenes = parser.parse(script, use_llm=opts["use_llm"] or False)
            except Exception as e:
                st.error(f"Phân tích thất bại: {e}")
                scenes = []
            project.scenes = scenes
            project.outcomes, project.selections, project.queries = {}, {}, {}
            project.excluded = []
            _save()
            _clear_widget_state()
            st.rerun()

    scenes = project.scenes
    if c2.button("2️⃣ Tìm tất cả các cảnh", use_container_width=True, disabled=not scenes):
        _search_and_store(auth, opts, scenes)

    if not scenes:
        st.info("Dán kịch bản rồi bấm 'Phân tích kịch bản' để bắt đầu.")
        return

    _render_download_bar(auth, opts, "top")
    for scene in scenes:
        _render_scene(scene, opts, auth)
    _render_download_bar(auth, opts, "bottom")


if __name__ == "__main__":
    st.set_page_config(page_title="Stock Matcher", page_icon="🎞️", layout="wide")
    render()
