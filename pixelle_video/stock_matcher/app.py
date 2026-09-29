"""
Module D (UI) - Streamlit dashboard for script-to-stock matching.

Standalone:  streamlit run pixelle_video/stock_matcher/app.py
Embedded:    web/pages/3_🎞️_Stock_Matcher.py calls render()
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

if __package__ in (None, ""):
    # Allow `streamlit run pixelle_video/stock_matcher/app.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from pixelle_video.stock_matcher.auth_manager import PROVIDER_ENV_VARS, AuthManager
from pixelle_video.stock_matcher.downloader import CustomClip, Downloader
from pixelle_video.stock_matcher.models import DownloadItem, SceneAnalysis, SearchOutcome
from pixelle_video.stock_matcher.nlp_parser import ScriptParser
from pixelle_video.stock_matcher.stock_searcher import (
    DEFAULT_PROVIDERS,
    PROVIDER_CLASSES,
    StockSearchEngine,
)

STATE_PREFIX = "sm_"
GRID_COLUMNS = 3
EXAMPLE_SCRIPT = (
    "An engineer is working late at night, coding on a laptop.\n"
    "The city lights shine through the office window.\n"
    "In the morning, the team celebrates a successful product launch."
)


def _state(key: str, default=None):
    full = STATE_PREFIX + key
    if full not in st.session_state:
        st.session_state[full] = default
    return st.session_state[full]


def _set(key: str, value) -> None:
    st.session_state[STATE_PREFIX + key] = value


def _run(coro):
    try:
        from web.utils.async_helpers import run_async

        return run_async(coro)
    except ImportError:
        return asyncio.run(coro)


def _auth() -> AuthManager:
    auth = _state("auth")
    if auth is None:
        auth = AuthManager()
        _set("auth", auth)
    return auth


def _render_sidebar(auth: AuthManager) -> dict:
    with st.sidebar:
        st.header("Providers")
        status = auth.status()
        labels = {k: cls.name + (" 💎" if cls.is_premium else "") for k, cls in PROVIDER_CLASSES.items()}
        providers = st.multiselect(
            "Search on",
            options=list(PROVIDER_CLASSES),
            default=[p for p in DEFAULT_PROVIDERS if status[p]["configured"]] or DEFAULT_PROVIDERS,
            format_func=lambda k: labels[k] + ("" if status[k]["configured"] else " ⚠️"),
        )
        for p in providers:
            if not status[p]["configured"]:
                st.warning(f"{labels[p]}: missing {', '.join(status[p]['missing'])}")

        with st.expander("🔑 API keys (this session only)"):
            st.caption("Prefer a `.env` file. Values entered here are not saved.")
            for provider, env_vars in PROVIDER_ENV_VARS.items():
                for var in env_vars:
                    value = st.text_input(var, type="password", key=f"{STATE_PREFIX}key_{var}")
                    if value:
                        auth.set_override(var, value)

        st.header("Search options")
        orientation = st.selectbox("Orientation", ["any", "landscape", "portrait", "square"])
        per_page = st.slider("Results per provider", 3, 15, 6)
        min_duration = st.number_input("Min clip length (s)", 0.0, 60.0, 0.0, step=1.0)

        st.header("NLP")
        llm = auth.llm_settings()
        use_llm = st.toggle(
            "Use LLM extraction / translation",
            value=llm.enabled,
            disabled=not llm.enabled,
            help="Configure STOCK_LLM_BACKEND / STOCK_LLM_MODEL / STOCK_LLM_API_KEY "
                 "or the llm section of config.yaml",
        )
        if llm.enabled:
            st.caption(f"{llm.backend} · {llm.model}")

        st.header("Output")
        output_dir = st.text_input("Output folder", "output/stock_clips")
        wps = st.number_input("Narration words / second", 1.0, 5.0, 2.5, step=0.1)
        show_video = st.toggle(
            "Autoplay all previews (heavy)", value=False,
            help="Loads every preview video at once and can freeze the browser. "
                 "Leave off and click ▶ on the clips you want to watch.",
        )
    return {
        "providers": providers,
        "orientation": None if orientation == "any" else orientation,
        "per_page": per_page,
        "min_duration": min_duration,
        "use_llm": use_llm,
        "output_dir": output_dir,
        "wps": wps,
        "show_video": show_video,
    }


def _engine(auth: AuthManager, opts: dict) -> StockSearchEngine:
    return StockSearchEngine(auth, providers=opts["providers"], orientation=opts["orientation"],
                             min_duration=opts["min_duration"])


async def _search(auth, opts, scenes: list[SceneAnalysis], overrides: dict[int, str],
                  on_scene_done=None):
    async with _engine(auth, opts) as engine:
        outcomes = await engine.search_scenes(scenes, per_page=opts["per_page"],
                                              overrides=overrides, on_scene_done=on_scene_done)
        return outcomes, engine.skipped


def _search_and_store(auth, opts, scenes: list[SceneAnalysis]) -> None:
    overrides = {
        s.index: q for s in scenes
        if (q := st.session_state.get(f"{STATE_PREFIX}q_{s.index}", "").strip()) and q != s.query
    }
    bar = st.progress(0.0, text=f"Searching {len(scenes)} scene(s)…")

    def on_scene_done(outcome: SearchOutcome, finished: int, total: int):
        bar.progress(finished / total,
                     text=f"Searched {finished}/{total} · scene {outcome.scene.index:02d}: "
                          f"{len(outcome.results)} clip(s)")

    try:
        outcomes, skipped = _run(_search(auth, opts, scenes, overrides, on_scene_done))
    except Exception as e:
        bar.empty()
        st.error(str(e))
        return
    bar.empty()
    for name, reason in skipped.items():
        st.warning(f"{name} skipped: {reason}")
    stored: dict[int, SearchOutcome] = _state("outcomes", {})
    for o in outcomes:
        stored[o.scene.index] = o
    _set("outcomes", stored)


def _render_scene(scene: SceneAnalysis, outcome: SearchOutcome | None, opts: dict, auth) -> None:
    selections: dict[int, str] = _state("selections", {})
    with st.container(border=True):
        head, action = st.columns([5, 1])
        head.markdown(f"**Scene {scene.index:02d}** — {scene.sentence}")
        head.caption(
            f"subjects: {', '.join(scene.subjects) or '–'} · actions: "
            f"{', '.join(scene.actions) or '–'} · mood: {', '.join(scene.descriptors) or '–'} "
            f"· via {scene.source}"
        )
        st.text_input("Search query", value=scene.query, key=f"{STATE_PREFIX}q_{scene.index}")
        if action.button("🔄 Re-search", key=f"{STATE_PREFIX}re_{scene.index}"):
            _search_and_store(auth, opts, [scene])
            st.rerun()

        if outcome is None:
            st.caption("Not searched yet.")
        else:
            if outcome.used_query and outcome.used_query != outcome.tried_queries[0]:
                st.info(f"No results for '{outcome.tried_queries[0]}', "
                        f"showing results for simplified query '{outcome.used_query}'.")
            for provider, err in outcome.errors.items():
                st.warning(f"{provider}: {err}")
            if not outcome.results:
                st.error("No clips found — edit the query and re-search, or upload a clip.")
            by_uid = {r.uid: r for r in outcome.results}
            cols = st.columns(GRID_COLUMNS)
            for i, r in enumerate(outcome.results):
                with cols[i % GRID_COLUMNS]:
                    play_key = f"{STATE_PREFIX}play_{scene.index}_{r.uid}"
                    if opts["show_video"] or st.session_state.get(play_key):
                        st.video(r.preview_url, muted=True, loop=True, autoplay=True)
                    else:
                        if r.thumbnail_url:
                            st.image(r.thumbnail_url, width="stretch")
                        else:
                            st.caption("(no thumbnail)")
                        st.button("▶ Preview", key=f"{play_key}_btn",
                                  on_click=lambda k=play_key: st.session_state.update({k: True}))
                    badge = "💎 " if r.is_premium else ""
                    st.caption(f"#{i + 1} · {badge}{r.provider} · {r.duration:.0f}s · "
                               f"{r.width}x{r.height}\n\n{r.title[:70]}")
            if outcome.results:
                options = [None] + list(by_uid)
                pick_key = f"{STATE_PREFIX}pick_{scene.index}"
                if st.session_state.get(pick_key) not in options:
                    st.session_state.pop(pick_key, None)
                current = selections.get(scene.index)
                choice = st.radio(
                    "Clip for this scene",
                    options,
                    index=options.index(current) if current in options else 0,
                    format_func=lambda uid: "skip" if uid is None
                    else f"#{list(by_uid).index(uid) + 1} {by_uid[uid].provider}",
                    horizontal=True,
                    key=pick_key,
                )
                if choice is None:
                    selections.pop(scene.index, None)
                else:
                    selections[scene.index] = choice
                _set("selections", selections)

        upload = st.file_uploader("…or upload your own clip", type=["mp4", "mov", "webm", "mkv"],
                                  key=f"{STATE_PREFIX}up_{scene.index}")
        uploads: dict[int, Path] = _state("uploads", {})
        if upload is not None:
            tmp_dir = Path(tempfile.gettempdir()) / "stock_matcher_uploads"
            tmp_dir.mkdir(exist_ok=True)
            path = tmp_dir / f"scene_{scene.index:02d}{Path(upload.name).suffix}"
            path.write_bytes(upload.getbuffer())
            uploads[scene.index] = path
            st.success(f"Custom clip will be used for scene {scene.index}.")
        else:
            uploads.pop(scene.index, None)
        _set("uploads", uploads)


async def _download(auth, opts, items, customs, scenes, on_progress):
    async with _engine(auth, opts) as engine:
        downloader = Downloader(engine, Path(opts["output_dir"]), words_per_second=opts["wps"])
        results = await downloader.download(items, on_progress=on_progress, custom_clips=customs)
        manifest = downloader.write_manifest(results, all_scenes=scenes)
        return results, manifest


def _render_download(auth, opts, scenes: list[SceneAnalysis]) -> None:
    outcomes: dict[int, SearchOutcome] = _state("outcomes", {})
    selections: dict[int, str] = _state("selections", {})
    uploads: dict[int, Path] = _state("uploads", {})

    items = []
    for scene in scenes:
        if scene.index in uploads:
            continue
        outcome = outcomes.get(scene.index)
        uid = selections.get(scene.index)
        video = next((r for r in outcome.results if r.uid == uid), None) if outcome else None
        if video:
            keyword = st.session_state.get(f"{STATE_PREFIX}q_{scene.index}") or scene.query
            items.append(DownloadItem(scene, video, keyword=keyword))
    customs = [CustomClip(s, uploads[s.index]) for s in scenes if s.index in uploads]

    st.subheader("⬇️ Download")
    c1, c2 = st.columns(2)
    if c1.button("Auto-select top result for unselected scenes"):
        for scene in scenes:
            o = outcomes.get(scene.index)
            if o and o.results and scene.index not in selections:
                selections[scene.index] = o.results[0].uid
        _set("selections", selections)
        for key in [k for k in st.session_state if k.startswith(f"{STATE_PREFIX}pick_")]:
            del st.session_state[key]
        st.rerun()

    premium = sum(1 for i in items if i.video.is_premium)
    st.write(f"{len(items)} stock clip(s) + {len(customs)} custom clip(s) selected "
             f"for {len(scenes)} scene(s).")
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


def render() -> None:
    st.title("🎞️ Script → Stock Video Matcher")
    st.caption("Paste a script, review matched stock footage per sentence, then download.")
    auth = _auth()
    opts = _render_sidebar(auth)

    script = st.text_area("Script", value=_state("script", EXAMPLE_SCRIPT), height=180,
                          help="One scene per sentence or per line. Vietnamese is supported "
                               "(best with an LLM configured).")
    c1, c2 = st.columns(2)
    if c1.button("1️⃣ Analyze script", use_container_width=True):
        _set("script", script)
        try:
            parser = ScriptParser(llm=auth.llm_settings())
            scenes = parser.parse(script, use_llm=opts["use_llm"] or False)
        except Exception as e:
            st.error(f"Analysis failed: {e}")
            scenes = []
        _set("scenes", scenes)
        _set("outcomes", {})
        _set("selections", {})
        for key in [k for k in st.session_state
                    if k.startswith((f"{STATE_PREFIX}q_", f"{STATE_PREFIX}pick_"))]:
            del st.session_state[key]

    scenes: list[SceneAnalysis] = _state("scenes", [])
    if c2.button("2️⃣ Search all scenes", use_container_width=True, disabled=not scenes):
        _search_and_store(auth, opts, scenes)

    if not scenes:
        st.info("Analyze a script to get started.")
        return

    outcomes: dict[int, SearchOutcome] = _state("outcomes", {})
    for scene in scenes:
        _render_scene(scene, outcomes.get(scene.index), opts, auth)
    _render_download(auth, opts, scenes)


if __name__ == "__main__":
    st.set_page_config(page_title="Stock Matcher", page_icon="🎞️", layout="wide")
    render()
