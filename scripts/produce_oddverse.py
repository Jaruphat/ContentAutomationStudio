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
from datetime import date, timedelta
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
WF_EDIT2 = os.environ.get("CAS_ODD_WF_EDIT2", "9da5f99b-724a-4f63-b097-a8bf39b2e7af")
#: Image to video: animates the approved key image.
WF_I2V = os.environ.get("CAS_ODD_WF_I2V", "711d55b8-fc50-41b3-92eb-d706653fde4f")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from oddverse import EPISODES, KNOWN_GAPS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

#: The model's canvas. The delivery canvas is the project's and is larger.
SRC_W, SRC_H = 576, 1024
#: Base seed for the scene plates. Fixed so a re-run rebuilds the same places.
PLATE_SEED = 317317


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


def scenes_of(ep: dict[str, Any]) -> list[dict[str, Any]]:
    """Every episode is a list of scenes; a one-place episode is a list of one.

    SF01 happens entirely at one station, so a single approved plate held all
    nine shots together and one scene was enough. An episode that moves - a
    street, a kitchen table, an upstairs hall, the room at the end of it -
    needs a plate for each place, because a plate is what stops three shots of
    a hallway being three different hallways. A place with a plate and a
    purpose is what a Scene already is, so scenes are where they go.
    """
    listed = ep.get("scenes")
    if listed:
        return list(listed)
    return [{
        "key": "",
        "title": ep["title"],
        "purpose": ep["objective"],
        "location": ep.get("location_name", "The location"),
        "time_of_day": "night",
        "world": ep["world"],
        "plate_prompt": ep.get(
            "plate_prompt",
            "Wide establishing photograph of the whole place, no people.",
        ),
    }]


def beat_scene(beat: tuple) -> str:
    """The scene a beat belongs to. Absent on a single-scene episode."""
    return beat[7] if len(beat) > 7 else ""


def canonical_view(pid: str, set_id: str, slot: str = "") -> str:
    """One approved canonical view of a character, as a reference image id.

    The slot matters. A face composited onto a newspaper has to be a face, and
    the canonical view a character set happens to list first can be a back
    shot - which is exactly what this episode's observer is, by design. Naming
    the slot fails loudly when the sheet does not carry it, rather than
    pasting a back view onto a front page.
    """
    cset = call("GET", f"/api/projects/{pid}/character-sets/{set_id}")
    approved = next(
        (v for v in cset["versions"] if v["id"] == cset["approved_version_id"]),
        None,
    )
    if approved is None:
        raise ProductionError(f"Character set {set_id} has no approved version.")
    views = [v for v in approved["views"] if v.get("reference_image_id")]
    if slot:
        for view in views:
            if view["slot"] == slot:
                return view["reference_image_id"]
        raise ProductionError(
            f"Character set {set_id} has no generated '{slot}' view. It has: "
            f"{', '.join(v['slot'] for v in views) or 'none'}."
        )
    if views:
        return views[0]["reference_image_id"]
    raise ProductionError(f"Character set {set_id} has no generated view.")


