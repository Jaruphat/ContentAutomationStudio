"""Run a controlled H3 I2V comparison in a separate Studio instance.

Each variant receives the same image, prompt, seed, canvas and frame count.
Only the existing full/Turbo switch changes. Workflows and projects are new;
source registrations and projects are never updated. No takes are auto-approved.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path

import requests

PROMPT = (
    "A weathered British passenger train approaches the camera along the rails "
    "at the empty rural station shown in <Picture 1>. Its wheels turn as it "
    "travels several metres towards the foreground, growing clearly larger. "
    "The headlights sweep bright reflections along the wet rails. Wisps of "
    "steam flow sideways across the platform. The camera remains in the same "
    "position. One continuous realistic documentary shot at night. "
    "Audio: approaching train rumble, wheels on rails and a gentle brake hiss."
)


def call(base: str, method: str, path: str, **kwargs):
    r = requests.request(method, base.rstrip("/") + path, timeout=60, **kwargs)
    r.raise_for_status()
    return r.json() if r.content else None


def save(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8002")
    parser.add_argument("--source-api", default="http://127.0.0.1:8001")
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260905)
    parser.add_argument("--variants", nargs="+", choices=["full", "turbo"], default=["full", "turbo"])
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = call(args.source_api, "GET", f"/api/workflows/{args.workflow}")
    source_bytes = Path(source["source_json_path"]).read_bytes()
    graph = json.loads(source_bytes)
    controls = [key for key, node in graph.items() if node["class_type"] == "PrimitiveBoolean"]
    if len(controls) != 1:
        raise ValueError("Expected the inspected H3 graph with one full/Turbo switch")
    condition = source["parameter_mapping"]["positivePrompt"]["nodeId"]
    manifest = {
        "source_workflow_id": args.workflow,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "image_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "prompt": PROMPT, "requested_seed": args.seed, "width": 576, "height": 1024,
        "frames": 124, "runs": [],
    }
    save(args.out / "experiment.json", manifest)
    for variant in args.variants:
        derived = copy.deepcopy(graph)
        derived[controls[0]]["inputs"]["value"] = variant == "turbo"
        derived[condition]["inputs"].update(width=576, height=1024, length=124)
        raw = json.dumps(derived, indent=2).encode()
        save(args.out / f"{variant}.workflow.json", derived)
        wf = call(args.api, "POST", "/api/workflows/import", files={
            "file": (f"h3_i2v_{variant}.json", raw, "application/json"),
        }, data={"name": f"H3 I2V probe {variant} 576x1024", "purpose": "image-to-video"})
        call(args.api, "PUT", f"/api/workflows/{wf['id']}/mapping", json={
            "parameter_mapping": source["parameter_mapping"], "output_mapping": source["output_mapping"],
        })
        validation = call(args.api, "POST", f"/api/workflows/{wf['id']}/validate")
        if not validation["valid"]:
            raise ValueError(validation)
        project = call(args.api, "POST", "/api/projects", json={
            "title": f"Motion lab — train — {variant}", "aspect_ratio": "9:16",
            "target_resolution": "576x1024", "frame_rate": 24,
            "target_duration_sec": 5, "default_video_workflow_id": wf["id"],
        })
        pid = project["id"]
        sheet = call(args.api, "POST", f"/api/projects/{pid}/references", json={
            "kind": "location", "name": "Train composition — controlled source",
        })
        with args.image.open("rb") as stream:
            ref = call(args.api, "POST", f"/api/projects/{pid}/references/{sheet['id']}/images",
                       files={"file": (args.image.name, stream, "image/png")},
                       data={"role": "canonical"})
        scene = call(args.api, "POST", f"/api/projects/{pid}/scenes", json={"title": "Train approach", "order": 1})
        shot = call(args.api, "POST", f"/api/projects/{pid}/scenes/{scene['id']}/shots", json={
            "order": 1, "shot_type": "Train approaches", "generation_mode": "image-to-video",
            "video_prompt": PROMPT, "planned_duration_sec": 5, "seed": args.seed,
            "seed_policy": "fixed", "workflow_preset_id": wf["id"],
            "reference_asset_ids": [ref["id"]],
        })
        jobs = call(args.api, "POST", f"/api/projects/{pid}/generate", json={"shot_ids": [shot["id"]]})
        record = {"variant": variant, "project_id": pid, "workflow_id": wf["id"], "shot_id": shot["id"], "job_id": jobs[0]["id"], "actual_seed": jobs[0]["seed"]}
        manifest["runs"].append(record)
        save(args.out / "experiment.json", manifest)
        print(json.dumps(record), flush=True)
        started = time.monotonic()
        previous = None
        while time.monotonic() - started < 1200:
            rows = call(args.api, "GET", f"/api/projects/{pid}/jobs")
            job = next(j for j in rows if j["id"] == record["job_id"])
            state = (job["status"], job.get("progress_stage"))
            if state != previous:
                print(variant, state, f"{time.monotonic() - started:.0f}s", flush=True)
                previous = state
            if job["status"] in ("Completed", "Failed", "Cancelled"):
                save(args.out / f"{variant}.job.json", job)
                record.update(status=job["status"], elapsed_sec=round(time.monotonic() - started, 2))
                if job["status"] != "Completed":
                    save(args.out / "experiment.json", manifest)
                    raise RuntimeError(job.get("error_message") or job["status"])
                takes = call(args.api, "GET", f"/api/shots/{shot['id']}/takes")
                save(args.out / f"{variant}.takes.json", takes)
                record["file_path"] = takes[0]["file_path"]
                record["take_id"] = takes[0]["id"]
                save(args.out / "experiment.json", manifest)
                break
            time.sleep(10)
        else:
            raise TimeoutError("Probe exceeded 20 minutes; inspect the queue before retrying")


if __name__ == "__main__":
    main()
