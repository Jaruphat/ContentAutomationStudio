"""Produce SF03 by typing it into the running application.

Not a test. This drives the real pages against the real backend on 8001, the
real database and the real ComfyUI, and leaves a real project behind. SF01 and
SF02 were produced by a Python file posting to the API; this is the same
pipeline driven the way a creator drives it.

It refuses to start unless the backend is up, ComfyUI is a *real* provider
rather than the mock, and the dev server is serving. A run against the mock
would produce placeholders and call them an episode.

Usage::

    python scripts/sf03_via_browser.py --phase type
    python scripts/sf03_via_browser.py --phase plates
    python scripts/sf03_via_browser.py --phase generate
    python scripts/sf03_via_browser.py --phase clips
    python scripts/sf03_via_browser.py --phase assemble
    python scripts/sf03_via_browser.py --phase type --headed

Nothing here starts or stops the backend or the dev server: they are the
user's, and a script that restarts them would take the application away from
whoever is watching it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
API = "http://127.0.0.1:8001/api"
APP = "http://localhost:5173"

PHASES = {
    "type": "types SF03",
    "plates": "generates the plates",
    "pin-size": "pins the edit graph",
    "canvas": "sets the canvas",
    "reject-first-pass": "rejects what the first pass",
    "remake": "re-makes the one key image",
    "generate": "generates the key images",
    "run-ready": "runs the shots that are ready",
    "approve-and-run": "approves what is waiting",
    "stop-clips": "stops the clips",
    "remake-clip": "remakes the clip whose first take",
    "place-clip": "puts the remade clip",
    "bind-first": "binds the first clip",
    "review": "reviews the key images",
    "rework": "reworks the two shots",
    "remake-two": "makes the two reworked shots",
    "bind-all": "approves the key images and gives",
    "order": "puts scene one back in the order",
    "redirect": "re-directs the dead opening",
    "opening-graph": "gives the opening clip a graph",
    "opening-frame": "re-makes the opening frame",
    "rebind-opening": "re-points the opening clip",
    "clips": "generates the clips",
    "assemble": "builds the cut and renders",
}


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def preflight() -> None:
    try:
        health = _get(f"{API}/health")
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(
            f"The backend is not answering on 8001 ({exc}). Start it first: "
            "COMFYUI_PROVIDER=real python -m uvicorn app.main:app --port 8001"
        )

    comfy = health.get("comfyui", {})
    if comfy.get("mock"):
        raise SystemExit(
            "ComfyUI is in mock mode. This would produce placeholders and "
            "call them an episode. Restart the backend with "
            "COMFYUI_PROVIDER=real."
        )
    if not comfy.get("online"):
        raise SystemExit(
            f"ComfyUI is not reachable: {comfy.get('error') or 'no reason given'}."
        )

    try:
        urllib.request.urlopen(APP, timeout=5).read(1)
    except (urllib.error.URLError, OSError) as exc:
        raise SystemExit(
            f"The application is not being served at {APP} ({exc}). Run "
            "`npm run dev` in frontend."
        )

    print(f"ComfyUI {comfy.get('version')} on {comfy.get('gpu_info', '')[:48]}")
    print(f"Queue: {health['queue']['queued']} queued, "
          f"{health['queue']['running']} running")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=sorted(PHASES), default="type")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    preflight()
    command = [
        "npx", "playwright", "test",
        "--config", "playwright.production.config.ts",
        "--grep", PHASES[args.phase],
    ]
    if args.headed:
        command.append("--headed")
    return subprocess.run(command, cwd=FRONTEND, shell=os.name == "nt").returncode


if __name__ == "__main__":
    raise SystemExit(main())
