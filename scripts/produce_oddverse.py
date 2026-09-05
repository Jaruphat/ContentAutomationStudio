"""Produce one ODDVERSE episode through the studio's own API.

Everything goes over HTTP exactly as the cockpit drives it. If a step is
impossible through the API it is impossible for a user, and worth finding out
on a real episode rather than in a test.

The route is the slow one, on purpose. Each beat is made twice: a key image
that a human looks at and approves, and then a clip animated from that
approved frame. Reference-to-video is four times faster and composes *from the
reference*, which is why the previous film opened every shot framed like a
character sheet. This blueprint's whole premise is an ordinary world
photographed plainly, so the composition has to be decided in a still.

The key images are shots too - prompt, seed, take, review, lineage - but they
are marked out of the cut, so the film is the nine clips and not eighteen
alternating stills and clips.

Resumable: every completed step is written to a state file, so a crash or a
cancelled run picks up rather than paying for the same shots twice.
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
#: Text to image, for the key image of a shot with nobody in it.
WF_T2I = os.environ.get("CAS_ODD_WF_T2I", "359c2852-f880-430f-a096-07e6ef5625a3")
#: Reference-conditioned image edit, for the key image of a shot with a
#: character in it: the canonical view goes in, the composed scene comes out.
WF_EDIT = os.environ.get("CAS_ODD_WF_EDIT", "75a73b44-5c6f-4661-87f6-26e66a639efd")
#: Reference-conditioned edit with two inputs, for a key image that has both a
#: character and the world plate to match.
WF_EDIT2 = os.environ.get("CAS_ODD_WF_EDIT2", "9da5f99b-0ba4-4a5c-a7c2-fd1b2eb4e1c9")
#: Image to video: animates the approved key image.
WF_I2V = os.environ.get("CAS_ODD_WF_I2V", "711d55b8-fc50-41b3-92eb-d706653fde4f")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oddverse import EPISODES, KNOWN_GAPS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

#: The model's canvas. The delivery canvas is the project's and is larger.
SRC_W, SRC_H = 576, 1024


class ProductionError(RuntimeError):
    """A step that cannot be completed through the application's own API."""


def load_state(out: Path) -> dict[str, Any]:
    path = out / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_state(out: Path, state: dict[str, Any]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "state.json").write_text(
        json.dumps(state, indent=2, default=str), encoding="utf-8")


def call(method: str, path: str, *, expect: int | tuple[int, ...] = 200, **kw: Any) -> Any:
    timeout = kw.pop("timeout", 60)
    response = requests.request(method, f"{BASE}{path}", timeout=timeout, **kw)
    allowed = (expect,) if isinstance(expect, int) else expect
    if response.status_code not in allowed:
        raise ProductionError(
            f"{method} {path} -> {response.status_code}: {response.text[:500]}")
    return response.json() if response.content else None


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def wait_for_jobs(pid: str, job_ids: list[str], budget: float) -> list[dict]:
    deadline = time.time() + budget
    terminal = {"Completed", "Failed", "Cancelled"}
    last = ""
    while time.time() < deadline:
        jobs = [j for j in call("GET", f"/api/projects/{pid}/jobs") if j["id"] in job_ids]
        done = sum(1 for j in jobs if j["status"] in terminal)
        running = next((j for j in jobs if j["status"] == "Running"), None)
        note = (
            f"{done}/{len(job_ids)} settled"
            + (f" · {running.get('progress_stage') or 'running'}"
               f" {round((running.get('progress') or 0) * 100)}%" if running else "")
        )
        if note != last:
            log(note)
            last = note
        if jobs and done == len(job_ids):
            return jobs
        time.sleep(10)
    raise ProductionError(f"jobs did not settle within {budget}s")


