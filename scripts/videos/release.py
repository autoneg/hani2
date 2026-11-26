"""Prepare the four walkthrough videos for YouTube: a release folder with, per video, the title,
the description (with chapters and the link to its written walkthrough), tags, subtitles and a
1280x720 thumbnail, plus a playlist file, the playlist's own text and an upload checklist.

    python scripts/videos/release.py            # writes ~/negmas/hani2-videos/youtube/
    python scripts/videos/release.py --open     # ... and opens the four videos as a playlist (IINA or VLC)

Run it after the films (see README.md); it reads their .mp4, .srt and .chapters.txt files.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

VIDEOS = Path(os.environ.get("HANI2_VIDEOS", Path.home() / "negmas" / "hani2-videos"))
OUT = VIDEOS / "youtube"
DOCS = "https://autoneg.github.io/hani2/walkthroughs"
REPO = "https://github.com/autoneg/hani2"

PLAYLIST_TITLE = "HANI2 walkthroughs: negotiating in the browser"
PLAYLIST_TEXT = (
    "Four short walkthroughs of the HANI2 negotiation page for people who have never negotiated "
    "before: against an AI opponent on your own, and with an AI Assistant on your side, against an AI "
    "or another person. Start with the basics, then watch the advanced videos.\n\n"
    f"Written walkthroughs: {DOCS}/\nHANI2: {REPO}"
)

COMMON_TAGS = ["negotiation", "HANI2", "human-agent negotiation", "tutorial", "walkthrough",
               "AI negotiation", "negotiation training", "negmas"]

#: (file stem, title, summary, written walkthrough page, extra tags, a note about the recording)
FILMS = [
    ("hani2-walkthrough-han-basics", "Negotiating against an AI: the basics | HANI2 walkthrough 1",
     ("Your first negotiation in HANI2, explained for someone who has never negotiated. We read the "
     "scenario and your preferences, explain every word on the screen (offer, utility, value on "
     "disagreement, deadline), make a counter-offer, and end with a deal."),
     "han-basics", ["HAN", "beginner"], None),
    ("hani2-walkthrough-han-advanced", "Negotiating against an AI: advanced | HANI2 walkthrough 2",
     ("The tools that help you negotiate against an AI opponent: the Utility Bar that finds deals by "
     "what they are worth to you, the Tools menu, reading the opponent from its offers, the deadline, "
     "the views of the page and your own settings, such as utility bars coloured by issue."),
     "han-advanced", ["HAN", "Utility Bar"], None),
    ("hani2-walkthrough-hi-basics", "Negotiating with an AI Assistant: the basics | HANI2 walkthrough 3",
     ("Negotiating with help: open the Assistant, ask it questions in plain words, let it fill in a "
     "counter-offer that you check and send, and switch it off when you want. Then negotiate against "
     "another person: choose a person or an AI, wait for a partner and take turns."),
     "hi-basics", ["HI", "hybrid intelligence", "AI assistant", "human opponents"],
     "The Assistant's answers come from a small local language model (qwen3:4b-instruct)."),
    ("hani2-walkthrough-hi-advanced", "Negotiating with an AI Assistant: advanced | HANI2 walkthrough 4",
     ("More from the Assistant: choose your scenario and opponent, decide how much the Assistant may do "
     "(Suggest, Semi, Full), ask it what the opponent cares about, use its estimate of the opponent in "
     "the Negotiation Plot and the Utility-based Selector, and see it take the place of the tools."),
     "hi-advanced", ["HI", "hybrid intelligence", "AI assistant", "opponent modeling"],
     "The Assistant's answers come from a small local language model (qwen3:4b-instruct)."),
]


def duration(mp4: Path) -> float:
    out = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", str(mp4)])
    return float(out)


def thumbnail(mp4: Path, png: Path, at: float = 4.0) -> None:
    """A 1280x720 frame of the title card (YouTube's thumbnail size)."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(mp4), "-frames:v", "1",
                    "-vf", "scale=1280:720", str(png)], check=True)


