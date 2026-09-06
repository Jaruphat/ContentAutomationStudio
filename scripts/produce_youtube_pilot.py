"""Create the isolated 25-second ODDVERSE pilot, then queue real H3 shots.

Resume with --state; creation never approves takes or publishes anything.
References are imported as owned assets. The workflow records its 576x1024
generation canvas; the project's 1080x1920 canvas is the delivery upscale.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from run_motion_probe import call, save, PROMPT

BEATS = [
    ("The train", "6003f255-f94b-4d3c-bdc4-8cdf473e8bec_a68a4b22_6dc8147c_00001.png",
     PROMPT, "This train still stops here every night.", "EVERY NIGHT."),
    ("The closed station", "eeb3c1dc-1197-4509-abc2-cea7ed6304b8_a68a4b22_618316b6_00001.png",
     "The camera travels slowly sideways along this abandoned railway platform, past the rusted bench and boarded window. Loose weeds sway in the wind. Mist drifts across the wet paving. Preserve the brick station in <Picture 1>. One continuous realistic night shot. Audio: wind across an empty station, distant train rumble.",
     "The station closed thirty years ago.", "CLOSED 30 YEARS AGO."),
    ("An open door", "595233eb-eba5-4364-b74c-c17be1aed663_a68a4b22_ef576955_00001.png",
     "The train carriage door in <Picture 1> opens wider with a pneumatic push. Warm light spreads across the wet platform. Steam flows visibly from under the carriage and curls past the open doorway. A steady slow camera approach towards the empty door. Realistic railway drama at night. Audio: a pneumatic hiss, low engine idle, light wind.",
     "Nobody ever gets off. Until last night.", "UNTIL LAST NIGHT."),
    ("The passenger", "37a470e2-c91f-4de9-84af-fd71d0000260_a68a4b22_aa4e9502_00001.png",
     "The woman in <Picture 1> walks two slow deliberate steps towards the camera along the platform. Her charcoal coat sways around her legs and her hair moves in the breeze. She keeps the folded newspaper at her side. Maintain her facial identity, the train and the station architecture. The camera stays at eye level. Realistic continuous shot. Audio: two footsteps on wet concrete, train idle and night wind.",
     "A woman stepped out and whispered my name.", "SHE KNEW MY NAME."),
    ("The invitation", "37a470e2-c91f-4de9-84af-fd71d0000260_a68a4b22_aa4e9502_00001.png",
     "The camera moves steadily closer to the woman in <Picture 1>, from full body to a close portrait of her face and shoulders. She looks straight into the lens, her expression calm and serious. A breeze moves her hair, she blinks once and tilts her head slightly. The newspaper remains down by her side outside the final close framing. Keep her face and charcoal coat consistent. One continuous realistic shot with smooth forward camera movement. Audio: quiet night wind and a low train rumble.",
     "You're late, she said. We buried you yesterday.", "WE BURIED YOU YESTERDAY."),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--api", default="http://127.0.0.1:8002")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--workflow", default="c72f759e-592c-4999-b28a-063ba421c451")
    args = p.parse_args()
    args.state.parent.mkdir(parents=True, exist_ok=True)
    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    if "project_id" not in state:
        project = call(args.api, "POST", "/api/projects", json={
            "title": "ODDVERSE — The Last Passenger — YouTube pilot",
            "objective": "A 25-second supernatural fiction short for YouTube.",
            "language": "en", "content_type": "short-film", "aspect_ratio": "9:16",
            "target_resolution": "1080x1920", "frame_rate": 24,
            "target_duration_sec": 25, "default_video_workflow_id": args.workflow,
            "brief_text": "Fictional ghost story adapted from the existing station world. Original key art reused as references; all video is newly generated. H3 Turbo 8 steps, 124 frames, 576x1024 source; 1080x1920 delivery upscale. Narrator tells a memory, no character lip sync required.",
        })
        state = {"project_id": project["id"], "shots": []}
        save(args.state, state)
    pid = state["project_id"]
    for i, (name, filename, prompt, dialogue, emphasis) in enumerate(BEATS, 1):
        if len(state["shots"]) >= i:
            continue
        sheet = call(args.api, "POST", f"/api/projects/{pid}/references", json={"kind": "location", "name": name})
        with (args.source / filename).open("rb") as f:
            ref = call(args.api, "POST", f"/api/projects/{pid}/references/{sheet['id']}/images", files={"file": (filename, f, "image/png")}, data={"role": "canonical"})
        scene = call(args.api, "POST", f"/api/projects/{pid}/scenes", json={"title": name, "order": i})
        shot = call(args.api, "POST", f"/api/projects/{pid}/scenes/{scene['id']}/shots", json={
            "order": 1, "generation_mode": "image-to-video", "video_prompt": prompt,
            "planned_duration_sec": 5, "seed_policy": "fixed", "seed": 42 if i == 1 else 20260905 + i,
            "workflow_preset_id": args.workflow, "reference_asset_ids": [ref["id"]],
            "dialogue": dialogue, "emphasis_text": emphasis,
        })
        state["shots"].append({"shot_id": shot["id"], "scene_id": scene["id"], "name": name})
        save(args.state, state)
    if "job_ids" not in state:
        jobs = call(args.api, "POST", f"/api/projects/{pid}/generate", json={"shot_ids": [s["shot_id"] for s in state["shots"]]})
        state["job_ids"] = [j["id"] for j in jobs]
        save(args.state, state)
    print(json.dumps(state), flush=True)
    previous = None
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline:
        jobs = call(args.api, "GET", f"/api/projects/{pid}/jobs")
        selected = [j for j in jobs if j["id"] in state["job_ids"]]
        status = [(j["shot_id"][:8], j["status"], j.get("progress_stage")) for j in selected]
        if status != previous:
            print(json.dumps(status), flush=True)
            previous = status
        if any(j["status"] in ("Failed", "Cancelled") for j in selected):
            save(args.state.parent / "jobs.json", selected)
            raise RuntimeError("Generation stopped; inspect jobs.json before retrying")
        if len(selected) == len(state["job_ids"]) and all(j["status"] == "Completed" for j in selected):
            save(args.state.parent / "jobs.json", selected)
            takes = call(args.api, "GET", f"/api/projects/{pid}/takes")
            save(args.state.parent / "takes.json", takes)
            print("All clips generated. Review before approval and render.", flush=True)
            return
        time.sleep(15)
    raise TimeoutError("Inspect the generation queue before retrying")


if __name__ == "__main__":
    main()
