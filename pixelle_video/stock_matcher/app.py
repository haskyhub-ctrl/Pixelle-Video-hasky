"""
Module D (UI) - Streamlit dashboard for script-to-stock matching.

Desktop:     python -m pixelle_video.stock_matcher.desktop   (own window)
Standalone:  streamlit run pixelle_video/stock_matcher/app.py
Embedded:    web/pages/3_🎞️_Stock_Matcher.py calls render()

All work lives in a project saved on disk (see project_store.py) and is saved
after every change, so nothing is lost when the window or browser tab closes.
"""

import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    # Allow `streamlit run pixelle_video/stock_matcher/app.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from pixelle_video.stock_matcher.auth_manager import PROVIDER_ENV_VARS, AuthManager
from pixelle_video.stock_matcher.downloader import CustomClip, Downloader
from pixelle_video.stock_matcher.llm_extractor import check_connection
from pixelle_video.stock_matcher.models import DownloadItem, SceneAnalysis, SearchOutcome
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
    widget_prefixes = tuple(_key(p) for p in ("q_", "pick_", "up_", "play_", "more_",
                                              "script_box"))
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


# ------------------------------------------------------------------ sidebar


def _render_project_bar() -> None:
    store, project = _store(), _project()
    with st.sidebar:
        st.header("📁 Project")
        names = store.list_projects()
        if project.name not in names:
            names.insert(0, project.name)
        choice = st.selectbox("Open project", names, index=names.index(project.name),
                              help="Everything is saved automatically after each step.")
        if choice != project.name:
            _open_project(choice)
            st.rerun()
        c1, c2 = st.columns(2)
        if c1.button("➕ New", use_container_width=True):
            new = ProjectState(name=store.new_name(), script="")
            store.save(new)
            st.session_state[_key("project")] = new
            _clear_widget_state()
            st.rerun()
        with c2.popover("✏️ Rename", use_container_width=True):
            new_name = st.text_input("New name", value=project.name)
            if st.button("Save name") and new_name.strip() and new_name != project.name:
                try:
                    project.name = store.rename(project.name, new_name)
                    _save()
                    st.rerun()
                except OSError as e:
                    st.error(str(e))
        if project.updated_at:
            st.caption(f"💾 Saved {project.updated_at.replace('T', ' ')}")


