"""End-to-end driver for the character-identity and shot-continuity chain.

Runs against a live backend and, unless ``--mock-media`` is passed, a live
ComfyUI. It walks the whole promised path once:

    character set -> generated canonical views -> approved version
      -> bound to shots -> reference-conditioned scene image -> approved take
      -> image-to-video -> approved video take -> extracted end frame
      -> bound as the next shot's continuity source -> that shot generated
      -> timeline -> render -> exports

and asserts the claims that matter at each step, rather than only that the
call returned 200: that the canonical view really reached the provider, that
an unapproved source really blocks the dependent shot, and that the take's
lineage really names the frame it was conditioned on.

Every response is written to an evidence directory so a failure can be read
after the fact.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE = os.environ.get("CAS_E2E_BASE", "http://127.0.0.1:8001")
TIMEOUT = 30

# Registered on this workstation; overridable so the script is not tied to one
# machine's workflow ids.
WF_T2I = os.environ.get("CAS_E2E_WF_T2I", "359c2852-f880-430f-a096-07e6ef5625a3")
WF_EDIT = os.environ.get("CAS_E2E_WF_EDIT", "75a73b44-5c6f-4661-87f6-26e66a639efd")
WF_I2V = os.environ.get("CAS_E2E_WF_I2V", "711d55b8-fc50-41b3-92eb-d706653fde4f")


class E2EFailure(AssertionError):
    """A promise the app makes that this run found broken."""


class Run:
    def __init__(self, evidence: Path) -> None:
        self.evidence = evidence
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.step = 0
        self.checks: list[dict[str, Any]] = []

    # -- plumbing ---------------------------------------------------------
    def record(self, name: str, payload: Any) -> None:
        self.step += 1
        path = self.evidence / f"{self.step:02d}-{name}.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def call(
        self,
        method: str,
        path: str,
        *,
        name: str,
        expect: int | tuple[int, ...] = 200,
        **kwargs: Any,
    ) -> Any:
        url = f"{BASE}{path}"
        # Generating a character sheet holds the request open for as long as
        # the GPU takes, so the caller sets the budget rather than one global.
        timeout = kwargs.pop("timeout", TIMEOUT)
        response = requests.request(method, url, timeout=timeout, **kwargs)
        try:
            body = response.json()
        except ValueError:
            body = {"_raw": response.text[:2000]}
        self.record(name, {"request": f"{method} {path}", "status": response.status_code, "body": body})
        allowed = (expect,) if isinstance(expect, int) else expect
        if response.status_code not in allowed:
            raise E2EFailure(
                f"{method} {path} returned {response.status_code}, expected {allowed}: "
                f"{json.dumps(body, default=str)[:600]}"
            )
        return body

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        self.checks.append({"check": label, "passed": bool(condition), "detail": detail})
        mark = "PASS" if condition else "FAIL"
        print(f"  [{mark}] {label}" + (f" - {detail}" if detail and not condition else ""))
        if not condition:
            raise E2EFailure(f"{label}: {detail}")

    def stage(self, title: str) -> None:
        print(f"\n=== {title} ===")


def wait_for_jobs(run: Run, project_id: str, job_ids: list[str], *, budget_sec: float) -> list[dict]:
    """Poll until every job leaves the queue, or the budget runs out."""
    deadline = time.time() + budget_sec
    terminal = {"Completed", "Failed", "Cancelled"}
    last: list[dict] = []
    while time.time() < deadline:
        jobs = requests.get(f"{BASE}/api/projects/{project_id}/jobs", timeout=TIMEOUT).json()
        last = [job for job in jobs if job["id"] in job_ids]
        if last and all(job["status"] in terminal for job in last):
            return last
        time.sleep(3)
    raise E2EFailure(
        f"jobs did not settle within {budget_sec}s: "
        + json.dumps([{"id": j["id"], "status": j["status"]} for j in last])
    )


def approve_take(run: Run, take_id: str, name: str) -> dict:
    return run.call("POST", f"/api/takes/{take_id}/approve", name=name)


def latest_take(run: Run, shot_id: str) -> dict:
    takes = run.call("GET", f"/api/shots/{shot_id}/takes", name=f"takes-{shot_id[:8]}")
    if not takes:
        raise E2EFailure(f"shot {shot_id} produced no takes")
    return takes[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evidence",
        default=str(Path(__file__).resolve().parents[1] / "backend" / "data" / "e2e_evidence" / "character-continuity"),
    )
    parser.add_argument(
        "--video-budget",
        type=float,
        default=900.0,
        help="Seconds to wait for the image-to-video job before failing.",
    )
    parser.add_argument(
        "--image-budget",
        type=float,
        default=300.0,
        help="Seconds to wait for an image job before failing.",
    )
    parser.add_argument(
        "--sheet-budget",
        type=float,
        default=600.0,
        help="Seconds to hold the character-sheet generation request open.",
    )
    args = parser.parse_args()

    run = Run(Path(args.evidence))
    started = time.time()

    # ------------------------------------------------------------------
    run.stage("0. Health and providers")
    health = run.call("GET", "/api/health", name="health")
    run.check("backend healthy", health.get("status") == "ok")
    run.check(
        "ComfyUI online",
        bool(health.get("comfyui", {}).get("online")),
        json.dumps(health.get("comfyui")),
    )
    run.check("no startup blockers", not health.get("blockers"), json.dumps(health.get("blockers")))

    # ------------------------------------------------------------------
    run.stage("1. Project")
    project = run.call(
        "POST",
        "/api/projects",
        name="project",
        json={
            "title": "E2E ความต่อเนื่องตัวละคร",  # Unicode path coverage
            "objective": "Prove canonical identity survives a shot hand-off.",
            "aspect_ratio": "16:9",
            "target_resolution": "1280x720",
            "frame_rate": 24.0,
            "default_image_workflow_id": WF_EDIT,
            "default_video_workflow_id": WF_I2V,
        },
        expect=201,
    )
    pid = project["id"]
    print(f"  project {pid}")

    # ------------------------------------------------------------------
    run.stage("2. Character set with canonical views")
    cset = run.call(
        "POST",
        f"/api/projects/{pid}/character-sets",
        name="character-set",
        json={
            "name": "Mai, the courier",
            "appearance": "young woman, short black bob, amber eyes, small scar on left brow",
            "proportions": "slim, 165cm, athletic shoulders",
            "wardrobe": "teal weatherproof courier jacket, grey cargo trousers, worn brown boots",
            "palette": "teal, warm grey, amber",
            "identity_tokens": "consistent face, consistent wardrobe, same person",
            "negative_tokens": "different face, changed hair colour, extra limbs",
        },
        expect=201,
    )
    set_id = cset["id"]

    version = run.call(
        "POST",
        f"/api/projects/{pid}/character-sets/{set_id}/versions",
        name="character-set-version",
        json={"slots": ["full_body", "front", "side"], "notes": "canonical sheet v1"},
        expect=201,
    )
    version_id = version["id"]
    run.check("version drafted three views", len(version.get("views", [])) == 3, str(version.get("views")))

    generated = run.call(
        "POST",
        f"/api/projects/{pid}/character-sets/{set_id}/versions/{version_id}/generate",
        name="character-set-generated",
        json={
            "provider_id": "comfyui",
            "model": "workflow",
            "workflow_id": WF_T2I,
            "seed": 424242,
            "width": 768,
            "height": 768,
            "confirm_paid_generation": False,
        },
        timeout=args.sheet_budget,
    )
    views = generated.get("views", [])
    ready = [v for v in views if v.get("reference_image_id")]
    run.check(
        "every canonical view produced real bytes",
        len(ready) == 3,
        json.dumps([{"slot": v["slot"], "status": v["status"], "error": v.get("error_message")} for v in views]),
    )
    run.check(
        "each view carries a distinct content hash",
        len({v["sha256"] for v in ready}) == 3,
        json.dumps([v["sha256"][:12] for v in ready]),
    )
    for view in ready:
        blob = requests.get(f"{BASE}{view['url']}", timeout=TIMEOUT)
        run.check(
            f"view '{view['slot']}' is downloadable image bytes",
            blob.status_code == 200 and len(blob.content) > 5000,
            f"status={blob.status_code} bytes={len(blob.content)}",
        )
        (run.evidence / f"view-{view['slot']}.png").write_bytes(blob.content)

    approved_version = run.call(
        "POST",
        f"/api/projects/{pid}/character-sets/{set_id}/versions/{version_id}/approve",
        name="character-set-approved",
    )
    run.check("version approved", approved_version.get("status") == "Approved", approved_version.get("status", ""))

    # ------------------------------------------------------------------
    run.stage("3. Scene and two narratively linked shots")
    scene = run.call(
        "POST",
        f"/api/projects/{pid}/scenes",
        name="scene",
        json={"order": 1, "title": "Rooftop hand-off", "purpose": "Mai delivers the parcel."},
        expect=201,
    )
    sid = scene["id"]

    shot_a = run.call(
        "POST",
        f"/api/projects/{pid}/scenes/{sid}/shots",
        name="shot-a",
        json={
            "order": 1,
            "shot_type": "medium",
            "subject": "Mai the courier",
            "action": "steps onto the rooftop, parcel under one arm",
            "environment": "windy rooftop at dusk, city haze behind",
            "planned_duration_sec": 4.0,
            "generation_mode": "image",
            "image_prompt": "Mai the courier steps onto a windy rooftop at dusk, parcel under one arm, city haze behind, cinematic",
            "video_prompt": "slow push in as she steadies herself against the wind",
            "character_set_ids": [set_id],
            "workflow_preset_id": WF_EDIT,
            "image_provider_id": "comfyui",
            "image_model": "workflow",
        },
        expect=201,
    )
    shot_b = run.call(
        "POST",
        f"/api/projects/{pid}/scenes/{sid}/shots",
        name="shot-b",
        json={
            "order": 2,
            "shot_type": "medium",
            "subject": "Mai the courier",
            "action": "turns to face the waiting client",
            "environment": "same rooftop, moments later",
            "planned_duration_sec": 4.0,
            "generation_mode": "image",
            "image_prompt": "Mai the courier turns to face the waiting client on the same rooftop, moments later, cinematic",
            "character_set_ids": [set_id],
            "workflow_preset_id": WF_EDIT,
            "image_provider_id": "comfyui",
            "image_model": "workflow",
        },
        expect=201,
    )
    run.check("shot A bound to the character set", shot_a.get("character_set_ids") == [set_id], str(shot_a.get("character_set_ids")))
    run.check("shot B bound to the character set", shot_b.get("character_set_ids") == [set_id], str(shot_b.get("character_set_ids")))

    # ------------------------------------------------------------------
    run.stage("4. Shot A: canonical identity reaches the provider")
    preflight = run.call("GET", f"/api/projects/{pid}/preflight", name="preflight-a")
    blocking = [entry for entry in preflight.get("issues", []) if entry.get("issues")]
    run.check("preflight clean before generation", not blocking, json.dumps(blocking)[:600])

    jobs = run.call(
        "POST",
        f"/api/projects/{pid}/generate",
        name="generate-a",
        json={"shot_ids": [shot_a["id"]], "confirm_paid_generation": False},
    )
    settled = wait_for_jobs(run, pid, [j["id"] for j in jobs], budget_sec=args.image_budget)
    run.record("jobs-a-settled", settled)
    run.check(
        "shot A image job completed",
        all(j["status"] == "Completed" for j in settled),
        json.dumps([{"status": j["status"], "error": j.get("error_message")} for j in settled]),
    )

    job_a = settled[0]
    run.check(
        "job A records the character set it was conditioned on",
        job_a.get("character_set_ids") == [set_id],
        str(job_a.get("character_set_ids")),
    )
    run.check(
        "job A records the canonical content hash",
        bool(job_a.get("character_set_sha256s")),
        str(job_a.get("character_set_sha256s")),
    )
    submitted = [
        img
        for img in (job_a.get("reference_provenance") or {}).get("images", [])
        if img.get("submitted")
    ]
    run.check(
        "a canonical view was actually submitted to the workflow, not just named",
        any(img.get("source") == "character_set" for img in submitted),
        json.dumps((job_a.get("reference_provenance") or {}).get("images", []))[:800],
    )

    take_a = latest_take(run, shot_a["id"])
    run.check("shot A take has media", bool(take_a.get("file_path") or take_a.get("url")), json.dumps(take_a)[:400])
    take_a = approve_take(run, take_a["id"], "take-a-approved")
    run.check("shot A take approved", take_a["review_status"] == "Approved", take_a["review_status"])

    # ------------------------------------------------------------------
    run.stage("5. Shot A image -> video, then approve the clip")
    run.call(
        "PUT",
        f"/api/projects/{pid}/scenes/{sid}/shots/{shot_a['id']}",
        name="shot-a-to-i2v",
        json={"generation_mode": "image-to-video", "workflow_preset_id": WF_I2V},
    )
    video_jobs = run.call(
        "POST",
        f"/api/projects/{pid}/generate",
        name="generate-a-video",
        json={"shot_ids": [shot_a["id"]], "confirm_paid_generation": False},
    )
    settled_video = wait_for_jobs(run, pid, [j["id"] for j in video_jobs], budget_sec=args.video_budget)
    run.record("jobs-a-video-settled", settled_video)
    run.check(
        "image-to-video job completed",
        all(j["status"] == "Completed" for j in settled_video),
        json.dumps([{"status": j["status"], "error": j.get("error_message")} for j in settled_video]),
    )

    video_take = latest_take(run, shot_a["id"])
    run.check("video take produced a clip", str(video_take.get("file_path", "")).lower().endswith((".mp4", ".webm")), str(video_take.get("file_path")))
    video_take = approve_take(run, video_take["id"], "video-take-approved")

    # ------------------------------------------------------------------
    run.stage("6. Extract the approved clip's end frame")
    frame = run.call(
        "POST",
        f"/api/projects/{pid}/takes/{video_take['id']}/continuity-frame",
        name="continuity-frame",
        json={},
        expect=(200, 201),
    )
    run.check("frame captured real bytes", bool(frame.get("reference_image_id")), json.dumps(frame)[:400])
    run.check("frame records its content hash", bool(frame.get("sha256")), str(frame.get("sha256")))
    run.check(
        "frame sits at the end of the clip",
        frame.get("frame_time_sec", 0) > 0
        and frame["frame_time_sec"] <= frame.get("source_duration_sec", 0) + 0.5,
        f"t={frame.get('frame_time_sec')} duration={frame.get('source_duration_sec')}",
    )
    frame_blob = requests.get(f"{BASE}{frame['url']}", timeout=TIMEOUT)
    run.check("frame is downloadable", frame_blob.status_code == 200 and len(frame_blob.content) > 3000, f"{frame_blob.status_code}/{len(frame_blob.content)}")
    (run.evidence / "continuity-end-frame.png").write_bytes(frame_blob.content)

    # ------------------------------------------------------------------
    run.stage("7. Bind the hand-off to shot B, and prove the gate is real")
    status = run.call(
        "PUT",
        f"/api/projects/{pid}/scenes/{sid}/shots/{shot_b['id']}/continuity",
        name="continuity-bound",
        json={"source_take_id": video_take["id"]},
    )
    run.check("shot B bound to the source take", status.get("source_take_id") == video_take["id"], str(status.get("source_take_id")))
    run.check("binding reports no problems", not status.get("problems"), json.dumps(status.get("problems")))
    run.check("binding names its source shot", status.get("source_shot_id") == shot_a["id"], str(status.get("source_shot_id")))

    # Negative case: withdraw approval and the dependent shot must be blocked.
    run.call("POST", f"/api/takes/{video_take['id']}/reject", name="video-take-rejected", json={"reason": "e2e gate probe"})
    blocked_status = run.call(
        "GET",
        f"/api/projects/{pid}/scenes/{sid}/shots/{shot_b['id']}/continuity",
        name="continuity-blocked",
    )
    run.check(
        "unapproving the source blocks the dependent shot",
        bool(blocked_status.get("problems")),
        "the dependent shot reported no problem after its source lost approval",
    )
    blocked_preflight = run.call("GET", f"/api/projects/{pid}/preflight", name="preflight-blocked")
    shot_b_issues = [
        message
        for entry in blocked_preflight.get("issues", [])
        if entry.get("shot_id") == shot_b["id"]
        for message in entry.get("issues", [])
    ]
    run.check(
        "preflight refuses to generate the dependent shot",
        bool(shot_b_issues),
        json.dumps(blocked_preflight.get("issues"))[:600],
    )
    run.check(
        "the refusal explains what to do about it",
        any("Approve it again" in message for message in shot_b_issues),
        json.dumps(shot_b_issues),
    )
    blocked_generate = run.call(
        "POST",
        f"/api/projects/{pid}/generate",
        name="generate-b-refused",
        json={"shot_ids": [shot_b["id"]], "confirm_paid_generation": False},
        expect=(400, 409, 422),
    )
    run.check("generation itself refuses the stale hand-off", True, json.dumps(blocked_generate)[:300])

    # Restore approval and continue.
    approve_take(run, video_take["id"], "video-take-reapproved")

    # ------------------------------------------------------------------
    run.stage("8. Shot B generated from the hand-off frame")
    recovered = run.call(
        "GET",
        f"/api/projects/{pid}/scenes/{sid}/shots/{shot_b['id']}/continuity",
        name="continuity-recovered",
    )
    run.check("re-approval clears the block", not recovered.get("problems"), json.dumps(recovered.get("problems")))

    jobs_b = run.call(
        "POST",
        f"/api/projects/{pid}/generate",
        name="generate-b",
        json={"shot_ids": [shot_b["id"]], "confirm_paid_generation": False},
    )
    settled_b = wait_for_jobs(run, pid, [j["id"] for j in jobs_b], budget_sec=args.image_budget)
    run.record("jobs-b-settled", settled_b)
    run.check(
        "shot B job completed",
        all(j["status"] == "Completed" for j in settled_b),
        json.dumps([{"status": j["status"], "error": j.get("error_message")} for j in settled_b]),
    )

    job_b = settled_b[0]
    run.check(
        "job B records the take it continues from",
        job_b.get("continuity_source_take_id") == video_take["id"],
        str(job_b.get("continuity_source_take_id")),
    )
    run.check(
        "job B records the exact frame bytes it used",
        job_b.get("continuity_source_sha256") == frame.get("sha256"),
        f"job={job_b.get('continuity_source_sha256')} frame={frame.get('sha256')}",
    )
    run.check(
        "job B still carries the canonical identity in its lineage",
        job_b.get("character_set_ids") == [set_id],
        str(job_b.get("character_set_ids")),
    )
    submitted_b = [
        img for img in (job_b.get("reference_provenance") or {}).get("images", []) if img.get("submitted")
    ]
    run.check(
        "the hand-off frame is what the one-input workflow actually received",
        any(img.get("source") == "continuity" for img in submitted_b),
        json.dumps((job_b.get("reference_provenance") or {}).get("images", []))[:800],
    )

    take_b = approve_take(run, latest_take(run, shot_b["id"])["id"], "take-b-approved")
    run.check("shot B take approved", take_b["review_status"] == "Approved", take_b["review_status"])

    # ------------------------------------------------------------------
    run.stage("9. Staleness: a new canonical version invalidates dependents")
    version2 = run.call(
        "POST",
        f"/api/projects/{pid}/character-sets/{set_id}/versions",
        name="character-set-version-2",
        json={"slots": ["full_body"], "notes": "wardrobe change"},
        expect=201,
    )
    run.call(
        "PUT",
        f"/api/projects/{pid}/character-sets/{set_id}",
        name="character-set-edited",
        json={"wardrobe": "red courier jacket, black trousers"},
    )
    edited = run.call("GET", f"/api/projects/{pid}/character-sets/{set_id}", name="character-set-after-edit")
    run.check(
        "editing identity marks the approved version out of date",
        edited.get("approved_version_is_current") is False,
        str(edited.get("approved_version_is_current")),
    )
    run.record("character-set-version-2-id", {"version_id": version2["id"]})

    # ------------------------------------------------------------------
    run.stage("10. Timeline, render and exports from approved takes only")
    timeline = run.call("POST", f"/api/projects/{pid}/timeline/build", name="timeline", json={})
    items = timeline.get("items", [])
    run.check("timeline built from approved takes", len(items) >= 2, json.dumps(timeline)[:500])
    approved_take_ids = {take_a["id"], take_b["id"], video_take["id"]}
    run.check(
        "every timeline item cites an approved take",
        all(item.get("take_id") in approved_take_ids for item in items),
        json.dumps([item.get("take_id") for item in items]),
    )

    render = run.call(
        "POST", f"/api/projects/{pid}/render", name="render", json={},
        expect=(200, 201, 409), timeout=args.video_budget,
    )
    rendered_path = render.get("output_path") or ""
    if rendered_path and Path(rendered_path).exists():
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", rendered_path],
            capture_output=True, text=True,
        )
        run.record("render-ffprobe", json.loads(probe.stdout or "{}"))
        run.check("rendered file decodes", probe.returncode == 0, probe.stderr[:400])
    else:
        run.check(
            "render said plainly why it produced nothing",
            bool(render.get("reason")),
            json.dumps(render)[:400],
        )

    for export in ("storyboard", "prompts", "timeline-manifest", "project-archive"):
        body = run.call("GET", f"/api/projects/{pid}/export/{export}", name=f"export-{export}")
        run.check(f"export '{export}' parses", body is not None)

    # ------------------------------------------------------------------
    elapsed = time.time() - started
    summary = {
        "project_id": pid,
        "character_set_id": set_id,
        "approved_version_id": version_id,
        "shot_a": shot_a["id"],
        "shot_b": shot_b["id"],
        "video_take_id": video_take["id"],
        "continuity_frame_sha256": frame.get("sha256"),
        "elapsed_sec": round(elapsed, 1),
        "checks": run.checks,
        "passed": sum(1 for c in run.checks if c["passed"]),
        "failed": sum(1 for c in run.checks if not c["passed"]),
    }
    (run.evidence / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{summary['passed']} checks passed, {summary['failed']} failed, in {elapsed:.0f}s")
    print(f"Evidence: {run.evidence}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except E2EFailure as exc:
        print(f"\nE2E FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
