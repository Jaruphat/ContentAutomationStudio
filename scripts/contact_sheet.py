"""Every take in a project on one page, numbered by shot.

Reviewing seventy-nine stills one at a time in the browser is how a doubled
character or a stray hand reaches the cut: the eye stops seeing after about
twenty. Laid out in a grid at thumbnail size, the frames that do not belong to
the film are visible in a second - a background that changed colour, a figure
that grew a second copy of itself, a surface with lettering on it.

The number under each frame is the shot's order, so a defect found here names
the shot to re-make without going and looking it up.

Usage::

    python scripts/contact_sheet.py <project-id> [--out sheet.png] [--cols 6]
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw

API = "http://127.0.0.1:8001/api"
#: Wide enough to judge a silhouette and a background, small enough that a
#: nine-minute episode is one page.
THUMB_W = 320


def _get(url: str):
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def shots_in_order(project_id: str) -> list[dict]:
    scenes = _get(f"{API}/projects/{project_id}/scenes")
    shots: list[dict] = []
    for scene in scenes:
        shots.extend(
            _get(f"{API}/projects/{project_id}/scenes/{scene['id']}/shots")
        )
    return sorted(shots, key=lambda shot: shot.get("order") or 0)


def latest_take_path(project_id: str, shot_id: str) -> str:
    """The newest take for a shot, or an empty string if it has none yet."""
    takes = [
        take
        for take in _get(f"{API}/projects/{project_id}/takes?limit=500")
        if take.get("shot_id") == shot_id and take.get("file_path")
    ]
    if not takes:
        return ""
    return sorted(takes, key=lambda take: take.get("created_at") or "")[-1]["file_path"]


def build(project_id: str, out_path: Path, cols: int) -> None:
    shots = shots_in_order(project_id)
    takes = _get(f"{API}/projects/{project_id}/takes?limit=500")
    newest: dict[str, str] = {}
    for take in sorted(takes, key=lambda t: t.get("created_at") or ""):
        if take.get("file_path"):
            newest[take.get("shot_id")] = take["file_path"]

    tiles: list[tuple[int, Image.Image | None]] = []
    for shot in shots:
        path = newest.get(shot["id"], "")
        image: Image.Image | None = None
        if path:
            try:
                image = Image.open(path).convert("RGB")
            except OSError:
                image = None
        tiles.append((shot.get("order") or 0, image))

    if not tiles:
        raise SystemExit("This project has no shots.")

    # The first real frame sets the cell shape, so a 16:9 film and a 9:16 film
    # both come out as a grid of correctly proportioned cells.
    sample = next((im for _, im in tiles if im is not None), None)
    if sample is None:
        raise SystemExit("No take has produced a readable file yet.")
    ratio = sample.height / sample.width
    cell = (THUMB_W, int(THUMB_W * ratio))
    label_h = 18

    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new(
        "RGB", (cols * cell[0], rows * (cell[1] + label_h)), (24, 24, 27)
    )
    draw = ImageDraw.Draw(sheet)
    for index, (order, image) in enumerate(tiles):
        x = (index % cols) * cell[0]
        y = (index // cols) * (cell[1] + label_h)
        if image is not None:
            sheet.paste(image.resize(cell), (x, y))
        else:
            draw.rectangle([x, y, x + cell[0], y + cell[1]], fill=(60, 20, 20))
            draw.text((x + 8, y + 8), "no take", fill=(240, 200, 200))
        draw.text((x + 6, y + cell[1] + 3), f"{order}", fill=(200, 200, 210))

    sheet.save(out_path)
    missing = sum(1 for _, im in tiles if im is None)
    print(f"{len(tiles)} shots, {missing} without a take -> {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id")
    parser.add_argument("--out", default="contact_sheet.png")
    parser.add_argument("--cols", type=int, default=6)
    args = parser.parse_args()
    build(args.project_id, Path(args.out), args.cols)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
