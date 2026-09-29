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

## Web UI

Open **Stock Matcher** in the Pixelle-Video web UI (`./start_web.sh`), or run it
standalone:

```bash
uv run streamlit run pixelle_video/stock_matcher/app.py
```

1. Paste the script and click **Analyze script**
2. Edit any query, then **Search all scenes** (or **Re-search** one scene)
3. Pick a clip per scene, or upload your own
4. **Download selected** → clips + `manifest.json` in the output folder

## CLI

```bash
uv run python -m pixelle_video.stock_matcher status
uv run python -m pixelle_video.stock_matcher parse  script.txt
uv run python -m pixelle_video.stock_matcher search script.txt --providers pexels pixabay
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
