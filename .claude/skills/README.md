# Vendored motion-design skills

Claude Code skills for making motion graphics / animated video from code. Claude Code
loads them automatically when this repo is opened.

| Skill dir | Source | Commit | License |
| --- | --- | --- | --- |
| `hyperframes`, `hyperframes-core`, `hyperframes-cli`, `hyperframes-animation`, `hyperframes-creative`, `hyperframes-keyframes`, `hyperframes-audio`, `hyperframes-registry`, `media-use`, `faceless-explainer`, `motion-graphics`, `general-video` | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes) `skills/` | `3aa6886` | Apache-2.0 (`LICENSE.hyperframes`) |
| `motion-design-code` (upstream name `motion-design`) | [howseen-ai/claude-motion-design](https://github.com/howseen-ai/claude-motion-design) `skill/motion-design` | `3d90d34` | MIT |
| `motion-principles` (upstream name `motion-design`) | [LottieFiles/motion-design-skill](https://github.com/LottieFiles/motion-design-skill) `skills/motion-design` | `f9a8a04` | MIT |

The two upstream `motion-design` skills were renamed (directory and `name:` field) so they
don't collide. HyperFrames `*.test.mjs` files were dropped.

Only the HyperFrames core set plus the workflows that fit Pixelle-Video's narrated videos
are vendored. The `/hyperframes` router installs other workflows (slideshow, music-to-video,
product-launch-video, …) on demand with `npx hyperframes skills update <workflow>`.

Requirements: Node >= 22, ffmpeg, Chromium (Playwright). `motion-design-code` scripts also
need Python with numpy; its `mcp21_client.py`, `mixkit_sfx_search.py` and `svgl_logos.py`
call external sites (21st.dev, mixkit.co, svgl.app).

To update, re-copy the directories from a newer upstream commit and update the table.
