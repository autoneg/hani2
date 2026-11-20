"""Build the pictures of the bundled scenarios.

Every scene in ``scenes/<Type>.svg`` is a fragment of SVG elements drawn on a
480 x 200 canvas with the class names of the shared palette below (no colours of
its own). This script wraps each scene in a rounded backdrop and writes two
files into the bundled scenario folder:

- ``picture.svg``       — the light version,
- ``picture_dark.svg``  — the dark version (same drawing, night palette).

Run it after changing a scene::

    .venv/bin/python scripts/scenario_pictures/make_pictures.py            # all scenes
    .venv/bin/python scripts/scenario_pictures/make_pictures.py UsedCar    # one scene
    .venv/bin/python scripts/scenario_pictures/make_pictures.py --sheet out.png  # + contact sheet
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENES = HERE / "scenes"
TARGET = HERE.parents[1] / "src" / "hani2" / "sample_scenarios" / "Default"
W, H = 480, 200

# Class -> (light, dark) fill colour. Scenes use only these classes (plus opacity).
PALETTE: dict[str, tuple[str, str]] = {
    # backdrop (gradient stops) and land
    "skyTop": ("#cfe0ff", "#141d36"),
    "skyBottom": ("#f3f6ff", "#28345a"),
    "hill": ("#c9e4cf", "#22344a"),
    "hill2": ("#b3d8bd", "#1d2d40"),
    "ground": ("#e6dccb", "#2b3346"),
    "ground2": ("#d6c8b2", "#232a3b"),
    "water": ("#9cc8ec", "#22466e"),
    "water2": ("#7fb3e0", "#1b3a5e"),
    "sand": ("#f1dfb4", "#5b5038"),
    "floor": ("#ece4d8", "#262d3e"),
    "wall": ("#f6f1ea", "#1f2638"),
    # sky objects
    "sun": ("#ffc94a", "#e9eef8"),
    "sunGlow": ("#ffe8a8", "#3a4670"),
    "cloud": ("#ffffff", "#34406a"),
    "star": ("#ffffff", "#f2f5ff"),
    # neutrals
    "ink": ("#2b3550", "#0f1424"),
    "inkSoft": ("#56617d", "#7b86a3"),
    "paper": ("#ffffff", "#dfe5f2"),
    "paper2": ("#eef1f7", "#b9c2d6"),
    "metal": ("#a9b2c3", "#7d879e"),
    "metal2": ("#7f8aa0", "#5c6680"),
    "glass": ("#bfe0f6", "#6f9cc4"),
    "shadow": ("#1d2740", "#000000"),
    "light": ("#fff6d8", "#ffe7a0"),
    # accents (people, objects)
    "blue": ("#4a6cf0", "#6f86ff"),
    "blue2": ("#2f4bc4", "#4c62d6"),
    "orange": ("#f29a38", "#e8963e"),
    "orange2": ("#d77b1c", "#b8701f"),
    "green": ("#34b483", "#2fa577"),
    "green2": ("#1e8a62", "#1f7a58"),
    "red": ("#e8574b", "#d85448"),
    "red2": ("#b93a30", "#a53a32"),
    "yellow": ("#ffcf4d", "#e6b93f"),
    "purple": ("#8b6cf0", "#8a72e8"),
    "teal": ("#2fb3c2", "#2a9fae"),
    "pink": ("#f29bb6", "#d98aa3"),
    "brown": ("#a4703f", "#8a5f37"),
    "brown2": ("#7a4f2a", "#654325"),
    "wood": ("#d9a86a", "#a98250"),
    "leaf": ("#4fbf73", "#3a9a5c"),
    "leaf2": ("#2f9a57", "#2a7a48"),
    # people
    "skin1": ("#f2c8a6", "#d9ae8c"),
    "skin2": ("#c98d62", "#b07a53"),
    "skin3": ("#8d5a3b", "#7b4e34"),
    "hair": ("#3a2c28", "#1f1715"),
    "hair2": ("#a8642e", "#8a5226"),
}
# Classes drawn only in one theme.
LIGHT_ONLY = ("lightOnly",)
DARK_ONLY = ("star", "darkOnly")


def style(theme: int) -> str:
    rules = [f".{k}{{fill:{v[theme]}}}" for k, v in PALETTE.items()]
    rules += [f".s-{k}{{stroke:{v[theme]}}}" for k, v in PALETTE.items()]
    rules += [f".{k}{{display:none}}" for k in (DARK_ONLY if theme == 0 else LIGHT_ONLY)]
    rules.append(".shadow{opacity:%s}" % ("0.12" if theme == 0 else "0.35"))
    rules.append(".s{fill:none;stroke-linecap:round;stroke-linejoin:round}")
    return "".join(rules)


def wrap(body: str, theme: int, title: str) -> str:
    top, bottom = PALETTE["skyTop"][theme], PALETTE["skyBottom"][theme]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">'
        f"<title>{title}</title>"
        f"<style>{style(theme)}</style>"
        "<defs>"
        f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>'
        f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="18"/></clipPath>'
        "</defs>"
        f'<g clip-path="url(#frame)"><rect width="{W}" height="{H}" fill="url(#bg)"/>{body.strip()}</g>'
        "</svg>\n"
    )


def build(names: list[str]) -> list[Path]:
    out = []
    for f in sorted(SCENES.glob("*.svg")):
        if names and f.stem not in names:
            continue
        dest = TARGET / f.stem
        if not dest.is_dir():
            raise SystemExit(f"no bundled scenario folder {dest}")
        body = f.read_text(encoding="utf-8")
        title = body.split("-->", 1)[0].replace("<!--", "").strip() if body.lstrip().startswith("<!--") else f.stem
        (dest / "picture.svg").write_text(wrap(body, 0, title), encoding="utf-8")
        (dest / "picture_dark.svg").write_text(wrap(body, 1, title), encoding="utf-8")
        out.append(dest)
    return out


def contact_sheet(dirs: list[Path], png: Path) -> None:
    """Every picture on the app's light (#ffffff) and dark (#151b26) card surfaces."""
    with tempfile.TemporaryDirectory() as tmp:
        tiles = []
        for d in dirs:
            for name, bg in (("picture.svg", "#ffffff"), ("picture_dark.svg", "#151b26")):
                p = Path(tmp) / f"{d.name}_{name}.png"
                subprocess.run(["rsvg-convert", "-w", "480", "-b", bg, "-o", str(p), str(d / name)], check=True)
                padded = Path(tmp) / f"{d.name}_{name}_pad.png"
                subprocess.run(["magick", str(p), "-bordercolor", bg, "-border", "12",
                                "-gravity", "North", "-background", bg, "-splice", "0x18",
                                "-font", "/System/Library/Fonts/Supplemental/Arial.ttf", "-fill", "#888", "-pointsize", "14", "-annotate", "+0+2", d.name, str(padded)],
                               check=True)
                tiles.append(str(padded))
        subprocess.run(["magick", "montage", *tiles, "-tile", "2x", "-geometry", "+0+0", str(png)], check=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--sheet", type=Path, help="also write a PNG contact sheet of both versions")
    a = ap.parse_args()
    built = build(a.names)
    print(f"built {len(built)} pictures")
    if a.sheet:
        contact_sheet(built, a.sheet)
        print(f"contact sheet: {a.sheet}")
