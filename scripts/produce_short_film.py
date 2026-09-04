"""Produce 'The Cartographer of Small Things' through the studio's own API.

Nothing here reaches around the application: the character set, the shots, the
generation queue, review, the timeline and the render are all driven over HTTP
exactly as the cockpit drives them. If a step is impossible through the API it
is impossible for a user too, and worth knowing.

Reference-to-video is the route. It takes the approved canonical views and
composes each scene itself, which measured four times faster here than making
a key image and animating it (80s against 349s per shot) and skips the key
image entirely - the difference between a film that finishes overnight and one
that does not.

The run is resumable. Every completed step is written to a state file, so a
crash, a restart or a cancelled run picks up where it stopped rather than
paying for the same shots twice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE = os.environ.get("CAS_E2E_BASE", "http://127.0.0.1:8001")
WF_T2I = os.environ.get("CAS_FILM_WF_T2I", "359c2852-f880-430f-a096-07e6ef5625a3")
# One reference, not two. Shown two canonical views of the same person, the
# model sometimes draws two people; one view is enough to hold the identity.
WF_R2V = os.environ.get("CAS_FILM_WF_R2V", "93b30e2e-fff1-40e2-b80c-a2300e5511d3")

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "data" / "film"
STATE_PATH = OUT / "state.json"

TITLE = "The Cartographer of Small Things"

#: A held composition and slow drift is the grammar this generator is good at,
#: so every shot names one, and the look is repeated in each prompt rather than
#: assumed - the model sees one shot at a time and remembers nothing.
LOOK = (
    "painterly 2D animation, warm ink linework over muted watercolour, "
    "overcast northern light, deep teal and paper-white palette with one warm "
    "accent, film grain, slow gentle camera drift, no text, no captions"
)

CHARACTER = {
    "name": "Ilva Reim",
    "appearance": (
        "woman in her late twenties, short copper hair cut blunt at the jaw, "
        "round brass-rimmed glasses, pale freckled skin, calm serious face"
    ),
    "proportions": "slight, upright, narrow shoulders",
    "wardrobe": (
        "slate-blue wool coat over a high-necked cream shirt, ink-stained "
        "fingers, canvas satchel of rolled paper"
    ),
    "palette": "slate blue, cream, copper, brass",
    "identity_tokens": "same woman, consistent face, consistent copper hair and glasses",
    "negative_tokens": "different face, changed hair colour, no glasses, extra limbs, text, watermark",
}

# (narration for the subtitle track, what the shot shows)
SHOTS: list[tuple[str, str]] = [
    ("They gave her the smallest desk in the survey office, and told her to map whatever nobody else wanted.",
     "Ilva sits alone at a cramped wooden desk under a single lamp in a vast dim drafting hall, tall windows behind her"),
    ("So she mapped the crack in a teacup.",
     "close on Ilva's ink-stained hands drawing a hairline crack in a white teacup, fine pen, lamplight"),
    ("She mapped where the light fell at four in the afternoon, and how it moved by winter.",
     "a shaft of afternoon light crossing a worn wooden floor, chalk marks tracking its edge, dust in the air"),
    ("She mapped one ant's road across a courtyard, and gave it a name.",
     "Ilva crouched low on wet cobblestones in a stone courtyard, tiny chalk lines drawn around her, coat hem trailing"),
    ("The other cartographers mapped coastlines. Their work was hung in halls.",
     "a grand gallery of enormous framed coastline maps, small figures in dark coats admiring them, high ceiling"),
    ("Hers was kept in a drawer that stuck.",
     "a jammed wooden archive drawer crammed with small rolled paper maps, dust, dim storeroom"),
    ("Twelve years. Nine hundred maps of things too small to matter.",
     "Ilva a little older standing among towering stacks of small paper scrolls in a narrow archive aisle"),
    ("Then the river came.",
     "dark floodwater rising fast along a narrow stone street at night, lamplight reflecting on the surface"),
    ("It took the harbour, the market, the street where she was born.",
     "floodwater covering a market square at dawn, half-submerged awnings and overturned crates, grey water"),
    ("When the water went down, the city was still there. But it was not the same city.",
     "grey mud-covered empty streets at dawn, colour drained from everything, still water in the gutters"),
    ("The great maps still showed the coastline. Coastlines had not changed.",
     "the grand map gallery empty and silted, the enormous coastline maps still hanging intact above the mud"),
    ("What was gone was smaller than a coastline.",
     "Ilva standing alone in the ruined market square looking down at her open hands, grey light"),
    ("The angle of a doorway. The name a family painted above a shop.",
     "a broken stone doorframe with faded hand-painted lettering above it, barely legible, wet plaster"),
    ("Where the light fell at four in the afternoon.",
     "the same worn wooden floor now bare and water-wrecked, no chalk marks left, cold flat light"),
    ("So they came, at last, to the drawer that stuck.",
     "officials in dark coats forcing open the jammed archive drawer by lamplight, dust rising"),
    ("And in nine hundred small maps, they found the city.",
     "hundreds of small paper maps spread edge to edge across an enormous table, figures leaning over them"),
    ("Every doorway. Every sign. Every path an ant had taken across a courtyard.",
     "close on one delicate hand-inked map of a courtyard with a single winding route traced across it"),
    ("They rebuilt from her drawer.",
     "wooden scaffolding rising against a half-rebuilt stone street, workers holding small paper maps up to the walls"),
    ("Not from the coastlines. From the crack in a teacup.",
     "a rebuilt shopfront with its painted sign restored exactly, Ilva standing in the street watching it"),
    ("She never got the large desk. She said she did not want it.",
     "Ilva back at the same small wooden desk in the drafting hall, quietly working, warm lamp"),
    ("She said the small desk was closer to the small things.",
     "close on Ilva's hands drawing by warm lamplight, her brass glasses catching the light, faint smile"),
    ("There is a child in the survey office now, mapping the shadow of a railing.",
     "a young girl in a wool coat crouched on a stone step with chalk, carefully drawing the shadow of an iron railing"),
    ("Nobody has told her it does not matter.",
     "wide shot of the girl small in a great sunlit drafting hall, morning light through tall windows, hopeful"),
]


class FilmError(RuntimeError):
    """A step that cannot be completed through the application's own API."""


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def call(method: str, path: str, *, expect: int | tuple[int, ...] = 200, **kw: Any) -> Any:
    timeout = kw.pop("timeout", 60)
    response = requests.request(method, f"{BASE}{path}", timeout=timeout, **kw)
    allowed = (expect,) if isinstance(expect, int) else expect
    if response.status_code not in allowed:
        raise FilmError(f"{method} {path} -> {response.status_code}: {response.text[:400]}")
    return response.json() if response.content else None


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def wait_for_jobs(pid: str, job_ids: list[str], budget: float) -> list[dict]:
    """Poll until every job settles, reporting the live progress as it goes."""
    deadline = time.time() + budget
    terminal = {"Completed", "Failed", "Cancelled"}
    last_note = ""
    while time.time() < deadline:
        jobs = [j for j in call("GET", f"/api/projects/{pid}/jobs") if j["id"] in job_ids]
        done = sum(1 for j in jobs if j["status"] in terminal)
        running = next((j for j in jobs if j["status"] == "Running"), None)
        note = (
            f"{done}/{len(job_ids)} settled"
            + (f" · {running.get('progress_stage') or 'running'}"
               f" {round((running.get('progress') or 0) * 100)}%" if running else "")
        )
        if note != last_note:
            log(note)
            last_note = note
        if jobs and done == len(job_ids):
            return jobs
        time.sleep(10)
    raise FilmError(f"jobs did not settle within {budget}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shots", type=int, default=len(SHOTS),
                        help="Produce only the first N shots; use a small number to pilot.")
    parser.add_argument("--seconds", type=float, default=8.0, help="Length of each shot.")
    parser.add_argument("--reset", action="store_true", help="Start a new project rather than resume.")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    state = {} if args.reset else load_state()
    shots_wanted = SHOTS[: args.shots]

    # -- project ---------------------------------------------------------
    if "project_id" not in state:
        project = call("POST", "/api/projects", expect=201, json={
            "title": TITLE,
            "objective": "A three-minute narrated short about the value of small work.",
            # 864x480 is 1.8:1, within a percent of cinema's 1.85:1, and both
            # sides are multiples of 32 as H3 wants. It is also the size this
            # machine was measured at.
            "aspect_ratio": "9:5", "target_resolution": "864x480", "frame_rate": 24.0,
            "target_duration_sec": args.seconds * len(shots_wanted),
            "default_video_workflow_id": WF_R2V,
            "language": "en",
        })
        state["project_id"] = project["id"]
        save_state(state)
        log(f"project {project['id']}")
    pid = state["project_id"]

    # -- canonical character ---------------------------------------------
    if "character_set_id" not in state:
        cset = call("POST", f"/api/projects/{pid}/character-sets", expect=201, json=CHARACTER)
        version = call("POST", f"/api/projects/{pid}/character-sets/{cset['id']}/versions",
                       expect=201, json={"slots": ["full_body", "front", "three_quarter"]})
        log("generating the canonical character sheet…")
        started = time.time()
        generated = call(
            "POST",
            f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/generate",
            timeout=1800,
            json={"provider_id": "comfyui", "model": "workflow", "workflow_id": WF_T2I,
                  "seed": 20260905, "width": 768, "height": 768,
                  "confirm_paid_generation": False},
        )
        missing = [v["slot"] for v in generated["views"] if not v.get("reference_image_id")]
        if missing:
            raise FilmError(f"canonical views failed: {missing}")
        call("POST",
             f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/approve")
        state["character_set_id"] = cset["id"]
        save_state(state)
        log(f"canonical set approved in {time.time() - started:.0f}s")
    set_id = state["character_set_id"]

    # -- scene and shots --------------------------------------------------
    if "scene_id" not in state:
        scene = call("POST", f"/api/projects/{pid}/scenes", expect=201,
                     json={"order": 1, "title": "The Cartographer", "purpose": TITLE})
        state["scene_id"] = scene["id"]
        save_state(state)
    sid = state["scene_id"]

    shot_ids: list[str] = state.get("shot_ids", [])
    if len(shot_ids) < len(shots_wanted):
        for index in range(len(shot_ids), len(shots_wanted)):
            narration, description = shots_wanted[index]
            shot = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots", expect=201, json={
                "order": index + 1,
                "subject": CHARACTER["name"],
                "action": description,
                "planned_duration_sec": args.seconds,
                "generation_mode": "video",
                # The subtitle track is built from this field, so the narration
                # lives here and nowhere else.
                "dialogue": narration,
                "video_prompt": (
                    f"{description}. {LOOK}. "
                    "Keep the woman in the reference images identical: same face, "
                    "same copper hair, same brass glasses, same slate-blue coat."
                ),
                "character_set_ids": [set_id],
                "workflow_preset_id": WF_R2V,
                "image_provider_id": "comfyui", "image_model": "workflow",
            })
            shot_ids.append(shot["id"])
            state["shot_ids"] = shot_ids
            save_state(state)
        log(f"{len(shot_ids)} shots written")

    # -- generate, one shot at a time so a failure costs one shot ----------
    done: dict[str, str] = state.get("approved_takes", {})
    for index, shot_id in enumerate(shot_ids, start=1):
        if shot_id in done:
            continue
        log(f"shot {index}/{len(shot_ids)}: generating")
        started = time.time()
        jobs = call("POST", f"/api/projects/{pid}/generate",
                    json={"shot_ids": [shot_id], "confirm_paid_generation": False})
        settled = wait_for_jobs(pid, [j["id"] for j in jobs], budget=2400)
        failed = [j for j in settled if j["status"] != "Completed"]
        if failed:
            raise FilmError(
                f"shot {index} failed: {failed[0].get('error_message')!r}. "
                f"State is saved; rerun to resume from here."
            )
        takes = call("GET", f"/api/shots/{shot_id}/takes")
        if not takes:
            raise FilmError(f"shot {index} completed with no take")
        approved = call("POST", f"/api/takes/{takes[0]['id']}/approve")
        done[shot_id] = approved["id"]
        state["approved_takes"] = done
        save_state(state)
        log(f"shot {index}/{len(shot_ids)}: approved in {time.time() - started:.0f}s")

    # -- timeline and render ----------------------------------------------
    timeline = call("POST", f"/api/projects/{pid}/timeline/build", json={})
    log(f"timeline: {timeline.get('item_count')} items, "
        f"{timeline.get('total_duration_sec')}s")

    call("PUT", f"/api/projects/{pid}/subtitles", json={
        "mode": "burn_in", "preset": "cinematic", "position": "bottom",
    }, expect=(200, 404))

    log("rendering…")
    started = time.time()
    render = call("POST", f"/api/projects/{pid}/render", json={}, timeout=3600,
                  expect=(200, 201, 409))
    state["render"] = render
    save_state(state)
    log(f"render finished in {time.time() - started:.0f}s: "
        f"{render.get('output_path') or render.get('reason')}")

    print(json.dumps({
        "project_id": pid,
        "shots": len(shot_ids),
        "timeline_seconds": timeline.get("total_duration_sec"),
        "output": render.get("output_path"),
        "reason": render.get("reason"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except FilmError as exc:
        print(f"\nFILM FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
