# Demo: "Mỗi ngày 10 trang sách" (HyperFrames)

A 16 s, 1080x1920 motion-graphics video built with [HyperFrames](https://github.com/heygen-com/hyperframes)
(HTML + GSAP rendered to MP4) as a proof of concept for adding animated scenes to Pixelle-Video.
Rendered result: `output.mp4`.

- `index.html`: the composition (3 scenes, captions, progress bar, 4 audio tracks).
- `assets/vo1-3.mp3`: Vietnamese voiceover from edge-tts, voice `vi-VN-HoaiMyNeural` (regenerate with `tts.py`).
- `assets/bgm.mp3`: first 16 s of `bgm/default.mp3` with fades.
- `assets/Inter-*.otf`: Inter font (SIL OFL), includes Vietnamese glyphs.

Run (Node >= 22, ffmpeg, Chromium):

```bash
cd motion/demo-10-trang-sach
npm run check    # lint + layout + contrast; must pass
npm run dev      # preview in the browser
npm run render   # -> renders/*.mp4 (~50 s on CPU)
```

Agent guidance for writing compositions lives in `.claude/skills/hyperframes*` and in this folder's `CLAUDE.md`.

## Next step: integrate into Pixelle-Video

Today each Pixelle scene is a static screenshot: `HTMLFrameGenerator.generate_frame`
(`pixelle_video/services/frame_html.py`) renders the template to one PNG, and
`FrameProcessor._step_create_video_segment` (`pixelle_video/services/frame_processor.py`) turns
that PNG plus the narration audio into a clip. Proposed change:

1. Add a new template kind, e.g. `templates/1080x1920/motion_*.html`: a HyperFrames composition
   that keeps Pixelle's `{{title}}`, `{{text}}`, `{{image}}` placeholders and gets its root
   `data-duration` from the narration length.
2. In `FrameProcessor`, when the template is a motion template: fill the placeholders, write the
   project to the task folder, run `npx hyperframes render`, then attach narration with the existing
   `VideoService.merge_audio_video`. Static templates keep the current path unchanged.
3. Give the AI image a slow Ken Burns move and animate title/caption entrances (see the
   `hyperframes-keyframes` and `hyperframes-animation` skills).
4. Add Node 22 to the Dockerfile. Expect render time per scene of roughly 3 s per second of video on CPU.