def _render_sidebar(auth: AuthManager) -> dict:
    saved = _load_settings()
    with st.sidebar:
        st.header("Providers")
        status = auth.status()
        labels = {k: cls.name + (" 💎" if cls.is_premium else "")
                  for k, cls in PROVIDER_CLASSES.items()}
        default_providers = [p for p in (saved["providers"] or DEFAULT_PROVIDERS)
                             if p in PROVIDER_CLASSES]
        if saved["providers"] is None:
            default_providers = [p for p in DEFAULT_PROVIDERS if status[p]["configured"]] \
                or DEFAULT_PROVIDERS
        providers = st.multiselect(
            "Search on",
            options=list(PROVIDER_CLASSES),
            default=default_providers,
            format_func=lambda k: labels[k] + ("" if status[k]["configured"] else " ⚠️"),
        )
        for p in providers:
            if not status[p]["configured"]:
                st.warning(f"{labels[p]}: missing {', '.join(status[p]['missing'])}")

        with st.expander("🔑 API keys (this session only)"):
            st.caption("Prefer a `.env` file. Values entered here are not saved.")
            for env_vars in PROVIDER_ENV_VARS.values():
                for var in env_vars:
                    value = st.text_input(var, type="password", key=_key(f"key_{var}"))
                    if value:
                        auth.set_override(var, value)

        st.header("Search options")
        clips_per_scene = st.slider("Clips shown per scene", 1, 10,
                                    int(saved["clips_per_scene"]),
                                    help="The best matches are shown first; use "
                                         "'Show more' under a scene to see the next ones.")
        orientations = ["any", "landscape", "portrait", "square"]
        orientation = st.selectbox("Orientation", orientations,
                                   index=orientations.index(saved["orientation"])
                                   if saved["orientation"] in orientations else 0)
        min_duration = st.number_input("Min clip length (s)", 0.0, 60.0,
                                       float(saved["min_duration"]), step=1.0)

        st.header("NLP")
        llm = auth.llm_settings()
        use_llm = st.toggle(
            "Use LLM extraction / translation",
            value=bool(saved["use_llm"]) and llm.enabled,
            disabled=not llm.enabled,
            help="Configure STOCK_LLM_BACKEND / STOCK_LLM_MODEL / STOCK_LLM_API_KEY "
                 "or the llm section of config.yaml",
        )
        if llm.enabled:
            st.caption(f"{llm.backend} · {llm.model} · {llm.base_url or 'default URL'}")
            if st.button("🔌 Test LLM connection"):
                _test_llm(llm)
        else:
            st.caption("No LLM configured: rule-based analysis only. An LLM gives much "
                       "better scene understanding, especially for Vietnamese scripts.")
        ai_rerank = st.toggle(
            "AI judges thumbnails (vision)",
            value=bool(saved["ai_rerank"]) and llm.enabled,
            disabled=not llm.enabled,
            help="After searching, a vision-capable LLM looks at the top clips of each "
                 "scene and scores how well they fit. Most accurate; costs LLM tokens. "
                 "Set STOCK_LLM_VISION_MODEL if your main model has no vision.",
        )
        ai_top_n = st.slider("Clips judged per scene", 3, 12, int(saved["ai_top_n"]),
                             disabled=not ai_rerank)

        st.header("Output")
        project = _project()
        output_dir = st.text_input("Output folder", f"output/stock_clips/{project.name}",
                                   key=_key(f"outdir_{project.name}"))
        wps = st.number_input("Narration words / second", 1.0, 5.0, float(saved["wps"]),
                              step=0.1)
        show_video = st.toggle(
            "Autoplay all previews (heavy)", value=bool(saved["show_video"]),
            help="Loads every preview video at once and can freeze the window. "
                 "Leave off and click ▶ on the clips you want to watch.",
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
        with st.spinner("Asking the LLM…"):
            reply = check_connection(llm)
        st.success(f"LLM replied: {reply[:80] or '(empty)'}")
    except Exception as e:
        hint = ""
        if "connection" in str(e).lower():
            hint = (" — is the LLM server running and is STOCK_LLM_BASE_URL correct? "
                    "(9Router: open its dashboard first)")
        elif "401" in str(e) or "auth" in str(e).lower():
            hint = " — check STOCK_LLM_API_KEY"
        elif "404" in str(e) or "model" in str(e).lower():
            hint = " — check STOCK_LLM_MODEL matches a model/combo name"
        st.error(f"LLM error: {e}{hint}")


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
    bar = st.progress(0.0, text=f"Searching {len(scenes)} scene(s)…")

    def on_scene_done(outcome: SearchOutcome, finished: int, total: int):
        bar.progress(finished / total,
                     text=f"Searched {finished}/{total} · scene {outcome.scene.index:02d}: "
                          f"{len(outcome.results)} candidate clip(s)")

    try:
        outcomes, skipped = _run(_search(auth, opts, scenes, overrides, on_scene_done))
    except Exception as e:
        bar.empty()
        st.error(str(e))
        return
    bar.empty()
    for name, reason in skipped.items():
        st.warning(f"{name} skipped: {reason}")

    # Save the text-ranked results right away, before the slower AI step
    for o in outcomes:
        project.outcomes[o.scene.index] = o
    _save()

    if opts["ai_rerank"]:
        bar = st.progress(0.0, text="AI is judging thumbnails…")
        failures: list[str] = []

        def on_rated(outcome: SearchOutcome, finished: int, total: int, error: str):
            if error:
                failures.append(f"scene {outcome.scene.index:02d}: {error}")
            bar.progress(finished / max(1, total), text=f"AI judged {finished}/{total} scene(s)")

        try:
            _run(rerank_outcomes(_auth().llm_settings(), outcomes, top_n=opts["ai_top_n"],
                                 on_done=on_rated))
        except Exception as e:
            failures.append(str(e))
        bar.empty()
        if failures:
            st.warning("AI judging failed for some scenes (text ranking kept). Does the "
                       "model accept images?\n\n" + "\n".join(failures[:5]))
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
    return f"{text or 'no context detected'} · via {scene.source}" + \
        (" · ↩ = carried over from earlier scenes" if scene.inherited else "")


def _on_query_change(index: int) -> None:
    project = _project()
    project.queries[index] = st.session_state.get(_key(f"q_{index}"), "")
    _save()


def _on_pick_change(index: int) -> None:
    project = _project()
    choice = st.session_state.get(_key(f"pick_{index}"))
    if choice is None:
        project.selections.pop(index, None)
    else:
        project.selections[index] = choice
    _save()


def _render_clip(scene: SceneAnalysis, r, rank: int, opts: dict) -> None:
    play_key = _key(f"play_{scene.index}_{r.uid}")
    if opts["show_video"] or st.session_state.get(play_key):
        st.video(r.preview_url, muted=True, loop=True, autoplay=True)
    else:
        if r.thumbnail_url.startswith("http"):
            st.image(r.thumbnail_url, width="stretch")
        else:
            st.caption("(no thumbnail)")
        st.button("▶ Preview", key=f"{play_key}_btn",
                  on_click=lambda k=play_key: st.session_state.update({k: True}))
    badge = "💎 " if r.is_premium else ""
    ai = f" · 🤖 {r.ai_score:.0f}/10" if r.ai_score is not None else ""
    lines = [f"**#{rank} · ⭐ {r.score:.0f}**{ai} · {badge}{r.provider} · "
             f"{r.duration:.0f}s · {r.width}x{r.height}"]
    if r.matched_terms:
        lines.append("✅ " + ", ".join(r.matched_terms))
    if r.conflicts:
        lines.append("⚠️ " + ", ".join(r.conflicts))
    if r.ai_reason:
        lines.append(f"🤖 {r.ai_reason}")
    lines.append(r.title[:70])
    st.caption("\n\n".join(lines))


def _render_scene(scene: SceneAnalysis, opts: dict, auth) -> None:
    project = _project()
    outcome = project.outcomes.get(scene.index)
    with st.container(border=True):
        head, action = st.columns([5, 1])
        head.markdown(f"**Scene {scene.index:02d}** — {scene.sentence}")
        head.caption(_scene_context_line(scene))
        if scene.visual_description:
            head.caption(f"🎬 {scene.visual_description}")
        if scene.index in project.downloads:
            head.caption(f"✅ Downloaded: `{Path(project.downloads[scene.index]).name}`")
        st.text_input("Search query (edit, then Re-search)",
                      value=project.queries.get(scene.index, scene.query),
                      key=_key(f"q_{scene.index}"),
                      on_change=_on_query_change, args=(scene.index,))
        if action.button("🔄 Re-search", key=_key(f"re_{scene.index}")):
            _search_and_store(auth, opts, [scene])
            st.rerun()

        if outcome is None:
            st.caption("Not searched yet.")
        else:
            _render_results(scene, outcome, opts)
        _render_upload(scene)


def _render_results(scene: SceneAnalysis, outcome: SearchOutcome, opts: dict) -> None:
    project = _project()
    st.caption("🔎 Queries: " + " · ".join(f"`{q}`" for q in outcome.tried_queries))
    for provider, err in outcome.errors.items():
        st.warning(f"{provider}: {err}")
    if not outcome.results:
        st.error("No clips found — edit the query and re-search, or upload a clip.")
        return

    more_key = _key(f"more_{scene.index}")
    shown_n = opts["clips_per_scene"] + st.session_state.get(more_key, 0)
    shown = outcome.results[:shown_n]
    cols = st.columns(GRID_COLUMNS)
    for i, r in enumerate(shown):
        with cols[i % GRID_COLUMNS]:
            _render_clip(scene, r, i + 1, opts)
    if len(outcome.results) > shown_n:
        st.button(f"➕ Show more ({len(outcome.results) - shown_n} left)",
                  key=f"{more_key}_btn",
                  on_click=lambda: st.session_state.update(
                      {more_key: st.session_state.get(more_key, 0) + opts["clips_per_scene"]}))

    by_uid = {r.uid: r for r in outcome.results}
    rank = {r.uid: i + 1 for i, r in enumerate(outcome.results)}
    options = [None] + [r.uid for r in shown]
    current = project.selections.get(scene.index)
    if current in by_uid and current not in options:
        options.append(current)  # picked from "Show more" earlier
    pick_key = _key(f"pick_{scene.index}")
    if pick_key in st.session_state and st.session_state[pick_key] not in options:
        del st.session_state[pick_key]
    st.radio(
        "Clip for this scene",
        options,
        index=options.index(current) if current in options else 0,
        format_func=lambda uid: "skip" if uid is None
        else f"#{rank[uid]} ⭐{by_uid[uid].score:.0f}",
        horizontal=True,
        key=pick_key,
        on_change=_on_pick_change, args=(scene.index,),
    )


def _render_upload(scene: SceneAnalysis) -> None:
    project = _project()
    existing = project.uploads.get(scene.index)
    if existing and Path(existing).exists():
        c1, c2 = st.columns([5, 1])
        c1.caption(f"📎 Custom clip: `{Path(existing).name}` (used instead of stock)")
        if c2.button("✖ Remove", key=_key(f"rmup_{scene.index}")):
            project.uploads.pop(scene.index, None)
            _save()
            st.rerun()
        return
    upload = st.file_uploader("…or upload your own clip", type=["mp4", "mov", "webm", "mkv"],
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


def _render_download(auth, opts, scenes: list[SceneAnalysis]) -> None:
    project = _project()
    uploads = {i: Path(p) for i, p in project.uploads.items() if Path(p).exists()}

    items = []
    for scene in scenes:
        if scene.index in uploads:
            continue
        outcome = project.outcomes.get(scene.index)
        uid = project.selections.get(scene.index)
        video = next((r for r in outcome.results if r.uid == uid), None) if outcome else None
        if video:
            keyword = project.queries.get(scene.index) or scene.query
            items.append(DownloadItem(scene, video, keyword=keyword))
    customs = [CustomClip(s, uploads[s.index]) for s in scenes if s.index in uploads]

    st.subheader("⬇️ Download")
    c1, c2 = st.columns(2)
    if c1.button("Auto-select best clip for unselected scenes"):
        for scene in scenes:
            o = project.outcomes.get(scene.index)
            if o and o.results and scene.index not in project.selections:
                project.selections[scene.index] = o.results[0].uid
        _save()
        for k in [k for k in st.session_state if k.startswith(_key("pick_"))]:
            del st.session_state[k]
        st.rerun()

    premium = sum(1 for i in items if i.video.is_premium)
    st.write(f"{len(items)} stock clip(s) + {len(customs)} custom clip(s) selected "
             f"for {len(scenes)} scene(s). Files go to `{opts['output_dir']}`.")
    if premium:
        st.warning(f"{premium} premium clip(s) will be licensed and count against your plan.")

    if c2.button("Download selected", type="primary", disabled=not (items or customs)):
        bar = st.progress(0.0, text="Starting…")
        per_scene: dict[int, float] = {}

        def on_progress(scene_index: int, done: int, total: int):
            per_scene[scene_index] = done / total if total else 0.5
            overall = sum(per_scene.values()) / max(1, len(items))
            bar.progress(min(1.0, overall), text=f"Scene {scene_index:02d}: {done / 1e6:.1f} MB")

        try:
            results, manifest = _run(_download(auth, opts, items, customs, scenes, on_progress))
        except Exception as e:
            st.error(f"Download failed: {e}")
            return
        bar.progress(1.0, text="Done")
        for r in results:
            if r.ok:
                project.downloads[r.scene.index] = str(r.path)
        _save()
        ok = [r for r in results if r.ok]
        st.success(f"Saved {len(ok)}/{len(results)} clip(s) to {opts['output_dir']}")
        for r in results:
            if not r.ok:
                st.error(f"Scene {r.scene.index:02d}: {r.error}")
        manifest_text = manifest.read_text(encoding="utf-8")
        st.download_button("manifest.json", manifest_text, file_name="manifest.json",
                           mime="application/json")
        with st.expander("Manifest"):
            st.json(json.loads(manifest_text))


# ------------------------------------------------------------------ page


def render() -> None:
    project = _project()
    auth = _auth()
    _render_project_bar()
    opts = _render_sidebar(auth)

    st.title("🎞️ Script → Stock Video Matcher")
    st.caption(f"Project **{project.name}** · paste a script, review the best matching "
               "clips per sentence, then download. Your work is saved automatically.")

    script = st.text_area("Script", value=project.script, height=180,
                          key=_key("script_box"),
                          help="One scene per sentence or per line. Vietnamese is supported "
                               "(best with an LLM configured).")
    if script != project.script:
        project.script = script
        _save()

    c1, c2 = st.columns(2)
    if c1.button("1️⃣ Analyze script", use_container_width=True, disabled=not script.strip()):
        if project.outcomes and not st.session_state.get(_key("confirm_reanalyze")):
            st.session_state[_key("confirm_reanalyze")] = True
            st.warning("Re-analysing clears this project's search results and selections. "
                       "Click **Analyze script** again to confirm.")
        else:
            st.session_state.pop(_key("confirm_reanalyze"), None)
            try:
                with st.spinner("Analysing the script…"):
                    parser = ScriptParser(llm=auth.llm_settings())
                    scenes = parser.parse(script, use_llm=opts["use_llm"] or False)
            except Exception as e:
                st.error(f"Analysis failed: {e}")
                scenes = []
            project.scenes = scenes
            project.outcomes, project.selections, project.queries = {}, {}, {}
            _save()
            _clear_widget_state()
            st.rerun()

    scenes = project.scenes
    if c2.button("2️⃣ Search all scenes", use_container_width=True, disabled=not scenes):
        _search_and_store(auth, opts, scenes)

    if not scenes:
        st.info("Analyze a script to get started.")
        return

    for scene in scenes:
        _render_scene(scene, opts, auth)
    _render_download(auth, opts, scenes)


if __name__ == "__main__":
    st.set_page_config(page_title="Stock Matcher", page_icon="🎞️", layout="wide")
    render()
