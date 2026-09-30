"""
Command-line interface.

    python -m pixelle_video.stock_matcher parse  script.txt
    python -m pixelle_video.stock_matcher search script.txt --providers pexels pixabay
    python -m pixelle_video.stock_matcher run    script.txt -o output/stock --pick interactive
"""

import argparse
import asyncio
import sys
from pathlib import Path

from loguru import logger

from .auth_manager import AuthManager
from .downloader import Downloader
from .llm_extractor import check_connection
from .models import DownloadItem, SearchOutcome
from .nlp_parser import ScriptParser, scenes_to_json
from .stock_searcher import DEFAULT_PROVIDERS, PROVIDER_CLASSES, StockSearchEngine
from .vision_ranker import rerank_outcomes


def _read_script(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _llm_flag(args) -> bool | None:
    return {"auto": None, "on": True, "off": False}[args.llm]


def _parse(args, auth: AuthManager):
    parser = ScriptParser(llm=auth.llm_settings(), use_spacy=not args.no_spacy)
    return parser.parse(_read_script(args.script), use_llm=_llm_flag(args))


def _print_outcome(o: SearchOutcome, limit: int) -> None:
    s = o.scene
    print(f"\n[{s.index:02d}] {s.sentence}")
    context = [("setting", ", ".join(s.setting)), ("time", s.time_of_day),
               ("weather", s.weather), ("season", s.season)]
    print("     context: " + (", ".join(f"{k}={v}" for k, v in context if v) or "-"))
    print(f"     queries: {' | '.join(o.tried_queries)}")
    for provider, err in o.errors.items():
        print(f"     ! {provider}: {err}")
    if not o.results:
        print("     (no results)")
    for i, r in enumerate(o.results[:limit], start=1):
        tag = " [premium]" if r.is_premium else ""
        ai = f" ai={r.ai_score:.0f}" if r.ai_score is not None else ""
        print(f"     {i:>2}. score={r.score:>5.1f}{ai} {r.provider:<12} {r.duration:>5.1f}s"
              f" {r.width}x{r.height}{tag}  {r.title[:50]}  {r.page_url or r.preview_url}")
        if r.matched_terms or r.conflicts:
            print(f"         match: {', '.join(r.matched_terms) or '-'}"
                  + (f"   conflicts: {', '.join(r.conflicts)}" if r.conflicts else ""))


def _pick(outcomes: list[SearchOutcome], mode: str, limit: int) -> list[DownloadItem]:
    items = []
    for o in outcomes:
        if not o.results:
            continue
        if mode == "first":
            items.append(DownloadItem(o.scene, o.results[0]))
            continue
        _print_outcome(o, limit)
        choice = input(f"  Pick 1-{min(limit, len(o.results))}, Enter=1, s=skip: ").strip().lower()
        if choice == "s":
            continue
        idx = int(choice) - 1 if choice.isdigit() else 0
        items.append(DownloadItem(o.scene, o.results[max(0, min(idx, len(o.results) - 1))]))
    return items


def _tqdm_progress():
    try:
        from tqdm import tqdm
    except ImportError:
        return None, lambda: None
    bars: dict[int, "tqdm"] = {}

    def update(scene: int, done: int, total: int):
        bar = bars.get(scene)
        if bar is None:
            bar = bars[scene] = tqdm(total=total or None, unit="B", unit_scale=True,
                                     desc=f"scene {scene:02d}", position=len(bars), leave=True)
        bar.n = done
        bar.refresh()

    return update, lambda: [b.close() for b in bars.values()]


def _engine(args, auth) -> StockSearchEngine:
    return StockSearchEngine(
        auth, providers=args.providers, orientation=args.orientation,
        min_duration=args.min_duration, max_width=args.max_width,
        cache_dir=None if args.no_cache else args.cache_dir,
        words_per_second=getattr(args, "wps", 2.5),
    )


async def _search_all(args, auth, engine: StockSearchEngine, scenes):
    for name, reason in engine.skipped.items():
        print(f"! {name} skipped: {reason}", file=sys.stderr)
    outcomes = await engine.search_scenes(scenes, per_page=args.per_page)
    if args.ai_rerank:
        llm = auth.llm_settings()
        if not llm.enabled:
            print("! --ai-rerank needs an LLM (STOCK_LLM_*)", file=sys.stderr)
        else:
            def report(o, done, total, error):
                print(f"  AI judged {done}/{total}" + (f"  ! scene {o.scene.index}: {error}"
                                                       if error else ""), file=sys.stderr)

            await rerank_outcomes(llm, outcomes, top_n=args.ai_top_n, on_done=report)
    return outcomes


async def cmd_search(args, auth):
    scenes = _parse(args, auth)
    async with _engine(args, auth) as engine:
        outcomes = await _search_all(args, auth, engine, scenes)
    for o in outcomes:
        _print_outcome(o, args.top)


async def cmd_run(args, auth):
    scenes = _parse(args, auth)
    async with _engine(args, auth) as engine:
        outcomes = await _search_all(args, auth, engine, scenes)
        items = _pick(outcomes, args.pick, args.top)
        if not items:
            print("Nothing selected for download.")
            return
        downloader = Downloader(engine, Path(args.output), max_parallel=args.parallel,
                                overwrite=args.overwrite, words_per_second=args.wps)
        on_progress, close = _tqdm_progress()
        try:
            results = await downloader.download(items, on_progress=on_progress)
        finally:
            close()
        manifest = downloader.write_manifest(results, all_scenes=scenes)
    ok = sum(r.ok for r in results)
    print(f"\nDownloaded {ok}/{len(results)} clips -> {args.output}")
    for r in results:
        if not r.ok:
            print(f"  ! scene {r.scene.index:02d}: {r.error}")
    print(f"Manifest: {manifest}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="stock-matcher",
                                description="Match a video script to stock footage.")
    p.add_argument("--env-file", default=None, help="Path to .env (default: ./.env)")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("script", help="Script text file, or - for stdin")
        sp.add_argument("--llm", choices=["auto", "on", "off"], default="auto",
                        help="LLM extraction (auto = use when configured)")
        sp.add_argument("--no-spacy", action="store_true", help="Force heuristic parser")

    sp = sub.add_parser("parse", help="Show extracted scenes and queries as JSON")
    common(sp)

    for name, help_text in (("search", "Search and list matches"),
                            ("run", "Search, pick and download clips")):
        sp = sub.add_parser(name, help=help_text)
        common(sp)
        sp.add_argument("--providers", nargs="+", default=DEFAULT_PROVIDERS,
                        choices=list(PROVIDER_CLASSES))
        sp.add_argument("--per-page", type=int, default=8,
                        help="Clips fetched per query and provider (candidates)")
        sp.add_argument("--top", type=int, default=3, help="Best clips shown per scene")
        sp.add_argument("--orientation", choices=["landscape", "portrait", "square"])
        sp.add_argument("--min-duration", type=float, default=0.0)
        sp.add_argument("--max-width", type=int, default=1920)
        sp.add_argument("--ai-rerank", action="store_true",
                        help="Let a vision LLM judge thumbnails of the top clips")
        sp.add_argument("--ai-top-n", type=int, default=8)
        sp.add_argument("--cache-dir", default="output/.stock_cache")
        sp.add_argument("--no-cache", action="store_true")
        if name == "run":
            sp.add_argument("-o", "--output", default="output/stock_clips")
            sp.add_argument("--pick", choices=["first", "interactive"], default="first")
            sp.add_argument("--parallel", type=int, default=3)
            sp.add_argument("--overwrite", action="store_true")
            sp.add_argument("--wps", type=float, default=2.5,
                            help="Narration words per second for manifest timing")

    sub.add_parser("status", help="Show which providers / LLM are configured")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if args.verbose else "WARNING")
    auth = AuthManager(env_file=args.env_file)

    if args.command == "status":
        for provider, st in auth.status().items():
            mark = "ok " if st["configured"] else "-- "
            detail = "" if st["configured"] else f"missing {', '.join(st['missing'])}"
            print(f"{mark}{provider:<13}{detail}")
        llm = auth.llm_settings()
        if not llm.enabled:
            print("LLM: not configured")
            return 0
        print(f"LLM: {llm.backend} / {llm.model} @ {llm.base_url or 'default URL'}")
        try:
            print(f"LLM test reply: {check_connection(llm)[:80]}")
        except Exception as e:
            print(f"LLM test FAILED: {e}")
            return 1
        return 0
    try:
        if args.command == "parse":
            print(scenes_to_json(_parse(args, auth)))
        elif args.command == "search":
            asyncio.run(cmd_search(args, auth))
        elif args.command == "run":
            asyncio.run(cmd_run(args, auth))
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
