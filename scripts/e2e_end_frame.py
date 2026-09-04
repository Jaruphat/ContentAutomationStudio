"""Prove a clip can be told where to finish, not just where to begin.

With only a first frame a clip drifts, and the shot after it inherits the
drift. Given both ends - two stills somebody already approved - the model
interpolates between them, so the cut lands exactly where the next shot opens.

This walks that against a live ComfyUI and checks the claim at the boundary:
that the landing image physically reached `last_frame` and not a reference
slot, and that the clip's final frame actually resembles the image it was told
to land on. A run that merely completes proves neither.

Needs a workflow mapping `endFrameImage`; it finds one by mapping, or takes
CAS_E2E_WF_ENDFRAME.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE = os.environ.get("CAS_E2E_BASE", "http://127.0.0.1:8001")
WF_T2I = os.environ.get("CAS_E2E_WF_T2I", "359c2852-f880-430f-a096-07e6ef5625a3")
WF_EDIT = os.environ.get("CAS_E2E_WF_EDIT", "75a73b44-5c6f-4661-87f6-26e66a639efd")
TIMEOUT = 30
EVIDENCE = Path(__file__).resolve().parents[1] / "backend" / "data" / "e2e_evidence" / "end-frame"

checks: list[dict[str, Any]] = []
step = 0


class E2EFailure(AssertionError):
    """A promise the end-frame path makes that this run found broken."""


def record(name: str, payload: Any) -> None:
    global step
    step += 1
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{step:02d}-{name}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )


def call(method: str, path: str, *, name: str, expect: int | tuple[int, ...] = 200, **kw: Any) -> Any:
    timeout = kw.pop("timeout", TIMEOUT)
    response = requests.request(method, f"{BASE}{path}", timeout=timeout, **kw)
    try:
        body = response.json()
    except ValueError:
        body = {"_raw": response.text[:1500]}
    record(name, {"request": f"{method} {path}", "status": response.status_code, "body": body})
    allowed = (expect,) if isinstance(expect, int) else expect
    if response.status_code not in allowed:
        raise E2EFailure(f"{method} {path} -> {response.status_code}: {json.dumps(body)[:400]}")
    return body


def check(label: str, condition: bool, detail: str = "") -> None:
    checks.append({"check": label, "passed": bool(condition), "detail": detail})
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + ("" if condition else f" - {detail}"))
    if not condition:
        raise E2EFailure(f"{label}: {detail}")


def settle(pid: str, job_ids: list[str], budget: float) -> list[dict]:
    deadline = time.time() + budget
    terminal = {"Completed", "Failed", "Cancelled"}
    last: list[dict] = []
    while time.time() < deadline:
        jobs = requests.get(f"{BASE}/api/projects/{pid}/jobs", timeout=TIMEOUT).json()
        last = [job for job in jobs if job["id"] in job_ids]
        if last and all(job["status"] in terminal for job in last):
            return last
        time.sleep(3)
    raise E2EFailure(f"jobs did not settle in {budget}s")


def resolve_workflow() -> str:
    configured = os.environ.get("CAS_E2E_WF_ENDFRAME")
    if configured:
        return configured
    for workflow in requests.get(f"{BASE}/api/workflows", timeout=TIMEOUT).json():
        detail = requests.get(f"{BASE}/api/workflows/{workflow['id']}", timeout=TIMEOUT).json()
        if "endFrameImage" in (detail.get("parameter_mapping") or {}):
            return workflow["id"]
    raise E2EFailure("No registered workflow maps endFrameImage.")


def generate_shot(pid: str, sid: str, shot: dict, name: str, budget: float) -> dict:
    jobs = call("POST", f"/api/projects/{pid}/generate", name=f"generate-{name}",
                json={"shot_ids": [shot["id"]], "confirm_paid_generation": False})
    settled = settle(pid, [j["id"] for j in jobs], budget)
    record(f"jobs-{name}", settled)
    check(f"{name} completed", all(j["status"] == "Completed" for j in settled),
          json.dumps([{"s": j["status"], "e": j.get("error_message")} for j in settled])[:500])
    take = call("GET", f"/api/shots/{shot['id']}/takes", name=f"takes-{name}")[0]
    return call("POST", f"/api/takes/{take['id']}/approve", name=f"approve-{name}")


def mean_abs_difference(first: str, second: str) -> float:
    """How far apart two images are, 0 identical, 255 opposite."""
    result = subprocess.run(
        # metadata=print logs at info level, so a quieter level prints nothing.
        ["ffmpeg", "-v", "info", "-i", first, "-i", second,
         "-filter_complex",
         "[0:v]scale=256:144,format=gray[a];[1:v]scale=256:144,format=gray[b];"
         "[a][b]blend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    values = [
        float(line.split("=")[-1])
        for line in result.stderr.splitlines()
        if "YAVG" in line
    ]
    if not values:
        raise E2EFailure(f"could not compare {first} and {second}: {result.stderr[:300]}")
    return sum(values) / len(values)


def main() -> int:
    started = time.time()
    wf_end = resolve_workflow()
    print(f"end-frame workflow: {wf_end}")

    print("\n=== 1. Two approved stills: where the clip starts and where it lands ===")
    project = call("POST", "/api/projects", name="project", expect=201, json={
        "title": "E2E เฟรมจบที่กำหนดไว้",
        "aspect_ratio": "9:5", "target_resolution": "864x480", "frame_rate": 24.0,
        "default_image_workflow_id": WF_EDIT, "default_video_workflow_id": wf_end,
    })
    pid = project["id"]

    cset = call("POST", f"/api/projects/{pid}/character-sets", name="character-set",
                expect=201, json={
                    "name": "Mai, the courier",
                    "appearance": "young woman, short black bob, amber eyes",
                    "wardrobe": "teal courier jacket, grey cargo trousers, brown boots",
                    "identity_tokens": "consistent face, consistent wardrobe",
                })
    version = call("POST", f"/api/projects/{pid}/character-sets/{cset['id']}/versions",
                   name="version", expect=201, json={"slots": ["full_body"]})
    call("POST",
         f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/generate",
         name="sheet", timeout=900.0,
         json={"provider_id": "comfyui", "model": "workflow", "workflow_id": WF_T2I,
               "seed": 515151, "width": 768, "height": 768,
               "confirm_paid_generation": False})
    call("POST",
         f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/approve",
         name="approve-set")

    sid = call("POST", f"/api/projects/{pid}/scenes", name="scene", expect=201,
               json={"order": 1, "title": "Rooftop"})["id"]

    def still(order: int, prompt: str, name: str) -> dict:
        return call("POST", f"/api/projects/{pid}/scenes/{sid}/shots", name=name,
                    expect=201, json={
                        "order": order, "subject": "Mai the courier",
                        "planned_duration_sec": 3.0, "generation_mode": "image",
                        "image_prompt": prompt, "character_set_ids": [cset["id"]],
                        "workflow_preset_id": WF_EDIT,
                        "image_provider_id": "comfyui", "image_model": "workflow",
                    })

    shot_open = still(1, "Mai the courier stands at the left edge of a rooftop at dusk, "
                         "city lights behind her, wide shot", "shot-open")
    shot_land = still(2, "Mai the courier stands at the right edge of the same rooftop "
                         "at dusk, city lights behind her, wide shot", "shot-land")
    take_open = generate_shot(pid, sid, shot_open, "open", 400.0)
    take_land = generate_shot(pid, sid, shot_land, "land", 400.0)

    print("\n=== 2. A clip told both where to start and where to finish ===")
    clip = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots", name="shot-clip",
                expect=201, json={
                    "order": 3, "subject": "Mai the courier",
                    "planned_duration_sec": 3.0, "generation_mode": "image-to-video",
                    "video_prompt": "Mai walks steadily from left to right across the rooftop",
                    "workflow_preset_id": wf_end,
                    "image_provider_id": "comfyui", "image_model": "workflow",
                })

    for take, name in ((take_open, "open"), (take_land, "land")):
        call("POST", f"/api/projects/{pid}/takes/{take['id']}/continuity-frame",
             name=f"capture-{name}", json={}, expect=(200, 201))

    start_status = call("PUT", f"/api/projects/{pid}/scenes/{sid}/shots/{clip['id']}/continuity",
                        name="bind-start", json={"source_take_id": take_open["id"]})
    check("the clip starts from the first approved still",
          start_status.get("source_take_id") == take_open["id"], json.dumps(start_status)[:300])

    end_status = call("PUT", f"/api/projects/{pid}/scenes/{sid}/shots/{clip['id']}/end-frame",
                      name="bind-end", json={"source_take_id": take_land["id"]})
    check("the clip is told which frame to land on",
          end_status.get("end_frame_take_id") == take_land["id"], json.dumps(end_status)[:300])
    check("both ends are bound at once, and neither displaced the other",
          end_status.get("source_take_id") == take_open["id"]
          and end_status.get("end_frame_take_id") == take_land["id"],
          json.dumps({"start": end_status.get("source_take_id"),
                      "end": end_status.get("end_frame_take_id")}))
    check("binding the landing raised no problems",
          not end_status.get("problems"), json.dumps(end_status.get("problems")))

    print("\n=== 3. What the provider actually received ===")
    jobs = call("POST", f"/api/projects/{pid}/generate", name="generate-clip",
                json={"shot_ids": [clip["id"]], "confirm_paid_generation": False})
    settled = settle(pid, [j["id"] for j in jobs], 1200.0)
    record("jobs-clip", settled)
    check("the clip rendered", all(j["status"] == "Completed" for j in settled),
          json.dumps([{"s": j["status"], "e": j.get("error_message")} for j in settled])[:500])

    job = settled[0]
    provenance = job.get("reference_provenance") or {}
    landing = provenance.get("end_frame") or {}
    check("the landing is recorded apart from the conditioning",
          bool(landing.get("take_id")), json.dumps(provenance)[:400])
    check("the landing came from the second still",
          landing.get("take_id") == take_land["id"], str(landing.get("take_id")))
    check("the landing reached last_frame, not a reference slot",
          landing.get("comfyui", {}).get("mapping", {}).get("nodeId")
          not in {img["comfyui"]["mapping"]["nodeId"]
                  for img in provenance.get("images", []) if img.get("submitted")},
          json.dumps(landing.get("comfyui", {}).get("mapping")))
    check("the payload names a distinct upload for the landing",
          bool(job["parameter_map"].get("endFrameImage"))
          and job["parameter_map"]["endFrameImage"] != job["parameter_map"].get("referenceImage"),
          json.dumps({k: v for k, v in job["parameter_map"].items() if "Image" in k}))

    print("\n=== 4. The clip really lands where it was told ===")
    clip_take = call("GET", f"/api/shots/{clip['id']}/takes", name="takes-clip")[0]
    clip_path = clip_take["file_path"]
    check("a clip was produced", clip_path.lower().endswith(".mp4"), clip_path)

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    last_frame = str(EVIDENCE / "clip-last-frame.png")
    first_frame = str(EVIDENCE / "clip-first-frame.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.2", "-i", clip_path,
                    "-update", "1", "-frames:v", "1", last_frame], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", clip_path,
                    "-update", "1", "-frames:v", "1", first_frame], check=True)

    to_landing = mean_abs_difference(last_frame, take_land["file_path"])
    to_opening = mean_abs_difference(last_frame, take_open["file_path"])
    record("frame-distances", {"last_vs_landing": to_landing, "last_vs_opening": to_opening})
    check(
        "the clip's final frame resembles the landing more than the opening",
        to_landing < to_opening,
        f"distance to landing {to_landing:.2f} vs to opening {to_opening:.2f}",
    )

    summary = {
        "project_id": pid, "workflow_id": wf_end,
        "shot_open": shot_open["id"], "shot_land": shot_land["id"], "clip": clip["id"],
        "last_vs_landing": to_landing, "last_vs_opening": to_opening,
        "elapsed_sec": round(time.time() - started, 1),
        "checks": checks,
        "passed": sum(1 for c in checks if c["passed"]),
        "failed": sum(1 for c in checks if not c["passed"]),
    }
    (EVIDENCE / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{summary['passed']} passed, {summary['failed']} failed in {summary['elapsed_sec']}s")
    print(f"Evidence: {EVIDENCE}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except E2EFailure as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        sys.exit(1)
