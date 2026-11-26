# Walkthrough videos

Narrated 1920x1080 videos of the four [walkthroughs](../../docs/walkthroughs/index.md), recorded from
the real app. Each film script starts its own HANI2 server(s) on a fresh temporary home, drives the
page in a browser window on a stage, and speaks every line with a local voice; the recording waits
for each line, so picture and voice stay in sync.

| Script | Video | Walkthrough |
|--------|-------|-------------|
| `film_han_basics.py` | `hani2-walkthrough-han-basics.mp4` | Against an AI: the basics |
| `film_han_advanced.py` | `hani2-walkthrough-han-advanced.mp4` | Against an AI: advanced |
| `film_hi_basics.py` | `hani2-walkthrough-hi-basics.mp4` | With an Assistant: the basics |
| `film_hi_advanced.py` | `hani2-walkthrough-hi-advanced.mp4` | With an Assistant: advanced |

## What you need

- The project environment: `uv venv && uv pip install -e ".[dev,e2e]"` (the servers run with
  `.venv/bin/python`).
- The `demo-video` toolkit (`dv.py`, `stage.html`): by default in
  `~/.claude/skills/demo-video/scripts`, or set `HANI2_DV` to its folder. Its `ensure.sh` installs
  ffmpeg, the Kokoro voice model (`~/.cache/kokoro`) and checks for Chrome.
- For the two Assistant films: Ollama with the default model, `ollama pull qwen3:4b-instruct`.

## Run

From the repository root:

```bash
uv run --with kokoro-onnx==0.6.1 --with numpy --with playwright python scripts/videos/film_han_basics.py
```

Add `--show` to watch the recording. Each run writes, in `~/negmas/hani2-videos/` (or `HANI2_VIDEOS`):

- `<name>.mp4`: the video (H.264 and AAC);
- `<name>.srt`: subtitles from the narration;
- `<name>.chapters.txt`: YouTube chapters (paste them into the video's description);
- `work/<name>/`: the recording, the cue log and the cached voice lines (re-runs reuse the voice).

The large files stay outside git. The Assistant's answers come from the language model, so they
differ from take to take: watch the result before publishing.

## Changing a film

The narration is the `N` dictionary at the top of each script; the storyboard below it says what
happens on screen while each line is spoken (`f.say(..., wait=False)` lets actions run under the
voice). `hv.py` holds the shared helpers: the servers, the window, drags, typing, the Assistant
chat, subtitles and chapters (`f.mark("Title")` starts a chapter).
