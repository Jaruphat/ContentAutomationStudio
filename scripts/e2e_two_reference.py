"""Prove a shot can carry identity and continuity into the same render.

With one reference slot these compete: the hand-off frame wins and the
character's face survives only as far as the previous clip carried it. This
walks the two-slot path against a live ComfyUI and asserts that both images
reach the provider - the frame in slot one, because it is what the shot
continues from and what sizes the canvas, and the canonical view in slot two,
because it is what says who this is.

Needs the two-reference Boogu workflow registered; pass its id as
CAS_E2E_WF_EDIT2 or let it be discovered by name.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE = os.environ.get("CAS_E2E_BASE", "http://127.0.0.1:8001")
WF_T2I = os.environ.get("CAS_E2E_WF_T2I", "359c2852-f880-430f-a096-07e6ef5625a3")
WF_EDIT1 = os.environ.get("CAS_E2E_WF_EDIT", "75a73b44-5c6f-4661-87f6-26e66a639efd")
TIMEOUT = 30
EVIDENCE = Path(__file__).resolve().parents[1] / "backend" / "data" / "e2e_evidence" / "two-reference"


class E2EFailure(AssertionError):
    """A promise the two-slot path makes that this run found broken."""


checks: list[dict[str, Any]] = []
step = 0


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
        raise E2EFailure(
            f"{method} {path} -> {response.status_code}, expected {allowed}: "
            f"{json.dumps(body, default=str)[:500]}"
        )
    return body


def check(label: str, condition: bool, detail: str = "") -> None:
    checks.append({"check": label, "passed": bool(condition), "detail": detail})
    print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + ("" if condition else f" - {detail}"))
    if not condition:
        raise E2EFailure(f"{label}: {detail}")


def settle(project_id: str, job_ids: list[str], budget: float) -> list[dict]:
    deadline = time.time() + budget
    terminal = {"Completed", "Failed", "Cancelled"}
    last: list[dict] = []
    while time.time() < deadline:
        jobs = requests.get(f"{BASE}/api/projects/{project_id}/jobs", timeout=TIMEOUT).json()
        last = [job for job in jobs if job["id"] in job_ids]
        if last and all(job["status"] in terminal for job in last):
            return last
        time.sleep(3)
    raise E2EFailure(f"jobs did not settle in {budget}s")


def resolve_two_reference_workflow() -> str:
    configured = os.environ.get("CAS_E2E_WF_EDIT2")
    if configured:
        return configured
    for workflow in requests.get(f"{BASE}/api/workflows", timeout=TIMEOUT).json():
        detail = requests.get(f"{BASE}/api/workflows/{workflow['id']}", timeout=TIMEOUT).json()
        mapping = detail.get("parameter_mapping") or {}
        if "referenceImage" in mapping and "referenceImage2" in mapping:
            return workflow["id"]
    raise E2EFailure(
        "No registered workflow maps two reference slots. Import the "
        "two-reference graph and map referenceImage and referenceImage2."
    )


def main() -> int:
    started = time.time()
    wf_edit2 = resolve_two_reference_workflow()
    print(f"two-reference workflow: {wf_edit2}")

    print("\n=== 1. Project and approved character set ===")
    project = call("POST", "/api/projects", name="project", expect=201, json={
        "title": "E2E สองอ้างอิงพร้อมกัน",
        "aspect_ratio": "16:9", "target_resolution": "1280x720", "frame_rate": 24.0,
        "default_image_workflow_id": WF_EDIT1,
    })
    pid = project["id"]

    cset = call("POST", f"/api/projects/{pid}/character-sets", name="character-set", expect=201, json={
        "name": "Mai, the courier",
        "appearance": "young woman, short black bob, amber eyes, small scar on left brow",
        "wardrobe": "teal weatherproof courier jacket, grey cargo trousers, worn brown boots",
        "palette": "teal, warm grey, amber",
        "identity_tokens": "consistent face, consistent wardrobe, same person",
    })
    set_id = cset["id"]
    version = call("POST", f"/api/projects/{pid}/character-sets/{set_id}/versions",
                   name="version", expect=201, json={"slots": ["full_body"]})
    generated = call(
        "POST", f"/api/projects/{pid}/character-sets/{set_id}/versions/{version['id']}/generate",
        name="sheet", timeout=600.0,
        json={"provider_id": "comfyui", "model": "workflow", "workflow_id": WF_T2I,
              "seed": 424242, "width": 768, "height": 768, "confirm_paid_generation": False},
    )
    check("canonical view rendered", bool(generated["views"][0].get("reference_image_id")),
          json.dumps(generated["views"])[:300])
    call("POST", f"/api/projects/{pid}/character-sets/{set_id}/versions/{version['id']}/approve",
         name="approved")

    print("\n=== 2. Shot A establishes the scene ===")
    scene = call("POST", f"/api/projects/{pid}/scenes", name="scene", expect=201,
                 json={"order": 1, "title": "Rooftop hand-off"})
    sid = scene["id"]
    shot_a = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots", name="shot-a", expect=201, json={
        "order": 1, "subject": "Mai the courier", "planned_duration_sec": 4.0,
        "generation_mode": "image",
        "image_prompt": "Mai the courier steps onto a windy rooftop at dusk, parcel under one arm, cinematic",
        "character_set_ids": [set_id], "workflow_preset_id": WF_EDIT1,
        "image_provider_id": "comfyui", "image_model": "workflow",
    })

    # Putting this shot on the two-input graph would leave one input holding
    # whatever image the workflow was exported with, so it is refused.
    call("PUT", f"/api/projects/{pid}/scenes/{sid}/shots/{shot_a['id']}",
         name="shot-a-on-two-slot", json={"workflow_preset_id": wf_edit2})
    blocked = call("GET", f"/api/projects/{pid}/preflight", name="preflight-two-slot")
    messages = [
        text
        for entry in blocked.get("issues", [])
        if entry.get("shot_id") == shot_a["id"]
        for text in entry.get("issues", [])
    ]
    check("one image cannot be sent into a two-input graph",
          any("unfilled" in text for text in messages), json.dumps(messages)[:400])
    call("PUT", f"/api/projects/{pid}/scenes/{sid}/shots/{shot_a['id']}",
         name="shot-a-back", json={"workflow_preset_id": WF_EDIT1})

    jobs = call("POST", f"/api/projects/{pid}/generate", name="generate-a",
                json={"shot_ids": [shot_a["id"]], "confirm_paid_generation": False})
    settled = settle(pid, [j["id"] for j in jobs], 400.0)
    record("jobs-a", settled)
    check("shot A completed", all(j["status"] == "Completed" for j in settled),
          json.dumps([{"s": j["status"], "e": j.get("error_message")} for j in settled]))
    take_a = call("GET", f"/api/shots/{shot_a['id']}/takes", name="takes-a")[0]
    take_a = call("POST", f"/api/takes/{take_a['id']}/approve", name="approve-a")

    print("\n=== 3. Shot B carries both the hand-off and the identity ===")
    shot_b = call("POST", f"/api/projects/{pid}/scenes/{sid}/shots", name="shot-b", expect=201, json={
        "order": 2, "subject": "Mai the courier", "planned_duration_sec": 4.0,
        "generation_mode": "image",
        "image_prompt": "Mai the courier turns to face the waiting client, same rooftop, cinematic",
        "character_set_ids": [set_id], "workflow_preset_id": wf_edit2,
        "image_provider_id": "comfyui", "image_model": "workflow",
    })
    call("POST", f"/api/projects/{pid}/takes/{take_a['id']}/continuity-frame",
         name="frame", json={}, expect=(200, 201))
    status = call("PUT", f"/api/projects/{pid}/scenes/{sid}/shots/{shot_b['id']}/continuity",
                  name="bind", json={"source_take_id": take_a["id"]})
    check("continuity bound cleanly", not status.get("problems"), json.dumps(status.get("problems")))

    jobs_b = call("POST", f"/api/projects/{pid}/generate", name="generate-b",
                  json={"shot_ids": [shot_b["id"]], "confirm_paid_generation": False})
    settled_b = settle(pid, [j["id"] for j in jobs_b], 400.0)
    record("jobs-b", settled_b)
    check("shot B completed", all(j["status"] == "Completed" for j in settled_b),
          json.dumps([{"s": j["status"], "e": j.get("error_message")} for j in settled_b]))

    job_b = settled_b[0]
    images = (job_b.get("reference_provenance") or {}).get("images", [])
    submitted = [img for img in images if img.get("submitted")]
    sources = [img.get("source") for img in submitted]
    check("both slots were filled", len(submitted) == 2, json.dumps(images)[:700])
    check("slot 1 is the hand-off frame", sources[:1] == ["continuity"], str(sources))
    check("slot 2 is the canonical identity", sources[1:2] == ["character_set"], str(sources))

    slots = [img.get("comfyui", {}).get("mapping", {}) for img in submitted]
    check("each image bound to its own node input",
          slots[0].get("nodeId") != slots[1].get("nodeId"), json.dumps(slots))
    check("the payload names two distinct uploads",
          job_b["parameter_map"].get("referenceImage") != job_b["parameter_map"].get("referenceImage2")
          and bool(job_b["parameter_map"].get("referenceImage2")),
          json.dumps({k: v for k, v in job_b["parameter_map"].items() if "reference" in k}))

    take_b = call("GET", f"/api/shots/{shot_b['id']}/takes", name="takes-b")[0]
    check("shot B produced media", bool(take_b.get("file_path")), json.dumps(take_b)[:300])

    summary = {
        "project_id": pid, "workflow_id": wf_edit2,
        "shot_a": shot_a["id"], "shot_b": shot_b["id"],
        "take_a": take_a["id"], "take_b": take_b["id"],
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
