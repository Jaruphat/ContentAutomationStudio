"""End-to-end test exercising the full vertical slice via HTTP API."""
import io
import json
import os
import sys
import time

import requests

# Target the running backend. ComfyUI occupies 8000 on this workstation, so the
# application backend defaults to 8001; override with CAS_E2E_BASE.
BASE = os.environ.get("CAS_E2E_BASE", "http://127.0.0.1:8001/api")

# A minimal ComfyUI API-format workflow JSON for testing
MOCK_WORKFLOW_JSON = json.dumps({
    "6": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["4", 0]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": "", "clip": ["4", 0]},
    },
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "seed": 0,
            "steps": 20,
            "cfg": 7,
            "sampler_name": "euler",
            "scheduler": "normal",
            "denoise": 1,
            "model": ["4", 0],
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"width": 1024, "height": 576, "batch_size": 1},
    },
    "18": {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": "output", "images": ["8", 0]},
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "model.safetensors"},
    },
    "8": {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    },
}).encode("utf-8")


def main():
    errors = []

    def check(condition, msg):
        if not condition:
            errors.append(msg)
            print(f"  FAIL: {msg}")
        return condition

    # 1. Health check
    print("=== Health Check ===")
    h = requests.get(f"{BASE}/health").json()
    print(f"  Status: {h['status']}, Mock: {h['comfyui']['mock']}")
    check(h["status"] == "ok", "Health status should be ok")

    # 2. Import a mock workflow
    print("\n=== Importing Mock Workflow ===")
    wf_resp = requests.post(
        f"{BASE}/workflows/import",
        files={"file": ("h3-image-api.json", io.BytesIO(MOCK_WORKFLOW_JSON), "application/json")},
        data={"name": "H3 Image v1", "purpose": "image", "version": "1.0"},
    )
    check(wf_resp.status_code == 201, f"Workflow import should return 201, got {wf_resp.status_code}")
    workflow = wf_resp.json()
    wf_id = workflow["id"]
    print(f"  Workflow: {wf_id} - {workflow['name']}")
    check(workflow["sha256_hash"] != "", "Workflow should have SHA-256 hash")

    # 3. Set parameter mapping
    print("\n=== Setting Workflow Mapping ===")
    mapping_resp = requests.put(f"{BASE}/workflows/{wf_id}/mapping", json={
        "parameter_mapping": {
            "positivePrompt": {"nodeId": "6", "field": "text"},
            "negativePrompt": {"nodeId": "7", "field": "text"},
            "seed": {"nodeId": "3", "field": "seed"},
            "width": {"nodeId": "5", "field": "width"},
            "height": {"nodeId": "5", "field": "height"},
        },
        "output_mapping": [
            {"nodeId": "18", "type": "image"},
        ],
    })
    check(mapping_resp.status_code == 200, f"Mapping update should return 200, got {mapping_resp.status_code}")

    # 4. Validate workflow mapping
    print("\n=== Validating Workflow ===")
    val_resp = requests.post(f"{BASE}/workflows/{wf_id}/validate").json()
    print(f"  Valid: {val_resp['valid']}, Errors: {val_resp['errors']}, Warnings: {val_resp['warnings']}")
    check(val_resp["valid"], "Workflow mapping should be valid")

    # 5. Create project with workflow defaults
    print("\n=== Creating Project ===")
    proj = requests.post(f"{BASE}/projects", json={
        "title": "The Lost Garden",
        "objective": "A 3-minute short film about discovery",
        "audience": "General",
        "content_type": "short-film",
        "aspect_ratio": "16:9",
        "target_resolution": "1920x1080",
        "target_duration_sec": 180,
        "frame_rate": 24,
        "language": "en",
        "brief_text": "A young explorer discovers a hidden garden in an abandoned city",
        "plot_text": "Mira walks through abandoned streets, finds a greenhouse, enters and discovers a living garden.",
        "default_image_workflow_id": wf_id,
    }).json()
    pid = proj["id"]
    print(f"  Project: {pid} - {proj['title']}")

    # 6. Add characters
    print("\n=== Adding Characters ===")
    char1 = requests.post(f"{BASE}/projects/{pid}/characters", json={
        "name": "Mira",
        "role": "protagonist",
        "age_range": "25-30",
        "appearance": "Short dark hair, olive skin, determined eyes",
        "clothing": "Weathered explorer outfit, leather boots, utility belt",
        "prompt_tokens": "young woman, short dark hair, olive skin, explorer outfit",
    }).json()
    print(f"  Character: {char1['name']}")

    char2 = requests.post(f"{BASE}/projects/{pid}/characters", json={
        "name": "The Garden Spirit",
        "role": "guide",
        "age_range": "ageless",
        "appearance": "Translucent figure made of light and leaves",
        "prompt_tokens": "ethereal spirit, translucent, leaf patterns, glowing",
    }).json()
    print(f"  Character: {char2['name']}")

    # 7. Add locations
    print("\n=== Adding Locations ===")
    loc1 = requests.post(f"{BASE}/projects/{pid}/locations", json={
        "name": "Abandoned City Streets",
        "description": "Overgrown urban landscape with crumbling buildings",
        "time_of_day": "golden hour",
        "lighting": "warm directional sunlight through broken structures",
        "palette": "muted grays, warm amber highlights",
    }).json()
    print(f"  Location: {loc1['name']}")

    loc2 = requests.post(f"{BASE}/projects/{pid}/locations", json={
        "name": "Hidden Greenhouse",
        "description": "Large Victorian greenhouse, glass panels mostly intact, lush vegetation",
        "time_of_day": "afternoon",
        "lighting": "dappled sunlight through glass, green-tinted ambient",
        "palette": "rich greens, golden light, glass reflections",
    }).json()
    print(f"  Location: {loc2['name']}")

    loc3 = requests.post(f"{BASE}/projects/{pid}/locations", json={
        "name": "Garden Interior",
        "description": "Deep inside the greenhouse, bioluminescent plants",
        "time_of_day": "afternoon",
        "lighting": "bioluminescent glow mixed with filtered sunlight",
        "palette": "deep greens, cyan bioluminescence, golden accents",
    }).json()
    print(f"  Location: {loc3['name']}")

    # 8. Add style
    print("\n=== Adding Style ===")
    style = requests.post(f"{BASE}/projects/{pid}/styles", json={
        "medium": "cinematic digital art",
        "genre": "sci-fi exploration",
        "visual_keywords": "cinematic, atmospheric, volumetric lighting, film grain",
        "camera_language": "slow deliberate movements, wide establishing shots",
        "negative_constraints": "cartoon, anime, text, watermark, blurry, deformed",
    }).json()
    print(f"  Style: {style['medium']}")

    # 9. Create 3 scenes
    print("\n=== Creating Scenes ===")
    scenes = []
    scene_data = [
        {
            "order": 1, "title": "The Search",
            "purpose": "Establish world and character",
            "summary": "Mira explores abandoned streets looking for signs of life",
            "planned_duration_sec": 60,
            "character_ids": [char1["id"]],
            "location_id": loc1["id"],
        },
        {
            "order": 2, "title": "Discovery",
            "purpose": "Rising action and wonder",
            "summary": "Mira finds the greenhouse and enters cautiously",
            "planned_duration_sec": 60,
            "character_ids": [char1["id"]],
            "location_id": loc2["id"],
        },
        {
            "order": 3, "title": "Revelation",
            "purpose": "Climax and resolution",
            "summary": "Mira meets the garden spirit and garden responds to her presence",
            "planned_duration_sec": 60,
            "character_ids": [char1["id"], char2["id"]],
            "location_id": loc2["id"],
        },
    ]
    for sd in scene_data:
        s = requests.post(f"{BASE}/projects/{pid}/scenes", json=sd).json()
        scenes.append(s)
        print(f"  Scene {s['order']}: {s['title']}")

    # 10. Create 9 shots (3 per scene)
    print("\n=== Creating Shots ===")
    shots = []
    shot_configs = [
        (scenes[0]["id"], 1, "wide shot", "high angle", "slow pan",
         "Aerial view of abandoned city", "Camera descends over ruins", "image", 6),
        (scenes[0]["id"], 2, "medium shot", "eye level", "tracking",
         "Mira walking through streets", "Walking cautiously, looking around", "image", 5),
        (scenes[0]["id"], 3, "close-up", "low angle", "static",
         "Mira spots the greenhouse", "Eyes widen with curiosity", "image", 4),
        (scenes[1]["id"], 1, "wide shot", "eye level", "slow push-in",
         "Greenhouse exterior", "Camera approaches the structure", "image", 5),
        (scenes[1]["id"], 2, "medium shot", "eye level", "handheld",
         "Mira enters greenhouse", "Pushing through vines at entrance", "image", 5),
        (scenes[1]["id"], 3, "wide shot", "low angle", "tilt up",
         "Interior reveal", "Full lush garden revealed", "image", 5),
        (scenes[2]["id"], 1, "close-up", "eye level", "static",
         "Mira touches a flower", "Gentle touch, flower responds with light", "image", 4),
        (scenes[2]["id"], 2, "medium shot", "eye level", "slow orbit",
         "Spirit appears", "Garden spirit materializes from light", "image", 6),
        (scenes[2]["id"], 3, "wide shot", "bird eye", "crane up",
         "Garden blooms", "Entire garden illuminates with life", "image", 5),
    ]
    for sc_id, order, stype, angle, movement, subject, action, mode, dur in shot_configs:
        sh = requests.post(
            f"{BASE}/projects/{pid}/scenes/{sc_id}/shots",
            json={
                "order": order,
                "shot_type": stype,
                "camera_angle": angle,
                "camera_movement": movement,
                "subject": subject,
                "action": action,
                "generation_mode": mode,
                "planned_duration_sec": dur,
                "image_prompt": f"{subject}, {action}",
                "negative_prompt": "blurry, deformed, text, watermark",
                "status": "Ready",
            },
        ).json()
        shots.append(sh)
        sc_num = [s["id"] for s in scenes].index(sc_id) + 1
        print(f"  Shot {order} (Scene {sc_num}): {subject[:40]}")

    print(f"\n  Total shots created: {len(shots)}")
    check(len(shots) == 9, "Should create 9 shots")

    # 11. Preflight
    print("\n=== Preflight Validation ===")
    pf = requests.get(f"{BASE}/projects/{pid}/preflight").json()
    print(f"  Ready: {pf['ready']}, Total: {pf['total_shots']}, Ready: {pf['ready_shots']}")
    check(pf["ready"], "Preflight should pass with workflow assigned via project default")
    check(pf["total_shots"] == 9, "Should have 9 total shots")
    check(pf["ready_shots"] == 9, "All 9 shots should be ready")

    # 12. Generate
    print("\n=== Starting Generation ===")
    gen_resp = requests.post(f"{BASE}/projects/{pid}/generate", json={"shot_ids": None})
    check(gen_resp.status_code == 200, f"Generate should return 200, got {gen_resp.status_code}")
    gen_jobs = gen_resp.json()
    print(f"  Jobs created: {len(gen_jobs)}")
    check(len(gen_jobs) == 9, "Should create 9 generation jobs")

    # 13. Wait for mock jobs to complete
    print("\n=== Waiting for jobs to complete ===")
    for i in range(60):
        time.sleep(1)
        jobs = requests.get(f"{BASE}/projects/{pid}/jobs").json()
        completed = sum(1 for j in jobs if j["status"] == "Completed")
        print(f"  {completed}/{len(jobs)} completed")
        if completed == len(jobs):
            break

    jobs = requests.get(f"{BASE}/projects/{pid}/jobs").json()
    all_done = all(j["status"] == "Completed" for j in jobs)
    check(all_done, "All jobs should be Completed")

    # 14. List and approve takes
    print("\n=== Reviewing Takes ===")
    takes = requests.get(f"{BASE}/projects/{pid}/takes").json()
    print(f"  Total takes: {len(takes)}")
    check(len(takes) == 9, "Should have 9 takes (one per shot)")

    for t in takes:
        r = requests.post(
            f"{BASE}/takes/{t['id']}/approve",
            json={"rating": 5, "notes": "Looks great!"},
        )
        check(r.status_code == 200, f"Approve take should return 200, got {r.status_code}")
        print(f"  Approved take {t['id'][:8]}...")

    # 15. Build timeline
    print("\n=== Building Timeline ===")
    tl_resp = requests.post(f"{BASE}/projects/{pid}/timeline/build")
    check(tl_resp.status_code == 200, f"Build timeline should return 200, got {tl_resp.status_code}")
    tl = tl_resp.json()
    print(f"  Timeline items: {len(tl['items'])}")
    check(len(tl["items"]) == 9, "Timeline should have 9 items")

    for item in tl["items"]:
        print(f"    [{item['order']}] Duration: {item['duration_sec']}s")

    # 16. Render plan
    print("\n=== Render Plan ===")
    rp_resp = requests.post(f"{BASE}/projects/{pid}/render-plan")
    check(rp_resp.status_code == 200, f"Render plan should return 200, got {rp_resp.status_code}")
    rp = rp_resp.json()
    print(f"  Timeline items: {rp['timeline_items']}")
    print(f"  FFmpeg available: {rp['ffmpeg_available']}")
    print(f"  Commands: {len(rp['commands'])}")
    print(f"  Warnings: {rp['warnings']}")
    check(len(rp["timeline_items"]) == 9, "Should have 9 timeline items")

    # 17. Exports
    print("\n=== Exports ===")

    sb_json = requests.get(f"{BASE}/projects/{pid}/export/storyboard?format=json")
    check(sb_json.status_code == 200, "Storyboard JSON export should work")
    sb_data = sb_json.json()
    print(f"  Storyboard JSON: {len(json.dumps(sb_data))} bytes")

    sb_csv = requests.get(f"{BASE}/projects/{pid}/export/storyboard?format=csv")
    check(sb_csv.status_code == 200, "Storyboard CSV export should work")
    print(f"  Storyboard CSV: {len(sb_csv.text)} chars")
    check(len(sb_csv.text) > 0, "CSV export should have content")

    sb_md = requests.get(f"{BASE}/projects/{pid}/export/storyboard?format=markdown")
    check(sb_md.status_code == 200, "Storyboard Markdown export should work")
    print(f"  Storyboard MD: {len(sb_md.text)} chars")
    check(len(sb_md.text) > 0, "Markdown export should have content")

    pr_resp = requests.get(f"{BASE}/projects/{pid}/export/prompts")
    check(pr_resp.status_code == 200, "Prompts export should work")
    pr = pr_resp.json()
    print(f"  Prompts export: {pr['prompt_count']} prompts")
    check(pr["prompt_count"] == 9, "Prompt export should have 9 prompts")

    mn_resp = requests.get(f"{BASE}/projects/{pid}/export/manifest")
    check(mn_resp.status_code == 200, "Manifest export should work")
    mn = mn_resp.json()
    print(f"  Manifest: {mn['job_count']} jobs")
    check(mn["job_count"] == 9, "Manifest should have 9 jobs")

    tm_resp = requests.get(f"{BASE}/projects/{pid}/export/timeline-manifest")
    check(tm_resp.status_code == 200, "Timeline manifest export should work")
    tm = tm_resp.json()
    print(f"  Timeline manifest: {tm['item_count']} items")
    check(tm["item_count"] == 9, "Timeline manifest should have 9 items")

    pa_resp = requests.get(f"{BASE}/projects/{pid}/export/project-archive")
    check(pa_resp.status_code == 200, "Project archive export should work")
    pa = pa_resp.json()
    print(f"  Project archive keys: {list(pa.keys())}")

    # 18. Persistence check
    print("\n=== Persistence Check ===")
    proj2 = requests.get(f"{BASE}/projects/{pid}").json()
    print(f"  Project still exists: {proj2['title']}")
    check(proj2["title"] == "The Lost Garden", "Project should persist")

    scenes2 = requests.get(f"{BASE}/projects/{pid}/scenes").json()
    print(f"  Scenes persisted: {len(scenes2)}")
    check(len(scenes2) == 3, "3 scenes should persist")

    takes2 = requests.get(f"{BASE}/projects/{pid}/takes").json()
    approved_count = sum(1 for t in takes2 if t["review_status"] == "Approved")
    print(f"  Approved takes: {approved_count}")
    check(approved_count == 9, "All 9 takes should remain approved")

    # Summary
    print("\n" + "=" * 50)
    if errors:
        print(f"FAILURES: {len(errors)}")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("ALL E2E TESTS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
