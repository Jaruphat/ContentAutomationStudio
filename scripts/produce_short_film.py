"""Produce one of the films in scripts/films.py through the studio's own API.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from films import FILMS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

class FilmError(RuntimeError):
    """A step that cannot be completed through the application's own API."""


def load_state(out: Path) -> dict[str, Any]:
    path = out / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_state(out: Path, state: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "state.json").write_text(
        json.dumps(state, indent=2, default=str), encoding="utf-8")


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
    parser.add_argument("--film", default="cartographer", choices=sorted(FILMS),
                        help="Which film in scripts/films.py to produce.")
    parser.add_argument("--shots", type=int, default=0,
                        help="Produce only the first N shots; 0 means all of them.")
    parser.add_argument("--reset", action="store_true",
                        help="Start a new project rather than resume.")
    args = parser.parse_args()

    film = FILMS[args.film]
    out = ROOT / "backend" / "data" / "film" / args.film
    out.mkdir(parents=True, exist_ok=True)
    state = {} if args.reset else load_state(out)
    shots_wanted = film["shots"][: args.shots] if args.shots else film["shots"]
    seconds = float(film["seconds_per_shot"])

    # -- project ---------------------------------------------------------
    if "project_id" not in state:
        project = call("POST", "/api/projects", expect=201, json={
            "title": film["title"],
            "objective": film["objective"],
            "aspect_ratio": film["aspect_ratio"],
            "target_resolution": film["resolution"],
            "frame_rate": 24.0,
            "target_duration_sec": seconds * len(shots_wanted),
            "default_video_workflow_id": WF_R2V,
            "language": "en",
        })
        state["project_id"] = project["id"]
        save_state(out, state)
        log(f"project {project['id']} - {film['title']}")
    pid = state["project_id"]

    # -- canonical cast ---------------------------------------------------
    if "character_set_ids" not in state:
        set_ids = []
        for member in film["cast"]:
            spec = {k: v for k, v in member.items() if k != "slots"}
            cset = call("POST", f"/api/projects/{pid}/character-sets", expect=201, json=spec)
            version = call("POST", f"/api/projects/{pid}/character-sets/{cset['id']}/versions",
                           expect=201, json={"slots": member["slots"]})
            log(f"generating the canonical sheet for {member['name']}...")
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
                raise FilmError(f"canonical views failed for {member['name']}: {missing}")
            call("POST",
                 f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/approve")
            set_ids.append(cset["id"])
            log(f"{member['name']} approved in {time.time() - started:.0f}s")
        state["character_set_ids"] = set_ids
        save_state(out, state)
    set_ids = state["character_set_ids"]

    # -- scene and shots --------------------------------------------------
    if "scene_id" not in state:
        scene = call("POST", f"/api/projects/{pid}/scenes", expect=201,
                     json={"order": 1, "title": film["title"], "purpose": film["objective"]})
        state["scene_id"] = scene["id"]
        save_state(out, state)
    sid = state["scene_id"]

    shot_ids: list[str] = state.get("shot_ids", [])
    if len(shot_ids) < len(shots_wanted):
        for index in range(len(shot_ids), len(shots_wanted)):
            narration, action = shots_wanted[index]
            shot = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots", expect=201, json={
                "order": index + 1,
                "subject": film["cast"][0]["name"],
                "action": action,
                "planned_duration_sec": seconds,
                "generation_mode": "video",
                # The subtitle track and the spoken narration both read this.
                "dialogue": narration,
                "video_prompt": f"{action}. {film['look']}. {film['identity_line']}",
                "character_set_ids": set_ids,
                "workflow_preset_id": WF_R2V,
                "image_provider_id": "comfyui", "image_model": "workflow",
            })
            shot_ids.append(shot["id"])
            state["shot_ids"] = shot_ids
            save_state(out, state)
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
        save_state(out, state)
        log(f"shot {index}/{len(shot_ids)}: approved in {time.time() - started:.0f}s")

    # -- timeline, subtitles, narrated render ------------------------------
    timeline = call("POST", f"/api/projects/{pid}/timeline/build", json={})
    log(f"timeline: {timeline.get('item_count')} items, {timeline.get('total_duration_sec')}s")

    call("PUT", f"/api/projects/{pid}/subtitles", json={
        "mode": "burn_in", "preset": "cinematic", "position": "bottom",
    }, expect=(200, 404))

    log("rendering with narration...")
    started = time.time()
    render = call("POST", f"/api/projects/{pid}/render", json={"narrate": True},
                  timeout=3600, expect=(200, 201, 409))
    state["render"] = render
    save_state(out, state)
    log(f"render finished in {time.time() - started:.0f}s: "
        f"{render.get('output_path') or render.get('reason')}")

    print(json.dumps({
        "film": args.film,
        "project_id": pid,
        "shots": len(shot_ids),
        "timeline_seconds": timeline.get("total_duration_sec"),
        "narration": render.get("narration"),
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