def generate_and_approve(
    pid: str, shot_id: str, label: str, budget: float, content_sha256: str = "",
) -> str:
    """Queue one shot, wait for it, and approve its take. Returns the take id.

    A take this shot already has is adopted rather than regenerated. A run
    killed between a completed job and the write of its state file has already
    paid for that frame, and re-queueing it both spends the GPU time twice and
    fails: the shot is sitting in NeedsReview, which the queue refuses. The
    adoption is only safe while the take still describes the shot as it now
    stands, so the shot's content digest has to match.
    """
    started = time.time()
    for take in call("GET", f"/api/shots/{shot_id}/takes"):
        if content_sha256 and take.get("content_sha256") != content_sha256:
            continue
        if take["review_status"] != "Approved":
            call("POST", f"/api/takes/{take['id']}/approve")
        log(f"{label}: adopted the take an earlier run already generated")
        return take["id"]
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
    parser.add_argument("--channel", default="",
                        help="Start the episode under this channel, so it "
                             "inherits the channel's bibles and is counted "
                             "against its pillars.")
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
        settings = {
            "aspect_ratio": ep["aspect_ratio"],
            "target_resolution": ep["resolution"],
            "frame_rate": ep["frame_rate"],
            "target_duration_sec": sum(b[0] for b in beats),
            "default_image_workflow_id": WF_T2I,
            "default_video_workflow_id": WF_I2V,
            "language": "en",
        }
        if args.channel:
            # Started under the channel, so the visual bible is copied in
            # rather than retyped, and the pillar and hook this episode is
            # testing are recorded now. Recorded afterwards they are guesses.
            project = call(
                "POST", f"/api/channels/{args.channel}/episodes", expect=201,
                json={
                    "title": ep["title"],
                    "objective": ep["objective"],
                    "premise": ep.get("one_strange_thing", ""),
                    "pillar": ep.get("pillar", ""),
                    "hook_type": ep.get("hook_type", ""),
                    "target_duration_sec": sum(b[0] for b in beats),
                },
            )
            call("PUT", f"/api/projects/{project['id']}", json=settings)
            log(f"episode started under channel {args.channel[:8]}")
        else:
            project = call("POST", "/api/projects", expect=201, json={
                "title": ep["title"], "objective": ep["objective"], **settings,
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

    # -- the house look ----------------------------------------------------
    # An episode started from a channel already carries the channel's visual
    # bible, copied into its own Story Bible when the episode began. Writing a
    # second style here would compile both into every prompt, so the existing
    # one is adopted rather than duplicated.
    if "style_id" not in state:
        existing = call("GET", f"/api/projects/{pid}/styles")
        if existing:
            state["style_id"] = existing[0]["id"]
            log(f"house look inherited from the channel: {existing[0]['medium']}")
        else:
            style = call("POST", f"/api/projects/{pid}/styles", expect=201, json={
                "medium": "live-action documentary photography",
                "genre": "mystery",
                "visual_keywords": ep["style"],
                # How the *frames* are chosen, not how they hold still. The
                # stillness instruction used to live here and reached every
                # clip prompt through the style, quietly overriding whatever
                # the shot asked to happen. Camera behaviour is per-shot now.
                "camera_language": "Establishing, medium, detail, reaction, reveal.",
                "palette": "muted neutral tones, cold damp night, weak tungsten",
                "lighting_rules": "natural practical lighting only, realistic exposure",
                "negative_constraints": ep["negative"],
            })
            state["style_id"] = style["id"]
            log("house look written to the Story Bible")
        save_state(out, state)

    # -- the places, each established once ----------------------------------
    # Nine key images generated from nine paragraphs are nine places. One
    # approved plate per scene, referenced by every key image in that scene,
    # is as many places as the film actually visits - the same thing a
    # character sheet does for a face.
    scene_state: dict[str, Any] = state.get("scenes", {})
    if "world_image_id" in state and not scene_state:
        # A run started before scenes existed kept its single plate at the top
        # level. Resuming it must not pay for that plate a second time.
        scene_state[""] = {
            "scene_id": state.get("scene_id"),
            "location_id": state.get("location_id"),
            "sheet_id": state.get("world_sheet_id"),
            "world_image_id": state["world_image_id"],
        }
    for position, scene in enumerate(scenes_of(ep)):
        key = scene["key"]
        record = scene_state.get(key) or {}
        if not record.get("location_id"):
            location = call("POST", f"/api/projects/{pid}/locations", expect=201, json={
                "name": scene["location"],
                "description": scene["world"],
                "time_of_day": scene.get("time_of_day", "night"),
            })
            record["location_id"] = location["id"]
        if not record.get("world_image_id"):
            sheet = call("POST", f"/api/projects/{pid}/references", expect=201, json={
                "kind": "location",
                "name": scene["location"],
                "canonical_description": scene["world"],
                "negative_tokens": ep["negative"],
            })
            log(f"generating the plate for {scene['title']}...")
            plate = call(
                "POST", f"/api/projects/{pid}/references/{sheet['id']}/generate",
                expect=201, timeout=1800,
                json={
                    "prompt": f"{scene['world']} {scene['plate_prompt']} {ep['style']}",
                    "negative_prompt": ep["negative"],
                    "workflow_id": WF_T2I,
                    # Distinct per place: one seed across four plates is four
                    # attempts at the same composition.
                    "seed": PLATE_SEED + position,
                    "width": 768,
                    "height": 1024,
                },
            )
            record["sheet_id"] = sheet["id"]
            record["world_image_id"] = plate["id"]
            log(f"plate for {scene['title']}: {plate['id'][:8]}")
        if not record.get("scene_id"):
            created = call("POST", f"/api/projects/{pid}/scenes", expect=201, json={
                "order": position + 1,
                "title": scene["title"],
                "purpose": scene["purpose"],
                "location_id": record["location_id"],
            })
            record["scene_id"] = created["id"]
        scene_state[key] = record
        state["scenes"] = scene_state
        save_state(out, state)

    # -- canonical cast -----------------------------------------------------
    cast_ids: dict[str, str] = state.get("cast_ids", {})
    # Cast a beat conditions on, plus anyone a composite will paste in: the
    # sheet has to exist either way, and only the first kind reaches a prompt.
    needed = {name for beat in beats for name in beat[6]}
    needed |= set(ep.get("composite_cast") or [])
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

    # -- beat by beat: key image, approve, animate, approve ----------------
    produced: dict[str, Any] = state.get("beats", {})
    #: Shot order is per scene, because the role a shot plays is read off its
    #: position within its own scene. Numbered across the film instead, every
    #: scene after the first would open on a continuation of the one before.
    order_in_scene: dict[str, int] = {}
    for index, beat in enumerate(beats, start=1):
        seconds, name, image_prompt, motion, narration, emphasis, cast = beat[:7]
        # Two parts or three. Every episode written before the models
        # generated sound has a pair, and must keep compiling to the prompt it
        # was made with.
        subject_motion, camera_motion, audio_direction = (
            tuple(motion) + ("", "", ""))[:3]
        scene_record = scene_state[beat_scene(beat)]
        sid = scene_record["scene_id"]
        world_ref = [scene_record["world_image_id"]]
        position = order_in_scene.get(beat_scene(beat), 0) + 1
        order_in_scene[beat_scene(beat)] = position
        record = produced.get(str(index), {})
        record["scene_id"] = sid
        detail = index in (ep.get("detail_beats") or ())
        sets = [cast_ids[c] for c in cast]
        log(f"beat {index}/{len(beats)} - {name}")

        # 1. The key image. A shot with a character is composed by editing
        #    that character's canonical view; one with nobody in it is made
        #    from the prompt alone.
        if "key_take_id" not in record:
            if "key_shot_id" not in record:
                shot = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots",
                            expect=201, json={
                    "order": position * 2 - 1,
                    "label": name,
                    "generation_mode": "image",
                    "include_in_cut": False,
                    "scene_role": "establishing",
                    "image_prompt": f"{image_prompt} {ep['style']}",
                    "negative_prompt": ep["negative"],
                    "character_set_ids": sets,
                    # Every key image is an edit of its scene's plate, so all
                    # the shots in a scene are the same place. A shot with a
                    # character carries two inputs: the canonical view, then
                    # the plate.
                    #
                    # A detail is the exception. The plate exists to hold a
                    # *place* together, and an extreme close-up of a label has
                    # no place in it - conditioning one on the plate hands
                    # back the plate's framing, so the shot comes out as
                    # another wide view of the room with the label somewhere
                    # in it. Two shots of this episode were lost that way
                    # before the rule was written down.
                    "reference_asset_ids": [] if detail else world_ref,
                    "workflow_preset_id": (
                        (WF_EDIT if detail else WF_EDIT2) if sets
                        else (WF_T2I if detail else WF_EDIT)
                    ),
                    "image_provider_id": "comfyui", "image_model": "workflow",
                })
                record["key_shot_id"] = shot["id"]
                produced[str(index)] = record
                state["beats"] = produced
                save_state(out, state)
            current = call(
                "GET", f"/api/projects/{pid}/scenes/{sid}/shots/{record['key_shot_id']}")
            record["key_take_id"] = generate_and_approve(
                pid, record["key_shot_id"], f"beat {index} key image",
                budget=1800, content_sha256=current["content_sha256"])
            produced[str(index)] = record
            state["beats"] = produced
            save_state(out, state)

        # 1b. Composite what the model cannot write. The date and the
        #     front-page photograph are the two things in this episode that
        #     have to be *read*, and no prompt makes a model spell. The
        #     composite is a new take of the same shot, reviewed like any
        #     other, and it is the frame the clip animates.
        recipe = ep.get("composites", {}).get(index)
        if recipe and "composited_take_id" not in record:
            today = date.today()
            # Dates a composite can ask for, resolved at production time. A
            # date typed into the recipe would be wrong the day after it was
            # written, and this is the one thing in the frame that gets read.
            dates = {
                "tomorrow": (today + timedelta(days=1)).strftime("%d %B %Y").upper(),
                "next_year": (today + timedelta(days=365)).strftime("%d %B %Y").upper(),
            }
            layers = []
            for layer in recipe:
                resolved = dict(layer)
                if resolved.get("text"):
                    resolved["text"] = resolved["text"].format(**dates)
                marker = str(resolved.get("reference_image_id") or "")
                if marker.startswith("{") and marker.endswith("}"):
                    name, _, slot = marker.strip("{}").partition(":")
                    resolved["reference_image_id"] = canonical_view(
                        pid, cast_ids[name], slot
                    )
                layers.append(resolved)
            composited = call(
                "POST", f"/api/takes/{record['key_take_id']}/composite",
                expect=201, json={"layers": layers},
            )
            call("POST", f"/api/takes/{composited['id']}/approve")
            record["composited_take_id"] = composited["id"]
            produced[str(index)] = record
            state["beats"] = produced
            save_state(out, state)
            log(f"beat {index}: composited {len(layers)} layer(s)")

        start_frame_take = record.get("composited_take_id") or record["key_take_id"]

        # 2. The clip, animated from that approved frame.
        if "clip_take_id" not in record:
            if "clip_shot_id" not in record:
                shot = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots",
                            expect=201, json={
                    "order": position * 2,
                    "label": name,
                    "generation_mode": "image-to-video",
                    "scene_role": "establishing" if position == 1 else "continuation",
                    "planned_duration_sec": seconds,
                    "dialogue": narration,
                    "emphasis_text": emphasis,
                    # What happens leads; the camera qualifies it. Sent apart
                    # because a video model reads a camera sentence as the
                    # whole brief and animates nothing.
                    "subject_motion": subject_motion,
                    "camera_motion": camera_motion,
                    # The H3 models render sound with the picture and read the
                    # direction for it from the same prompt. Left out, the
                    # clip comes back with whatever ambience it invented.
                    "audio_direction": audio_direction,
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
                 f"/api/projects/{pid}/takes/{start_frame_take}/continuity-frame",
                 json={"at_sec": 0.0}, expect=(200, 201))
            # Bind the approved key image as this clip's first frame. Never
            # inferred from shot order: the binding names a frame that exists.
            call("PUT",
                 f"/api/projects/{pid}/scenes/{sid}/shots/"
                 f"{record['clip_shot_id']}/continuity",
                 json={"source_take_id": start_frame_take})
            current = call(
                "GET", f"/api/projects/{pid}/scenes/{sid}/shots/{record['clip_shot_id']}")
            record["clip_take_id"] = generate_and_approve(
                pid, record["clip_shot_id"], f"beat {index} clip",
                budget=2400, content_sha256=current["content_sha256"])
            produced[str(index)] = record
            state["beats"] = produced
            save_state(out, state)

    # -- retire what this run replaced --------------------------------------
    # Redoing a beat creates a new clip shot; the one it replaced still has an
    # approved take and would still be assembled. Four extra shots turned a
    # 32-second cut into 48 without a single error, which is the shape of
    # mistake that only shows up as a duration.
    kept = {b["clip_shot_id"] for b in produced.values() if b.get("clip_shot_id")}
    for record in scene_state.values():
        scene_id = record["scene_id"]
        for shot in call("GET", f"/api/projects/{pid}/scenes/{scene_id}/shots"):
            if (shot["generation_mode"] == "image-to-video"
                    and shot["id"] not in kept
                    and shot["include_in_cut"]):
                call("PUT", f"/api/projects/{pid}/scenes/{scene_id}/shots/{shot['id']}",
                     json={"include_in_cut": False})
                log(f"retired superseded clip shot {shot['id'][:8]}")

    # -- captions -----------------------------------------------------------
    # Emphasis cards are post-production, not a generation input: setting them
    # does not move a shot's content digest, so a run already generated can
    # have its cards written without any take going stale.
    for index, beat in enumerate(beats, start=1):
        record = produced.get(str(index), {})
        if not record.get("clip_shot_id"):
            continue
        call("PUT",
             f"/api/projects/{pid}/scenes/{record['scene_id']}/shots/"
             f"{record['clip_shot_id']}",
             json={"emphasis_text": beat[5], "dialogue": beat[4]})

    # -- what this will be published as -------------------------------------
    # Written before the render rather than after it, because the publish
    # package refuses to invent a title and an episode with no pillar recorded
    # cannot be compared against the others once it is out.
    publishing = ep.get("publishing", {})
    if publishing:
        call("PUT", f"/api/projects/{pid}/publish", json={
            "publish_title": publishing.get("title", ""),
            "series_label": ep["series"],
            "publish_description": publishing.get("description", ""),
            "publish_hashtags": publishing.get("hashtags", ""),
        })

    # -- timeline and render ----------------------------------------------
    manifest = call("POST", f"/api/projects/{pid}/timeline/build")
    log(f"timeline: {manifest['item_count']} items, "
        f"{manifest['total_duration_sec']:.1f}s")

    render_body = {"narrate": True}
    if os.environ.get("CAS_ODD_VOICE", "system") == "openai":
        # Metered, so it is opt-in through the environment rather than the
        # default: a resumed run must not start spending because it was
        # resumed. The reading direction comes from the Voice Bible.
        render_body.update({
            "voice_provider": "openai",
            "voice": os.environ.get("CAS_ODD_VOICE_NAME", "onyx"),
            "voice_instructions": ep.get("voice_direction", ""),
            "confirm_paid_generation": True,
        })
    result = call("POST", f"/api/projects/{pid}/render",
                  json=render_body, timeout=3600)
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