def generate_and_approve(pid: str, shot_id: str, label: str, budget: float) -> str:
    """Queue one shot, wait for it, and approve its take. Returns the take id."""
    started = time.time()
    jobs = call("POST", f"/api/projects/{pid}/generate",
                json={"shot_ids": [shot_id], "confirm_paid_generation": False})
    if not jobs:
        raise ProductionError(f"{label}: the project refused to queue this shot")
    settled = wait_for_jobs(pid, [j["id"] for j in jobs], budget=budget)
    failed = [j for j in settled if j["status"] != "Completed"]
    if failed:
        raise ProductionError(
            f"{label} failed: {failed[0].get('error_message') or failed[0]['status']}")
    takes = call("GET", f"/api/shots/{shot_id}/takes")
    if not takes:
        raise ProductionError(f"{label}: completed with no take")
    take = takes[0]
    if take["review_status"] != "Approved":
        call("POST", f"/api/takes/{take['id']}/approve")
    log(f"{label}: approved in {time.time() - started:.0f}s")
    return take["id"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", default="sf01", choices=sorted(EPISODES))
    parser.add_argument("--shots", type=int, default=0,
                        help="Produce only the first N beats; 0 means all.")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--tag", default="",
                        help="A separate state directory, for a second cut of "
                             "the same episode.")
    args = parser.parse_args()

    ep = EPISODES[args.episode]
    out = ROOT / "backend" / "data" / "film" / (
        f"oddverse-{args.episode}" + (f"-{args.tag}" if args.tag else "")
    )
    out.mkdir(parents=True, exist_ok=True)
    state = {} if args.reset else load_state(out)
    beats = ep["shots"][: args.shots] if args.shots else ep["shots"]

    log(f"{ep['series']} - {ep['title']}")
    for gap in KNOWN_GAPS:
        log(f"  gap: {gap}")

    # -- project ----------------------------------------------------------
    if "project_id" not in state:
        project = call("POST", "/api/projects", expect=201, json={
            "title": ep["title"],
            "objective": ep["objective"],
            "aspect_ratio": ep["aspect_ratio"],
            "target_resolution": ep["resolution"],
            "frame_rate": ep["frame_rate"],
            "target_duration_sec": sum(b[0] for b in beats),
            "default_image_workflow_id": WF_T2I,
            "default_video_workflow_id": WF_I2V,
            "language": "en",
        })
        state["project_id"] = project["id"]
        save_state(out, state)
        log(f"project {project['id']}")
    pid = state["project_id"]

    # Subtitles readable on a vertical frame. The blueprint's Subtitle Bible
    # wants a plain accessibility track: no emoji, no colour, no bouncing.
    call("PUT", f"/api/projects/{pid}/subtitles", json={
        "mode": "burn_in",
        "preset": "clean",
        "max_chars_per_line": ep["subtitles"]["max_chars_per_line"],
        "vertical_margin": ep["subtitles"]["vertical_margin"],
    })

    # -- the house look, in the Story Bible rather than in 9 prompts -------
    if "style_id" not in state:
        style = call("POST", f"/api/projects/{pid}/styles", expect=201, json={
            "medium": "live-action documentary photography",
            "genre": "mystery",
            "visual_keywords": ep["style"],
            "camera_language": (
                "Establishing, medium, detail, reaction, reveal. Locked-off or "
                "restrained observational camera."
            ),
            "palette": "muted neutral tones, cold damp night, weak tungsten",
            "lighting_rules": "natural practical lighting only, realistic exposure",
            "negative_constraints": ep["negative"],
        })
        state["style_id"] = style["id"]
        location = call("POST", f"/api/projects/{pid}/locations", expect=201, json={
            "name": "The abandoned station",
            "description": ep["world"],
            "time_of_day": "night",
        })
        state["location_id"] = location["id"]
        save_state(out, state)
        log("style and world written to the Story Bible")

    # -- the world, established once --------------------------------------
    # Nine key images generated from nine paragraphs are nine places. One
    # approved plate, referenced by all of them, is one place - the same thing
    # a character sheet does for a face.
    if "world_image_id" not in state:
        sheet = call("POST", f"/api/projects/{pid}/references", expect=201, json={
            "kind": "location",
            "name": "The abandoned station",
            "canonical_description": ep["world"],
            "negative_tokens": ep["negative"],
        })
        log("generating the world plate...")
        plate = call(
            "POST", f"/api/projects/{pid}/references/{sheet['id']}/generate",
            expect=201, timeout=1800,
            json={
                "prompt": (
                    f"{ep['world']} Wide establishing photograph of the whole "
                    f"station at night, no people. {ep['style']}"
                ),
                "negative_prompt": ep["negative"],
                "workflow_id": WF_T2I,
                "seed": 317317,
                "width": 768,
                "height": 1024,
            },
        )
        state["world_sheet_id"] = sheet["id"]
        state["world_image_id"] = plate["id"]
        save_state(out, state)
        log(f"world plate {plate['id'][:8]} established")
    world_ref = [state["world_image_id"]]

    # -- canonical cast ---------------------------------------------------
    cast_ids: dict[str, str] = state.get("cast_ids", {})
    needed = {name for beat in beats for name in beat[6]}
    for key in sorted(needed - set(cast_ids)):
        member = ep["cast"][key]
        spec = {k: v for k, v in member.items() if k != "slots"}
        cset = call("POST", f"/api/projects/{pid}/character-sets", expect=201, json=spec)
        version = call("POST", f"/api/projects/{pid}/character-sets/{cset['id']}/versions",
                       expect=201, json={"slots": member["slots"]})
        log(f"generating the canonical sheet for {key}...")
        generated = call(
            "POST",
            f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/generate",
            timeout=1800,
            json={"provider_id": "comfyui", "model": "workflow", "workflow_id": WF_T2I,
                  "seed": 20260905, "width": 768, "height": 1024,
                  "confirm_paid_generation": False},
        )
        missing = [v["slot"] for v in generated["views"] if not v.get("reference_image_id")]
        if missing:
            raise ProductionError(f"canonical views failed for {key}: {missing}")
        call("POST",
             f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/approve")
        cast_ids[key] = cset["id"]
        state["cast_ids"] = cast_ids
        save_state(out, state)
        log(f"{key} approved")

    # -- scene ------------------------------------------------------------
    if "scene_id" not in state:
        scene = call("POST", f"/api/projects/{pid}/scenes", expect=201, json={
            "order": 1, "title": ep["title"], "purpose": ep["objective"],
            "location_id": state.get("location_id"),
        }, )
        state["scene_id"] = scene["id"]
        save_state(out, state)
    sid = state["scene_id"]

    # -- beat by beat: key image, approve, animate, approve ----------------
    produced: dict[str, Any] = state.get("beats", {})
    for index, beat in enumerate(beats, start=1):
        seconds, name, image_prompt, motion, narration, emphasis, cast = beat
        record = produced.get(str(index), {})
        sets = [cast_ids[c] for c in cast]
        log(f"beat {index}/{len(beats)} - {name}")

        # 1. The key image. A shot with a character is composed by editing
        #    that character's canonical view; one with nobody in it is made
        #    from the prompt alone.
        if "key_take_id" not in record:
            if "key_shot_id" not in record:
                shot = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots",
                            expect=201, json={
                    "order": index * 2 - 1,
                    "shot_type": name,
                    "generation_mode": "image",
                    "include_in_cut": False,
                    "scene_role": "establishing",
                    "image_prompt": f"{image_prompt} {ep['style']}",
                    "negative_prompt": ep["negative"],
                    "character_set_ids": sets,
                    # Every key image is an edit of the world plate, so all
                    # nine are the same station. A shot with a character
                    # carries two inputs: the canonical view, then the plate.
                    "reference_asset_ids": world_ref,
                    "workflow_preset_id": WF_EDIT2 if sets else WF_EDIT,
                    "image_provider_id": "comfyui", "image_model": "workflow",
                })
                record["key_shot_id"] = shot["id"]
                produced[str(index)] = record
                state["beats"] = produced
                save_state(out, state)
            record["key_take_id"] = generate_and_approve(
                pid, record["key_shot_id"], f"beat {index} key image", budget=1800)
            produced[str(index)] = record
            state["beats"] = produced
            save_state(out, state)

        # 2. The clip, animated from that approved frame.
        if "clip_take_id" not in record:
            if "clip_shot_id" not in record:
                shot = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots",
                            expect=201, json={
                    "order": index * 2,
                    "shot_type": name,
                    "generation_mode": "image-to-video",
                    "scene_role": "continuation",
                    "planned_duration_sec": seconds,
                    "dialogue": narration,
                    "emphasis_text": emphasis,
                    "video_prompt": motion,
                    "negative_prompt": ep["negative"],
                    "workflow_preset_id": WF_I2V,
                    "image_provider_id": "comfyui", "image_model": "workflow",
                })
                record["clip_shot_id"] = shot["id"]
                produced[str(index)] = record
                state["beats"] = produced
                save_state(out, state)
            # Capture the frame first. Binding names a frame that exists,
            # so the still has to be registered as one before a shot can
            # start on it - the same step a video take needs to have its end
            # frame extracted.
            call("POST",
                 f"/api/projects/{pid}/takes/{record['key_take_id']}/continuity-frame",
                 json={"at_sec": 0.0}, expect=(200, 201))
            # Bind the approved key image as this clip's first frame. Never
            # inferred from shot order: the binding names a frame that exists.
            call("PUT",
                 f"/api/projects/{pid}/scenes/{sid}/shots/"
                 f"{record['clip_shot_id']}/continuity",
                 json={"source_take_id": record["key_take_id"]})
            record["clip_take_id"] = generate_and_approve(
                pid, record["clip_shot_id"], f"beat {index} clip", budget=2400)
            produced[str(index)] = record
            state["beats"] = produced
            save_state(out, state)

    # -- captions -----------------------------------------------------------
    # Emphasis cards are post-production, not a generation input: setting them
    # does not move a shot's content digest, so a run already generated can
    # have its cards written without any take going stale.
    for index, beat in enumerate(beats, start=1):
        record = produced.get(str(index), {})
        if not record.get("clip_shot_id"):
            continue
        call("PUT",
             f"/api/projects/{pid}/scenes/{sid}/shots/{record['clip_shot_id']}",
             json={"emphasis_text": beat[5], "dialogue": beat[4]})

    # -- timeline and render ----------------------------------------------
    manifest = call("POST", f"/api/projects/{pid}/timeline/build")
    log(f"timeline: {manifest['item_count']} items, "
        f"{manifest['total_duration_sec']:.1f}s")

    result = call("POST", f"/api/projects/{pid}/render",
                  json={"narrate": True}, timeout=3600)
    (out / "render.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8")
    if not result["rendered"]:
        raise ProductionError(f"render refused: {result['reason']}")
    log(f"rendered {result['output_path']} "
        f"({result['duration_sec']:.1f}s, {result['width']}x{result['height']})")
    for warning in result.get("warnings", []):
        log(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProductionError as exc:
        log(f"STOPPED: {exc}")
        raise SystemExit(1)
