# Stock Matcher

Turn a narration script into a folder of stock clips: each sentence becomes a
scene, gets a visual search query, is matched against stock libraries, and the
chosen clips are downloaded as `scene_01_<keyword>.mp4` with a `manifest.json`.

## Setup

```bash
uv pip install python-dotenv tqdm   # optional: .env loading + CLI progress bars
uv pip install anthropic           # optional: only for STOCK_LLM_BACKEND=anthropic
cp .env.example .env           # then fill in at least one provider key
```

Optional, for better English keyword extraction:

```bash
uv pip install spacy && uv run python -m spacy download en_core_web_sm
```

| Provider     | Type    | Credentials                                          |
|--------------|---------|------------------------------------------------------|
| Pexels       | free    | `PEXELS_API_KEY`                                     |
| Pixabay      | free    | `PIXABAY_API_KEY`                                    |
| Mixkit       | free    | none (reads the public search page, best-effort)     |
| Shutterstock | premium | `SHUTTERSTOCK_API_TOKEN` (+ `SHUTTERSTOCK_SUBSCRIPTION_ID`) |
| Storyblocks  | premium | `STORYBLOCKS_PUBLIC_KEY/PRIVATE_KEY/USER_ID/PROJECT_ID` |

Premium providers show watermarked previews in search. Full-resolution files
are obtained through each provider's official licensing / download endpoint,
which counts against your subscription.

## How scenes are matched

1. **Scene analysis.** Each sentence is broken into subject, action, setting,
   time of day, weather, season and mood. Context the script established earlier
   ("that night, in the office...") is carried into later sentences until the
   script changes it, and pronouns ("She smiles") resolve to the previous subject.
   The Web UI marks carried-over values with ↩.
2. **Several queries per scene**, from specific ("girl walking countryside rain")
   to general ("girl"). Stock sites match short, tag-like queries best, so the
   first two run together and more general ones are added only while too few
   clips were found. Without an LLM, Vietnamese scenes are also searched in
   Vietnamese through the providers' language option.
3. **Relevance ranking.** Every clip's tags / description / URL is compared with
   the scene. Matching subject, action, place, time and weather earn points
   (✅ in the UI); contradictions such as a sunny clip for a night-time rain scene
   lose points (⚠️). The provider's own order and the specificity of the query
   add a small bonus. Clips are sorted by this score (⭐ 0-100), so the closest
   clip comes first even when nothing matches exactly.
4. **AI judges thumbnails (optional).** A vision-capable LLM looks at the top
   clips of each scene and rates how well each fits (🤖 0-10). This is the most
   accurate step because free stock sites have sparse tags. It costs LLM tokens.

| Analysis backend | When used                                  | Notes                                   |
|------------------|--------------------------------------------|-----------------------------------------|
| LLM              | `STOCK_LLM_*` set, or `llm` in config.yaml | Best: understands context, translates, writes 3-5 queries |
| spaCy            | `en_core_web_sm` installed                 | POS-based nouns / verbs / adjectives     |
| Heuristic        | always                                     | Word lists (EN + VI) for place, time, weather |

Search results are cached for 24 h in `output/.stock_cache`, so searching the
same script again does not use API quota (Pexels allows 200 requests/hour).

### Free vs premium libraries

Premium libraries (Shutterstock, Storyblocks) have far more clips and detailed
descriptions and keywords, which makes the relevance ranking more precise.
Pexels only exposes a URL slug and Pixabay a few tags, so for them the
"AI judges thumbnails" option makes the biggest difference.

## Desktop app (Windows)

Double-click **`start_stock_matcher.bat`**: it installs dependencies on first
run, creates `.env` if needed and opens Stock Matcher in its own window
(pywebview / Edge WebView2; falls back to an Edge or Chrome app window).
Run **`create_desktop_shortcut.bat`** once to get a "Stock Matcher" icon on the
Desktop.

Other platforms / manually:

```bash
uv run --with pywebview python -m pixelle_video.stock_matcher.desktop
uv run python -m pixelle_video.stock_matcher.desktop --browser   # browser window
uv run streamlit run pixelle_video/stock_matcher/app.py           # plain Streamlit
```

It is also available as the **Stock Matcher** page of the Pixelle-Video web UI.

### Projects and autosave

Each script is a **project** saved in `output/stock_projects/<name>/project.json`
after every step: script, analysis, search results, chosen clips, edited
queries, custom uploads and which scenes were downloaded. Closing the window
or restarting loses nothing; the most recent project reopens automatically.
Switch, create or rename projects in the sidebar. Clips download to
`output/stock_clips/<project>/` by default.

### Using it

The interface is in Vietnamese and has three steps:

1. **📝 Kịch bản** (script): paste the script or import a `.txt` / `.srt` / `.vtt`
   file, then **⚡ Phân tích + Tìm clip** (analyze and search in one click).
2. **🎬 Chọn clip** (choose): every scene shows its best matches with score,
   matched / conflicting context and an AI score when enabled. The best clip is
   used automatically ("Không dùng trùng clip" avoids reusing one clip in two
   scenes); press **Chọn** on another card to change it. Untick a scene to leave
   it out, re-search one scene, or use your own clip.
3. **⬇️ Tải về** (download): buttons on top (**Tải cảnh đã chọn**, **Tải tất cả
   cảnh**, **Mở thư mục**), then options:
   - quality 720p / 1080p / 4K (largest rendition up to that width),
   - one clip per scene, or the chosen clip plus 1-5 alternates
     (`scene_01_..._alt1.mp4`) to choose from while editing,
   - file naming (`scene_01_keyword.mp4`, `scene_01.mp4`, `01.mp4`),
   - output folder, overwrite, `credits.txt` with sources/authors, parallel downloads,
   - a scene table with checkboxes and thumbnails.

A scene already downloaded with the same clip is not fetched again; picking a
different clip replaces the file.

## CLI

```bash
uv run python -m pixelle_video.stock_matcher status
uv run python -m pixelle_video.stock_matcher parse  script.txt
uv run python -m pixelle_video.stock_matcher search script.txt --providers pexels pixabay --top 3
uv run python -m pixelle_video.stock_matcher search script.txt --ai-rerank   # vision LLM
uv run python -m pixelle_video.stock_matcher run    script.txt -o output/clips \
    --pick interactive --orientation landscape
```

## manifest.json

```json
{
  "total_estimated_seconds": 14.4,
  "scenes": [
    {
      "scene": 1,
      "sentence": "An engineer working late at night coding.",
      "search_query": "engineer working coding developer office night",
      "file": "scene_01_engineer_working_coding.mp4",
      "status": "ok",
      "source": {"provider": "Pexels", "id": "42", "page_url": "...", "author": "..."},
      "timing": {"start": 0.0, "end": 2.8, "narration_seconds": 2.8, "clip_seconds": 12.0}
    }
  ]
}
```

Timing is estimated from word count (`--wps`, default 2.5 words/second).

## Error handling

- HTTP 429 / 5xx are retried with exponential backoff (honouring `Retry-After`).
- Missing keys disable that provider with a message naming the variable to set;
  rejected keys (401/403) are reported per provider without stopping others.
