"""
Module D (UI) - Streamlit dashboard for script-to-stock matching (Vietnamese UI).

Desktop:     python -m pixelle_video.stock_matcher.desktop   (own window)
Standalone:  streamlit run pixelle_video/stock_matcher/app.py
Embedded:    web/pages/3_🎞️_Stock_Matcher.py calls render()

The page has three steps: 📝 script, 🎬 choose clips, ⬇️ download. All work lives
in a project saved on disk (project_store.py) after every change.
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

import pandas as pd
import streamlit as st

from pixelle_video.stock_matcher.auth_manager import PROVIDER_ENV_VARS, AuthManager
from pixelle_video.stock_matcher.downloader import NAME_STYLES, CustomClip, Downloader
from pixelle_video.stock_matcher.llm_extractor import check_connection
from pixelle_video.stock_matcher.models import (
    DownloadItem,
    SceneAnalysis,
    SearchOutcome,
    StockVideoResult,
)
from pixelle_video.stock_matcher.nlp_parser import ScriptParser, script_from_file
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
VIEWS = {"script": "📝 1. Kịch bản", "clips": "🎬 2. Chọn clip", "download": "⬇️ 3. Tải về"}
QUALITIES = {"720p": 1280, "1080p": 1920, "4K": 3840}
QUALITY_LABELS = {"720p": "720p · nhẹ", "1080p": "1080p · khuyên dùng",
                  "4K": "4K · nếu nguồn có"}
DL_MODES = {"chosen": "Chỉ clip đã chọn (1 clip / cảnh)",
            "alternates": "Clip đã chọn + clip dự phòng (để chọn khi dựng)"}
ORIENTATION_LABELS = {"any": "Bất kỳ", "landscape": "Ngang (16:9)",
                      "portrait": "Dọc (9:16)", "square": "Vuông"}
DEFAULT_SETTINGS = {
    "providers": None,
    "orientation": "any",
    "min_duration": 0.0,
    "clips_per_scene": 3,
    "avoid_dupes": True,
    "use_llm": True,
    "ai_rerank": False,
    "ai_top_n": 6,
    "wps": 2.5,
    "show_video": False,
    "quality": "1080p",
    "dl_mode": "chosen",
    "alt_count": 2,
    "name_style": "keyword",
    "overwrite": False,
    "credits": True,
    "parallel": 3,
    "output_dirs": {},
}

CSS = """
<style>
.block-container {padding-top: 3.2rem; max-width: 1400px;}
.sm-hero {background: linear-gradient(135deg, #21253d 0%, #3d4275 100%);
  color: #fff; border-radius: 16px; padding: 18px 24px; margin-bottom: 14px;}
.sm-hero h1 {font-size: 1.55rem; margin: 0; padding: 0; color: #fff;}
.sm-hero p {margin: 4px 0 0; opacity: .85; font-size: .92rem;}
.sm-steps {display: flex; gap: 6px; flex-wrap: wrap; margin-top: 12px;}
.sm-step {padding: 4px 12px; border-radius: 999px; font-size: .8rem;
  background: rgba(255,255,255,.12); color: #e8e9f3;}
.sm-step.done {background: #2f9e62; color: #fff;}
.sm-step.active {background: #ff6f61; color: #fff; font-weight: 600;}
.sm-badge {display: inline-block; padding: 1px 9px; border-radius: 999px;
  font-size: .75rem; font-weight: 600; margin-left: 4px;}
.sm-ok {background: #d9f2e3; color: #16683a;}
.sm-ready {background: #e3ecff; color: #2448a8;}
.sm-wait {background: #eceef3; color: #5a5f73;}
.sm-bad {background: #fde2df; color: #a8321f;}
div[data-testid="stMetric"] {background: #f6f7fb; border-radius: 12px;
  padding: 8px 14px; border: 1px solid #eceef5;}
div[data-testid="stMetricValue"] {font-size: 1.5rem;}
/* step navigation: horizontal radio styled as tabs */
div[role="radiogroup"] > label {background: #f1f2f7; border-radius: 10px;
  padding: 6px 14px !important; border: 1px solid #e3e5ee;}
div[role="radiogroup"] > label:has(input:checked) {background: #ff6f61; color: #fff;
  border-color: #ff6f61;}
div[role="radiogroup"] > label:has(input:checked) p {color: #fff; font-weight: 600;}
</style>
"""


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
                                              "script_box", "report", "table"))
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
        _go("clips" if project.scenes else "script")


def _save() -> None:
    _store().save(_project())


def _settings() -> dict:
    if _key("settings") not in st.session_state:
        settings = json.loads(json.dumps(DEFAULT_SETTINGS))
        try:
            file = _store().root / SETTINGS_FILE
            settings.update(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        st.session_state[_key("settings")] = settings
    return st.session_state[_key("settings")]


def _update_settings(values: dict) -> None:
    settings = _settings()
    if any(settings.get(k) != v for k, v in values.items()):
        settings.update(values)
        try:
            (_store().root / SETTINGS_FILE).write_text(
                json.dumps(settings, indent=1, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass


def _go(view: str) -> None:
    """Switch step on the next run (the nav widget may already be drawn)."""
    st.session_state[_key("next_view")] = view


def _output_dir() -> str:
    project = _project()
    return _settings()["output_dirs"].get(project.name, f"output/stock_clips/{project.name}")


# ------------------------------------------------------------------ clip choice


def _effective_map() -> dict[int, StockVideoResult]:
    """
    Clip used for every scene: the user's pick, else the best match. With
    "avoid duplicates" on, an automatic pick skips clips already used by
    another scene.
    """
    project = _project()
    avoid = _settings()["avoid_dupes"]
    chosen: dict[int, StockVideoResult] = {}
    used: set[str] = set()
    for scene in project.scenes:  # manual picks first, they always win
        outcome = project.outcomes.get(scene.index)
        uid = project.selections.get(scene.index)
        if outcome and uid:
            clip = next((r for r in outcome.results if r.uid == uid), None)
            if clip:
                chosen[scene.index] = clip
                used.add(clip.uid)
    for scene in project.scenes:
        outcome = project.outcomes.get(scene.index)
        if scene.index in chosen or not outcome or not outcome.results:
            continue
        pool = [r for r in outcome.results if r.uid not in used] if avoid else []
        clip = pool[0] if pool else outcome.results[0]
        chosen[scene.index] = clip
        used.add(clip.uid)
    return chosen


def _custom_clip(scene_index: int) -> Optional[Path]:
    path = _project().uploads.get(scene_index)
    return Path(path) if path and Path(path).exists() else None


def _scene_status(scene: SceneAnalysis, clips: dict[int, StockVideoResult]) -> tuple[str, str]:
    project = _project()
    if scene.index in project.downloads and Path(project.downloads[scene.index]).exists():
        return "sm-ok", "Đã tải"
    if _custom_clip(scene.index) or scene.index in clips:
        return "sm-ready", "Sẵn sàng tải"
    if scene.index in project.outcomes:
        return "sm-bad", "Không có clip"
    return "sm-wait", "Chưa tìm"


# ------------------------------------------------------------------ sidebar


def _render_project_bar() -> None:
    store, project = _store(), _project()
    with st.sidebar:
        st.subheader("📁 Dự án")
        names = store.list_projects()
        if project.name not in names:
            names.insert(0, project.name)
        choice = st.selectbox("Mở dự án", names, index=names.index(project.name),
                              label_visibility="collapsed",
                              help="Mọi thứ được tự động lưu sau mỗi bước.")
        if choice != project.name:
            _open_project(choice)
            st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("➕ Dự án mới", width="stretch"):
            new = ProjectState(name=store.new_name(), script="")
            store.save(new)
            st.session_state[_key("project")] = new
            _clear_widget_state()
            _go("script")
            st.rerun()
        with c2.popover("✏️ Đổi tên", width="stretch"):
            new_name = st.text_input("Tên mới", value=project.name)
            if st.button("Lưu tên") and new_name.strip() and new_name != project.name:
                try:
                    old = project.name
                    project.name = store.rename(old, new_name)
                    dirs = dict(_settings()["output_dirs"])
                    if old in dirs:
                        dirs[project.name] = dirs.pop(old)
                        _update_settings({"output_dirs": dirs})
                    _save()
                    st.rerun()
                except OSError as e:
                    st.error(str(e))
        if project.updated_at:
            st.caption(f"💾 Tự lưu lúc {project.updated_at.replace('T', ' ')}")


def _render_sidebar(auth: AuthManager) -> dict:
    saved = _settings()
    with st.sidebar:
        st.divider()
        st.subheader("🔎 Tìm kiếm")
        status = auth.status()
        labels = {k: cls.name + (" 💎" if cls.is_premium else "")
                  for k, cls in PROVIDER_CLASSES.items()}
        if saved["providers"] is None:
            default_providers = [p for p in DEFAULT_PROVIDERS if status[p]["configured"]] \
                or DEFAULT_PROVIDERS
        else:
            default_providers = [p for p in saved["providers"] if p in PROVIDER_CLASSES]
        providers = st.multiselect(
            "Nguồn video",
            options=list(PROVIDER_CLASSES),
            default=default_providers,
            format_func=lambda k: labels[k] + ("" if status[k]["configured"] else " ⚠️"),
        )
        for p in providers:
            if not status[p]["configured"]:
                st.warning(f"{labels[p]}: thiếu {', '.join(status[p]['missing'])} trong .env")
        clips_per_scene = st.slider("Số clip hiện mỗi cảnh", 1, 10,
                                    int(saved["clips_per_scene"]),
                                    help="Clip khớp nhất hiện trước; 'Xem thêm' để xem tiếp.")
        orientations = list(ORIENTATION_LABELS)
        orientation = st.selectbox("Khung hình", orientations,
                                   format_func=ORIENTATION_LABELS.get,
                                   index=orientations.index(saved["orientation"])
                                   if saved["orientation"] in orientations else 0)
        min_duration = st.number_input("Độ dài clip tối thiểu (giây)", 0.0, 60.0,
                                       float(saved["min_duration"]), step=1.0)
        avoid_dupes = st.toggle("Không dùng trùng clip giữa các cảnh",
                                value=bool(saved["avoid_dupes"]),
                                help="Khi tự chọn clip, bỏ qua clip đã được cảnh khác dùng.")
        show_video = st.toggle(
            "Tự phát mọi video xem trước (nặng)", value=bool(saved["show_video"]),
            help="Tải mọi video xem trước cùng lúc, có thể làm chậm. Nên để tắt và "
                 "bấm ▶ ở clip muốn xem.")

        st.divider()
        st.subheader("🤖 AI")
        llm = auth.llm_settings()
        use_llm = st.toggle(
            "Dùng LLM phân tích / dịch kịch bản",
            value=bool(saved["use_llm"]) and llm.enabled,
            disabled=not llm.enabled,
            help="Cấu hình STOCK_LLM_BACKEND / STOCK_LLM_MODEL / STOCK_LLM_API_KEY trong .env",
        )
        ai_rerank = st.toggle(
            "AI chấm điểm qua ảnh thumbnail",
            value=bool(saved["ai_rerank"]) and llm.enabled,
            disabled=not llm.enabled,
            help="Một LLM đọc được ảnh xem thumbnail các clip đầu của mỗi cảnh và chấm độ "
                 "phù hợp. Chính xác nhất; tốn token. Đặt STOCK_LLM_VISION_MODEL nếu "
                 "model chính không đọc được ảnh.",
        )
        ai_top_n = st.slider("Số clip AI chấm mỗi cảnh", 3, 12, int(saved["ai_top_n"]),
                             disabled=not ai_rerank)
        if llm.enabled:
            st.caption(f"{llm.backend} · {llm.model} · {llm.base_url or 'URL mặc định'}")
            if st.button("🔌 Kiểm tra kết nối LLM", width="stretch"):
                _test_llm(llm)
        else:
            st.caption("Chưa cấu hình LLM: chỉ phân tích bằng quy tắc. Có LLM sẽ hiểu "
                       "kịch bản tốt hơn nhiều, nhất là tiếng Việt.")

        with st.expander("🔑 API key tạm thời"):
            st.caption("Nên điền vào file `.env`. Giá trị nhập ở đây không được lưu.")
            for env_vars in PROVIDER_ENV_VARS.values():
                for var in env_vars:
                    value = st.text_input(var, type="password", key=_key(f"key_{var}"))
                    if value:
                        auth.set_override(var, value)

    _update_settings({
        "providers": providers, "orientation": orientation, "min_duration": min_duration,
        "clips_per_scene": clips_per_scene, "avoid_dupes": avoid_dupes,
        "use_llm": use_llm, "ai_rerank": ai_rerank, "ai_top_n": ai_top_n,
        "show_video": show_video,
    })
    return {
        "providers": providers,
        "orientation": None if orientation == "any" else orientation,
        "min_duration": min_duration,
        "clips_per_scene": clips_per_scene,
        "use_llm": use_llm,
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
            hint = " — LLM server (vd. 9Router) đã bật chưa, STOCK_LLM_BASE_URL đúng chưa?"
        elif "401" in str(e) or "auth" in str(e).lower():
            hint = " — kiểm tra STOCK_LLM_API_KEY"
        elif "404" in str(e) or "model" in str(e).lower():
            hint = " — kiểm tra STOCK_LLM_MODEL có đúng tên model / combo không"
        st.error(f"Lỗi LLM: {e}{hint}")


# ------------------------------------------------------------------ header


def _render_header() -> None:
    project = _project()
    clips = _effective_map()
    scenes = project.scenes
    steps = [
        ("Kịch bản", bool(project.script.strip())),
        ("Phân tích", bool(scenes)),
        ("Tìm clip", bool(project.outcomes)),
        ("Chọn clip", bool(clips)),
        ("Tải về", bool(project.downloads)),
    ]
    first_open = next((i for i, (_, done) in enumerate(steps) if not done), len(steps))
    chips = "".join(
        f'<span class="sm-step {"done" if done else "active" if i == first_open else ""}">'
        f'{"✓" if done else i + 1} {label}</span>'
        for i, (label, done) in enumerate(steps)
    )
    st.markdown(
        f'<div class="sm-hero"><h1>🎞️ Tìm video stock theo kịch bản</h1>'
        f'<p>Dự án <b>{project.name}</b> · mọi thao tác được lưu tự động</p>'
        f'<div class="sm-steps">{chips}</div></div>',
        unsafe_allow_html=True,
    )
    if scenes:
        ready = sum(1 for s in scenes if s.index in clips or _custom_clip(s.index))
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Số cảnh", len(scenes))
        m2.metric("Đã tìm", f"{len(project.outcomes)}/{len(scenes)}")
        m3.metric("Sẵn sàng tải", f"{ready}/{len(scenes)}")
        m4.metric("Đã tải", f"{len(project.downloads)}/{len(scenes)}")


def _render_nav() -> str:
    view_key = _key("view")
    if _key("next_view") in st.session_state:
        st.session_state[view_key] = st.session_state.pop(_key("next_view"))
    if view_key not in st.session_state:
        st.session_state[view_key] = "clips" if _project().scenes else "script"
    view = st.radio("Bước", list(VIEWS), format_func=VIEWS.get, key=view_key,
                    horizontal=True, label_visibility="collapsed")
    return view


# ------------------------------------------------------------------ search


def _engine(auth: AuthManager, opts: dict) -> StockSearchEngine:
    return StockSearchEngine(auth, providers=opts["providers"], orientation=opts["orientation"],
                             min_duration=opts["min_duration"], words_per_second=_settings()["wps"],
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

    for o in outcomes:
        project.outcomes[o.scene.index] = o
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


def _analyze(auth, opts, script: str) -> bool:
    project = _project()
    try:
        with st.spinner("Đang phân tích kịch bản…"):
            parser = ScriptParser(llm=auth.llm_settings())
            scenes = parser.parse(script, use_llm=opts["use_llm"] or False)
    except Exception as e:
        st.error(f"Phân tích thất bại: {e}")
        return False
    project.scenes = scenes
    project.outcomes, project.selections, project.queries = {}, {}, {}
    project.excluded = []
    _save()
    _clear_widget_state()
    return bool(scenes)


# ------------------------------------------------------------------ view 1: script


def _render_script_view(auth, opts) -> None:
    project = _project()
    with st.container(border=True):
        st.markdown("##### Dán kịch bản hoặc nhập từ file")
        upload = st.file_uploader("Nhập từ file .txt / .srt / .vtt / .md",
                                  type=["txt", "srt", "vtt", "md"], key=_key("script_file"))
        if upload is not None and st.session_state.get(_key("imported")) != upload.file_id:
            st.session_state[_key("imported")] = upload.file_id
            project.script = script_from_file(upload.name, upload.getvalue())
            _save()
            st.session_state.pop(_key("script_box"), None)
            st.rerun()
        script = st.text_area("Kịch bản", value=project.script, height=240,
                              key=_key("script_box"), label_visibility="collapsed",
                              placeholder="Mỗi câu hoặc mỗi dòng là một cảnh…")
        if script != project.script:
            project.script = script
            _save()
        lines = [ln for ln in script.splitlines() if ln.strip()]
        st.caption(f"{len(script.split())} từ · {len(lines)} dòng · hỗ trợ tiếng Việt "
                   "(tốt nhất khi có LLM)")

        c1, c2 = st.columns(2)
        confirm_needed = bool(project.outcomes)
        go_all = c1.button("⚡ Phân tích + Tìm clip", type="primary", width="stretch",
                           disabled=not script.strip())
        go_parse = c2.button("Chỉ phân tích", width="stretch",
                             disabled=not script.strip())
        if go_all or go_parse:
            if confirm_needed and not st.session_state.get(_key("confirm_reanalyze")):
                st.session_state[_key("confirm_reanalyze")] = True
                st.warning("Phân tích lại sẽ xóa kết quả tìm và lựa chọn hiện tại của dự án. "
                           "Bấm lại lần nữa để xác nhận.")
            else:
                st.session_state.pop(_key("confirm_reanalyze"), None)
                if _analyze(auth, opts, script):
                    if go_all:
                        _search_and_store(auth, opts, _project().scenes)
                    _go("clips")
                    st.rerun()

    if project.scenes:
        st.markdown("##### Kết quả phân tích")
        rows = [{
            "Cảnh": f"{s.index:02d}",
            "Câu": s.sentence,
            "Từ khóa tìm": project.queries.get(s.index) or s.query,
            "Bối cảnh": " · ".join(x for x in [", ".join(s.setting), s.time_of_day,
                                               s.weather, s.season] if x),
        } for s in project.scenes]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ------------------------------------------------------------------ view 2: clips


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
    return f"{text or 'chưa nhận ra bối cảnh'}" + \
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
    st.session_state[_key("table_ver")] = st.session_state.get(_key("table_ver"), 0) + 1
    _save()


def _render_clip(scene: SceneAnalysis, r: StockVideoResult, rank: int, opts: dict,
                 chosen: bool) -> None:
    with st.container(border=True):
        play_key = _key(f"play_{scene.index}_{r.uid}")
        if opts["show_video"] or st.session_state.get(play_key):
            st.video(r.preview_url, muted=True, loop=True, autoplay=True)
        elif r.thumbnail_url.startswith("http"):
            st.image(r.thumbnail_url, width="stretch")
        else:
            st.caption("(không có ảnh)")
        ai = f" · 🤖 {r.ai_score:.0f}/10" if r.ai_score is not None else ""
        badge = " 💎" if r.is_premium else ""
        st.markdown(f"**#{rank} · ⭐ {r.score:.0f}**{ai} · {r.provider}{badge} · "
                    f"{r.duration:.0f}s · {r.height or '?'}p")
        details = []
        if r.matched_terms:
            details.append("✅ " + ", ".join(r.matched_terms))
        if r.conflicts:
            details.append("⚠️ " + ", ".join(r.conflicts))
        if r.ai_reason:
            details.append(f"🤖 {r.ai_reason}")
        if details:
            st.caption("\n\n".join(details))
        b1, b2 = st.columns(2)
        if not (opts["show_video"] or st.session_state.get(play_key)):
            b1.button("▶ Xem", key=f"{play_key}_btn", width="stretch",
                      on_click=lambda k=play_key: st.session_state.update({k: True}))
        if chosen:
            b2.button("✅ Đã chọn", key=_key(f"sel_{scene.index}_{r.uid}"), disabled=True,
                      width="stretch")
        else:
            b2.button("Chọn", key=_key(f"sel_{scene.index}_{r.uid}"), type="primary",
                      width="stretch", on_click=_pick_clip, args=(scene.index, r.uid))


def _render_scene(scene: SceneAnalysis, opts: dict, auth,
                  clips: dict[int, StockVideoResult]) -> None:
    project = _project()
    outcome = project.outcomes.get(scene.index)
    css, status = _scene_status(scene, clips)
    with st.container(border=True):
        head, action = st.columns([6, 1])
        head.checkbox(
            f"**Cảnh {scene.index:02d}** — {scene.sentence}",
            value=scene.index not in project.excluded,
            key=_key(f"inc_{scene.index}"),
            on_change=_on_include_change, args=(scene.index,),
            help="Tích để đưa cảnh này vào danh sách tải",
        )
        head.markdown(f'<span class="sm-badge {css}">{status}</span> '
                      f'<small>{_scene_context_line(scene)}</small>', unsafe_allow_html=True)
        if action.button("🔄 Tìm lại", key=_key(f"re_{scene.index}"), width="stretch"):
            _search_and_store(auth, opts, [scene])
            st.rerun()

        with st.expander("Từ khóa & chi tiết", expanded=False):
            st.text_input("Từ khóa tìm (sửa rồi bấm 🔄 Tìm lại)",
                          value=project.queries.get(scene.index, scene.query),
                          key=_key(f"q_{scene.index}"),
                          on_change=_on_query_change, args=(scene.index,))
            if scene.visual_description:
                st.caption(f"🎬 {scene.visual_description}")
            if outcome:
                st.caption("🔎 Đã tìm với: " + " · ".join(f"`{q}`" for q in outcome.tried_queries))
            if scene.index in project.downloads:
                st.caption(f"💾 File: `{project.downloads[scene.index]}`")
            _render_upload(scene)

        if _custom_clip(scene.index):
            st.info(f"📎 Dùng clip của bạn: `{_custom_clip(scene.index).name}` "
                    "(mở 'Từ khóa & chi tiết' để bỏ)")
        elif outcome is None:
            st.caption("Chưa tìm — bấm 🔄 Tìm lại hoặc 'Tìm tất cả cảnh' ở trên.")
        else:
            _render_results(scene, outcome, opts, clips.get(scene.index))


def _render_results(scene: SceneAnalysis, outcome: SearchOutcome, opts: dict,
                    chosen: Optional[StockVideoResult]) -> None:
    for provider, err in outcome.errors.items():
        st.warning(f"{provider}: {err}")
    if not outcome.results:
        st.error("Không tìm thấy clip — sửa từ khóa rồi Tìm lại, hoặc tải clip của bạn lên.")
        return
    more_key = _key(f"more_{scene.index}")
    shown_n = opts["clips_per_scene"] + st.session_state.get(more_key, 0)
    shown = outcome.results[:shown_n]
    if chosen and chosen not in shown:
        shown.append(chosen)
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
        if st.button("✖ Bỏ clip của tôi, dùng lại clip stock", key=_key(f"rmup_{scene.index}")):
            project.uploads.pop(scene.index, None)
            _save()
            st.rerun()
        return
    upload = st.file_uploader("Dùng clip của bạn cho cảnh này",
                              type=["mp4", "mov", "webm", "mkv"], key=_key(f"up_{scene.index}"))
    if upload is not None:
        path = _store().uploads_dir(project.name) / \
            f"scene_{scene.index:02d}{Path(upload.name).suffix.lower()}"
        path.write_bytes(upload.getbuffer())
        project.uploads[scene.index] = str(path)
        _save()
        st.rerun()


def _render_clips_view(auth, opts) -> None:
    project = _project()
    if not project.scenes:
        st.info("Chưa có cảnh nào. Sang bước 📝 Kịch bản để dán kịch bản và phân tích.")
        return
    clips = _effective_map()
    unsearched = [s for s in project.scenes if s.index not in project.outcomes]
    empty = [s for s in project.scenes
             if (o := project.outcomes.get(s.index)) is not None and not o.results]

    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([1.2, 1.2, 1.6, 1.2])
        if c1.button("🔍 Tìm tất cả cảnh", type="primary", width="stretch"):
            _search_and_store(auth, opts, project.scenes)
            st.rerun()
        if c2.button(f"🔍 Tìm cảnh còn thiếu ({len(unsearched) + len(empty)})",
                     width="stretch", disabled=not (unsearched or empty)):
            _search_and_store(auth, opts, unsearched + empty)
            st.rerun()
        filters = {"all": "Tất cả cảnh", "todo": "Chưa tải", "problem": "Chưa có clip"}
        flt = c3.selectbox("Lọc", list(filters), format_func=filters.get,
                           key=_key("filter"), label_visibility="collapsed")
        if c4.button("Tiếp: Tải về ➜", width="stretch"):
            _go("download")
            st.rerun()

    for scene in project.scenes:
        css, _ = _scene_status(scene, clips)
        if flt == "todo" and css == "sm-ok":
            continue
        if flt == "problem" and css not in ("sm-bad", "sm-wait"):
            continue
        _render_scene(scene, opts, auth, clips)

    if st.button("Tiếp: Tải về ➜", key=_key("next_bottom"), type="primary"):
        _go("download")
        st.rerun()


# ------------------------------------------------------------------ view 3: download


async def _download(auth, opts, dl_opts, items, customs, scenes, on_progress):
    async with _engine(auth, opts) as engine:
        downloader = Downloader(
            engine, Path(dl_opts["output_dir"]), words_per_second=_settings()["wps"],
            max_width=QUALITIES[dl_opts["quality"]], name_style=dl_opts["name_style"],
            overwrite=dl_opts["overwrite"], max_parallel=dl_opts["parallel"],
        )
        results = await downloader.download(items, on_progress=on_progress, custom_clips=customs)
        manifest = downloader.write_manifest(results, all_scenes=scenes)
        if dl_opts["credits"]:
            downloader.write_credits(results)
        return results, manifest


def _download_plan(indices: list[int], dl_opts: dict
                   ) -> tuple[list[DownloadItem], list[CustomClip], list[int]]:
    """Items to fetch for these scenes, custom clips to copy, scenes with nothing to get."""
    project = _project()
    clips = _effective_map()
    by_index = {s.index: s for s in project.scenes}
    items, customs, missing = [], [], []
    for i in indices:
        scene = by_index[i]
        custom = _custom_clip(i)
        if custom:
            customs.append(CustomClip(scene, custom))
            continue
        clip = clips.get(i)
        if not clip:
            missing.append(i)
            continue
        keyword = project.queries.get(i) or scene.query
        items.append(DownloadItem(scene, clip, keyword=keyword))
        if dl_opts["mode"] == "alternates":
            outcome = project.outcomes[i]
            others = [r for r in outcome.results if r.uid != clip.uid][:dl_opts["alt_count"]]
            items += [DownloadItem(scene, r, keyword=keyword, alt=n)
                      for n, r in enumerate(others, start=1)]
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


def _run_download(auth, opts, dl_opts, indices: list[int], label: str) -> None:
    project = _project()
    items, customs, missing = _download_plan(indices, dl_opts)
    if not (items or customs):
        st.warning("Không có cảnh nào có clip để tải. Hãy tìm clip ở bước 🎬 trước.")
        return
    # A different clip was picked since the last download: replace the old file
    for item in items:
        i = item.scene.index
        old = project.downloads.get(i)
        if item.alt == 0 and old and project.download_uids.get(i) != item.video.uid:
            Path(old).unlink(missing_ok=True)
            project.downloads.pop(i, None)
    bar = st.progress(0.0, text=f"{label}: chuẩn bị…")
    per_item: dict[int, float] = {}

    def on_progress(scene_index: int, done: int, total: int):
        per_item[scene_index] = done / total if total else 0.5
        overall = sum(per_item.values()) / max(1, len({it.scene.index for it in items}))
        bar.progress(min(1.0, overall),
                     text=f"{label}: cảnh {scene_index:02d} · {done / 1e6:.1f} MB")

    try:
        results, manifest = _run(_download(auth, opts, dl_opts, items, customs,
                                           project.scenes, on_progress))
    except Exception as e:
        bar.empty()
        st.error(f"Tải thất bại: {e}")
        return
    bar.empty()
    for r in results:
        if r.ok and not r.alt:
            project.downloads[r.scene.index] = str(r.path)
            project.download_uids[r.scene.index] = r.video.uid if r.video else "custom"
    _save()
    st.session_state[_key("report")] = {
        "new": sum(r.ok and not r.skipped_existing for r in results),
        "existing": sum(r.skipped_existing for r in results),
        "alts": sum(r.ok and r.alt > 0 for r in results),
        "errors": [f"Cảnh {r.scene.index:02d}{' (dự phòng)' if r.alt else ''}: {r.error}"
                   for r in results if not r.ok],
        "missing": missing,
        "folder": dl_opts["output_dir"],
        "files": [str(r.path.name) for r in results if r.ok],
    }
    st.rerun()


def _render_download_options() -> dict:
    saved = _settings()
    project = _project()
    with st.container(border=True):
        st.markdown("##### ⚙️ Tùy chọn tải")
        c1, c2 = st.columns(2)
        with c1:
            quality = st.radio("Chất lượng video", list(QUALITIES), horizontal=True,
                               format_func=QUALITY_LABELS.get,
                               index=list(QUALITIES).index(saved["quality"])
                               if saved["quality"] in QUALITIES else 1,
                               help="Tải bản rộng nhất không vượt quá mức này. Clip nào không "
                                    "có bản cao hơn thì tải bản lớn nhất có sẵn.")
            mode = st.radio("Tải gì cho mỗi cảnh", list(DL_MODES), format_func=DL_MODES.get,
                            index=list(DL_MODES).index(saved["dl_mode"])
                            if saved["dl_mode"] in DL_MODES else 0)
            alt_count = st.slider("Số clip dự phòng mỗi cảnh", 1, 5, int(saved["alt_count"]),
                                  disabled=mode != "alternates",
                                  help="Lưu thành scene_01_..._alt1.mp4, _alt2.mp4…")
        with c2:
            name_style = st.selectbox("Đặt tên file", list(NAME_STYLES),
                                      format_func=lambda k: NAME_STYLES[k],
                                      index=list(NAME_STYLES).index(saved["name_style"])
                                      if saved["name_style"] in NAME_STYLES else 0)
            d1, d2 = st.columns([3, 1])
            output_dir = d1.text_input("Thư mục lưu", value=_output_dir(),
                                       key=_key(f"outdir_{project.name}"))
            d2.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)
            if d2.button("📂 Mở", width="stretch"):
                _open_folder(Path(output_dir))
            t1, t2 = st.columns(2)
            overwrite = t1.toggle("Ghi đè file đã có", value=bool(saved["overwrite"]))
            credits = t2.toggle("Xuất credits.txt", value=bool(saved["credits"]),
                                help="Danh sách nguồn & tác giả từng clip để ghi credit.")
            parallel = st.slider("Số clip tải cùng lúc", 1, 6, int(saved["parallel"]))

    dirs = dict(saved["output_dirs"])
    if output_dir != _output_dir():
        dirs[project.name] = output_dir
    _update_settings({"quality": quality, "dl_mode": mode, "alt_count": alt_count,
                      "name_style": name_style, "overwrite": overwrite, "credits": credits,
                      "parallel": parallel, "output_dirs": dirs})
    return {"quality": quality, "mode": mode, "alt_count": alt_count,
            "name_style": name_style, "overwrite": overwrite, "credits": credits,
            "parallel": parallel, "output_dir": output_dir}


def _render_scene_table(clips: dict[int, StockVideoResult]) -> None:
    project = _project()
    rows = []
    for s in project.scenes:
        clip = clips.get(s.index)
        custom = _custom_clip(s.index)
        _, status = _scene_status(s, clips)
        rows.append({
            "Tải": s.index not in project.excluded,
            "Cảnh": f"{s.index:02d}",
            "Ảnh": clip.thumbnail_url if clip and not custom else None,
            "Câu": s.sentence,
            "Clip": "Clip của bạn" if custom else
                    (f"{clip.provider} · ⭐{clip.score:.0f} · {clip.duration:.0f}s" if clip else "—"),
            "Trạng thái": status,
        })
    ver = st.session_state.get(_key("table_ver"), 0)
    edited = st.data_editor(
        pd.DataFrame(rows), key=_key(f"table_{ver}"), hide_index=True,
        width="stretch", row_height=56,
        disabled=["Cảnh", "Ảnh", "Câu", "Clip", "Trạng thái"],
        column_config={
            "Tải": st.column_config.CheckboxColumn("Tải", width="small"),
            "Cảnh": st.column_config.TextColumn("Cảnh", width="small"),
            "Ảnh": st.column_config.ImageColumn("Ảnh", width="small"),
            "Câu": st.column_config.TextColumn("Câu", width="large"),
        },
    )
    excluded = [s.index for s, keep in zip(project.scenes, edited["Tải"]) if not keep]
    if sorted(excluded) != sorted(project.excluded):
        project.excluded = excluded
        _save()
        st.rerun()


def _render_download_view(auth, opts) -> None:
    project = _project()
    if not project.scenes:
        st.info("Chưa có cảnh nào. Sang bước 📝 Kịch bản để bắt đầu.")
        return
    actions = st.container()  # filled below, shown first so the buttons are on top
    dl_opts = _render_download_options()
    clips = _effective_map()
    ready = [s.index for s in project.scenes if _custom_clip(s.index) or s.index in clips]
    chosen = [i for i in ready if i not in project.excluded]

    with st.container(border=True):
        st.markdown(f"##### 🎬 Chọn cảnh để tải · {len(chosen)}/{len(project.scenes)} cảnh")
        if len(ready) < len(project.scenes):
            st.caption(f"{len(project.scenes) - len(ready)} cảnh chưa có clip sẽ được bỏ qua — "
                       "quay lại bước 🎬 để tìm.")
        _render_scene_table(clips)
        c1, c2, _ = st.columns([1, 1, 3])
        c1.button("☑ Chọn tất cả", width="stretch",
                  on_click=_set_all_included, args=(True,))
        c2.button("☐ Bỏ chọn tất cả", width="stretch",
                  on_click=_set_all_included, args=(False,))

    per_scene = 1 + (dl_opts["alt_count"] if dl_opts["mode"] == "alternates" else 0)
    with actions.container(border=True):
        st.markdown(f"##### ⬇️ Tải về · {dl_opts['quality']} · {DL_MODES[dl_opts['mode']]}")
        premium = sum(1 for i in chosen
                      if (c := clips.get(i)) and c.is_premium and not _custom_clip(i))
        if premium:
            st.warning(f"{premium} clip trả phí sẽ được mua bản quyền và trừ vào gói của bạn.")
        b1, b2, b3 = st.columns([1.3, 1.3, 1])
        if b1.button(f"⬇️ Tải cảnh đã chọn ({len(chosen)} cảnh · ~{len(chosen) * per_scene} file)",
                     type="primary", width="stretch", disabled=not chosen):
            _run_download(auth, opts, dl_opts, chosen, "Tải cảnh đã chọn")
        if b2.button(f"⬇️ Tải tất cả cảnh ({len(ready)})", width="stretch",
                     disabled=not ready):
            _run_download(auth, opts, dl_opts, ready, "Tải tất cả")
        if b3.button("📂 Mở thư mục", key=_key("open_main"), width="stretch"):
            _open_folder(Path(dl_opts["output_dir"]))

        report = st.session_state.get(_key("report"))
        if report:
            parts = [f"**{report['new']}** file mới"]
            if report["existing"]:
                parts.append(f"{report['existing']} file đã có sẵn (không tải lại)")
            if report["alts"]:
                parts.append(f"trong đó {report['alts']} clip dự phòng")
            st.success("Xong: " + " · ".join(parts) + f" → `{report['folder']}`")
            for err in report["errors"]:
                st.error(err)
            if report["missing"]:
                st.info("Bỏ qua (chưa có clip): cảnh " +
                        ", ".join(f"{i:02d}" for i in report["missing"]))
            with st.expander(f"📄 Danh sách file ({len(report['files'])})"):
                st.code("\n".join(report["files"] + ["manifest.json"]
                                  + (["credits.txt"] if dl_opts["credits"] else [])),
                        language=None)


# ------------------------------------------------------------------ page


def render() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    auth = _auth()
    _render_project_bar()
    opts = _render_sidebar(auth)
    _render_header()
    view = _render_nav()
    if view == "script":
        _render_script_view(auth, opts)
    elif view == "clips":
        _render_clips_view(auth, opts)
    else:
        _render_download_view(auth, opts)


if __name__ == "__main__":
    st.set_page_config(page_title="Stock Matcher", page_icon="🎞️", layout="wide")
    render()