def description(summary: str, page: str, chapters: str, note: str | None, n: int) -> str:
    parts = [summary, "",
             f"Read the written walkthrough, with screenshots: {DOCS}/{page}/",
             f"All four walkthroughs: {DOCS}/", "",
             "Chapters", chapters.strip(), ""]
    others = [f"{i + 1}. {t.split(' | ')[0]}" for i, (_, t, *_) in enumerate(FILMS) if i != n]
    parts += ["The other walkthroughs in this series:", *others, ""]
    parts += [("Recorded from the real HANI2 app, in its default simple view, with the Apartment Lease "
              "scenario. Narration by a synthetic voice; subtitles included.")]
    if note:
        parts.append(note)
    parts += ["", f"HANI2, a web interface for human-agent negotiation: {REPO}"]
    return "\n".join(parts) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--open", action="store_true", help="open the four videos as a playlist")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    playlist = ["#EXTM3U", f"#PLAYLIST:{PLAYLIST_TITLE}"]
    checklist = [f"# Upload checklist: {PLAYLIST_TITLE}", "",
                 "0. Merge and deploy the docs first: every description links to its written walkthrough",
                 f"   under {DOCS}/, which exists only once the walkthrough pages are published.",
                 "1. Create the playlist (public or unlisted) with the title and text in `playlist.txt`.",
                 "2. Upload each video below in order. For each one:",
                 "   - title from `title.txt`, description from `description.txt` (it holds the chapters),",
                 "   - tags from `tags.txt`, thumbnail `thumbnail.png`,",
                 "   - Subtitles: upload `<name>.en.srt` as English;",
                 "   - Audience: not made for kids; category: Education; add it to the playlist.",
                 "3. Replace the placeholder in each docs page (`YOUTUBE-LINK-PLACEHOLDER` in",
                 "   `docs/walkthroughs/*.md`) with the video's link, and fill the `[links]` below.",
                 "", "| # | Video | Length | Docs page | YouTube link |", "|---|---|---|---|---|"]
    missing = []
    for n, (stem, title, summary, page, tags, note) in enumerate(FILMS):
        mp4 = VIDEOS / f"{stem}.mp4"
        if not mp4.exists():
            missing.append(mp4.name)
            continue
        d = OUT / f"{n + 1}-{stem}"
        d.mkdir(exist_ok=True)
        chapters = (VIDEOS / f"{stem}.chapters.txt").read_text(encoding="utf-8")
        (d / "title.txt").write_text(title + "\n", encoding="utf-8")
        (d / "description.txt").write_text(description(summary, page, chapters, note, n), encoding="utf-8")
        (d / "tags.txt").write_text(", ".join(COMMON_TAGS + tags) + "\n", encoding="utf-8")
        shutil.copyfile(VIDEOS / f"{stem}.srt", d / f"{stem}.en.srt")
        thumbnail(mp4, d / "thumbnail.png")
        secs = duration(mp4)
        playlist += [f"#EXTINF:{int(secs)},{title}", str(mp4)]
        checklist.append(f"| {n + 1} | `{mp4}` | {int(secs) // 60}:{int(secs) % 60:02d} | "
                         f"docs/walkthroughs/{page}.md | [link] |")
        print(f"{n + 1}. {title}  ({int(secs) // 60}:{int(secs) % 60:02d})  -> {d}")
    (OUT / "playlist.m3u").write_text("\n".join(playlist) + "\n", encoding="utf-8")
    (OUT / "playlist.txt").write_text(f"{PLAYLIST_TITLE}\n\n{PLAYLIST_TEXT}\n", encoding="utf-8")
    (OUT / "UPLOAD.md").write_text("\n".join(checklist) + "\n", encoding="utf-8")
    print("wrote", OUT)
    if missing:
        print("missing (record them first):", ", ".join(missing), file=sys.stderr)
    if a.open:
        player = next((p for p in ("/Applications/IINA.app", "/Applications/VLC.app") if Path(p).exists()), None)
        cmd = ["open", "-a", player, str(OUT / "playlist.m3u")] if player else ["open", str(OUT / "playlist.m3u")]
        subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
