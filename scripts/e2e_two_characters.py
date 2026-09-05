"""Two named characters in one shot, proved against a live ComfyUI.

A shot has always been able to bind more than one character set. What the
resolver did with them was the problem: it emitted every canonical view of
every set in set order, so a two-input workflow given a hare and a tortoise
received the hare's full body and the hare's front view, and drew two hares.

This checks the fix where it matters - at the provider boundary. Both
characters must physically reach ComfyUI, on separate node inputs, each from
its own approved character set. A clip that merely renders proves nothing:
two hares render perfectly well.
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
TIMEOUT = 30
EVIDENCE = Path(__file__).resolve().parents[1] / "backend" / "data" / "e2e_evidence" / "two-characters"

CAST = [
    {
        "name": "Bram the hare",
        "appearance": "anthropomorphic brown hare, long ears, amber eyes, lean and quick",
        "wardrobe": "red running vest, white number bib, worn canvas shoes",
        "palette": "russet, red, cream",
        "identity_tokens": "same hare, consistent brown fur and red vest",
        "negative_tokens": "tortoise, turtle, different animal, extra limbs",
    },
    {
        "name": "Odo the tortoise",
        "appearance": "anthropomorphic tortoise, domed olive shell, wrinkled green skin, calm eyes",
        "wardrobe": "small round spectacles, blue knitted scarf",
        "palette": "olive, moss, slate blue",
        "identity_tokens": "same tortoise, consistent olive shell and blue scarf",
        "negative_tokens": "hare, rabbit, different animal, extra limbs",
    },
]

checks: list[dict[str, Any]] = []
step = 0


class E2EFailure(AssertionError):
    """A promise the multi-character path makes that this run found broken."""


def record(name: str, payload: Any) -> None:
    global step
    step += 1
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{step:02d}-{name}.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8")


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
    last = ""
    while time.time() < deadline:
        jobs = [j for j in call("GET", f"/api/projects/{pid}/jobs", name="jobs") if j["id"] in job_ids]
        running = next((j for j in jobs if j["status"] == "Running"), None)
        note = (running.get("progress_stage") or "running") if running else "waiting"
        if note != last:
            print(f"    {note}", flush=True)
            last = note
        if jobs and all(j["status"] in terminal for j in jobs):
            return jobs
        time.sleep(5)
    raise E2EFailure(f"jobs did not settle in {budget}s")


def resolve_two_reference_video_workflow() -> str:
    configured = os.environ.get("CAS_E2E_WF_R2V2")
    if configured:
        return configured
    for workflow in requests.get(f"{BASE}/api/workflows", timeout=TIMEOUT).json():
        detail = requests.get(f"{BASE}/api/workflows/{workflow['id']}", timeout=TIMEOUT).json()
        mapping = detail.get("parameter_mapping") or {}
        if (detail.get("purpose") in ("image-to-video", "text-to-video")
                and "referenceImage" in mapping and "referenceImage2" in mapping):
            return workflow["id"]
    raise E2EFailure("No video workflow maps two reference slots.")


def main() -> int:
    started = time.time()
    workflow_id = resolve_two_reference_video_workflow()
    print(f"two-reference video workflow: {workflow_id}")

    print("\n=== 1. Two characters, each with an approved canonical set ===")
    pid = call("POST", "/api/projects", name="project", expect=201, json={
        "title": "E2E กระต่ายกับเต่า",
        "aspect_ratio": "9:5", "target_resolution": "864x480", "frame_rate": 24.0,
        "default_video_workflow_id": workflow_id,
    })["id"]

    set_ids: list[str] = []
    for index, member in enumerate(CAST):
        cset = call("POST", f"/api/projects/{pid}/character-sets",
                    name=f"set-{index}", expect=201, json=member)
        version = call("POST", f"/api/projects/{pid}/character-sets/{cset['id']}/versions",
                       name=f"version-{index}", expect=201, json={"slots": ["full_body"]})
        generated = call(
            "POST",
            f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/generate",
            name=f"sheet-{index}", timeout=900.0,
            json={"provider_id": "comfyui", "model": "workflow", "workflow_id": WF_T2I,
                  "seed": 70707 + index * 31, "width": 768, "height": 768,
                  "confirm_paid_generation": False})
        check(f"{member['name']} rendered a canonical view",
              bool(generated["views"][0].get("reference_image_id")),
              json.dumps(generated["views"])[:250])
        call("POST",
             f"/api/projects/{pid}/character-sets/{cset['id']}/versions/{version['id']}/approve",
             name=f"approve-{index}")
        set_ids.append(cset["id"])

    check("the two sets are distinct", len(set(set_ids)) == 2, str(set_ids))

    print("\n=== 2. One shot bound to both ===")
    sid = call("POST", f"/api/projects/{pid}/scenes", name="scene", expect=201,
               json={"order": 1, "title": "The race"})["id"]
    shot = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots", name="shot", expect=201, json={
        "order": 1, "subject": "Bram and Odo",
        "planned_duration_sec": 5.0, "generation_mode": "video",
        "video_prompt": (
            "A brown hare in a red running vest and a tortoise with a blue scarf "
            "stand side by side at the start line of a country road race, storybook "
            "illustration, warm afternoon light, gentle camera drift. "
            "Keep both animals exactly as in the reference images."
        ),
        "character_set_ids": set_ids,
        "workflow_preset_id": workflow_id,
        "image_provider_id": "comfyui", "image_model": "workflow",
    })
    check("the shot carries both character sets",
          shot.get("character_set_ids") == set_ids, str(shot.get("character_set_ids")))

    preflight = call("GET", f"/api/projects/{pid}/preflight", name="preflight")
    issues = [t for e in preflight.get("issues", []) if e.get("shot_id") == shot["id"]
              for t in e.get("issues", [])]
    check("two characters on a two-input workflow preflight clean",
          not issues, json.dumps(issues))

    print("\n=== 3. What ComfyUI actually received ===")
    jobs = call("POST", f"/api/projects/{pid}/generate", name="generate",
                json={"shot_ids": [shot["id"]], "confirm_paid_generation": False})
    settled = settle(pid, [j["id"] for j in jobs], 1800.0)
    record("job", settled)
    check("the shot rendered", all(j["status"] == "Completed" for j in settled),
          json.dumps([{"s": j["status"], "e": j.get("error_message")} for j in settled])[:400])

    job = settled[0]
    submitted = [i for i in (job.get("reference_provenance") or {}).get("images", [])
                 if i.get("submitted")]
    check("two references were submitted", len(submitted) == 2,
          json.dumps([i.get("detail") for i in submitted])[:400])
    names = [i["detail"].get("character_set_name") for i in submitted]
    check("one view from each character, not two of the first",
          len(set(names)) == 2 and set(names) == {c["name"] for c in CAST}, str(names))
    check("each landed on its own node input",
          len({i["comfyui"]["mapping"]["nodeId"] for i in submitted}) == 2,
          json.dumps([i["comfyui"]["mapping"] for i in submitted]))
    check("the payload names two distinct uploads",
          job["parameter_map"].get("referenceImage") != job["parameter_map"].get("referenceImage2"),
          json.dumps({k: v for k, v in job["parameter_map"].items() if "reference" in k}))

    take = call("GET", f"/api/shots/{shot['id']}/takes", name="takes")[0]
    check("a clip was produced", str(take.get("file_path", "")).lower().endswith(".mp4"),
          str(take.get("file_path")))

    # A contact sheet so the two characters can be seen, not just counted.
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    sheet = str(EVIDENCE / "two-characters.png")
    refs = [i["file_path"] for i in submitted]
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", refs[0], "-i", refs[1],
         "-i", take["file_path"], "-filter_complex",
         "[0:v]scale=-1:300,pad=iw+8:308:0:4:color=0x222222[a];"
         "[1:v]scale=-1:300,pad=iw+8:308:0:4:color=0x222222[b];"
         "[2:v]select='eq(n\\,4)+eq(n\\,60)',scale=-1:300,"
         "pad=iw+8:308:0:4:color=0x222222,tile=2x1[c];"
         "[a][b][c]hstack=inputs=3", "-frames:v", "1", sheet],
        check=False, capture_output=True,
    )

    summary = {
        "project_id": pid, "workflow_id": workflow_id, "shot_id": shot["id"],
        "character_set_ids": set_ids, "submitted": names,
        "elapsed_sec": round(time.time() - started, 1), "checks": checks,
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
