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

## Keyword extraction

| Backend   | When used                                  | Notes                                   |
|-----------|--------------------------------------------|-----------------------------------------|
| LLM       | `STOCK_LLM_*` set, or `llm` in config.yaml | Best quality; translates Vietnamese etc. |
| spaCy     | `en_core_web_sm` installed                 | POS-based nouns / verbs / adjectives     |
| Heuristic | always                                     | Stopwords + suffix rules, small VI glossary |

If a query returns nothing, it is simplified automatically:
full query → without adjectives → core nouns → main noun.

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
