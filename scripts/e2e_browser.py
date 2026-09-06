"""Run the browser walk-through against a backend of its own.

The rest of the end-to-end evidence in this repository was produced by posting
to the API. That proves the backend and says nothing about whether a person
can use the application, so this drives the real pages in a real browser and
types every value into a field a creator can see.

The backend it talks to is deliberately not the one on 8001:

* **Its own database.** ``backend/data/e2e-browser`` is wiped before each run,
  so a walk-through cannot leave a half-finished project in the switcher, and
  a previous run's workflow cannot be picked up by the next one. Nothing
  outside that directory is touched.
* **Mock providers.** No GPU, no API key, no charge. What comes out is a
  deterministic placeholder, which is the point: a walk-through that needs a
  graphics card is a walk-through nobody runs. Picture quality is judged
  elsewhere, on real renders.

Usage::

    python scripts/e2e_browser.py            # run it
    python scripts/e2e_browser.py --headed   # watch it happen

Requires ``npm install`` in ``frontend`` and Chrome installed. Playwright uses
the installed Chrome rather than downloading its own, because the download is
blocked on this machine.
"""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"
DATA_DIR = BACKEND / "data" / "e2e-browser"
PORT = 8011
HEALTH = f"http://127.0.0.1:{PORT}/api/health"


def python_executable() -> str:
    for candidate in (
        BACKEND / ".venv" / "Scripts" / "python.exe",
        BACKEND / ".venv" / "bin" / "python",
    ):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def reset_data_dir() -> None:
    # Guarded because this deletes a tree: only ever the directory this script
    # owns, never the real one beside it.
    assert DATA_DIR.name == "e2e-browser", DATA_DIR
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    DATA_DIR.mkdir(parents=True)


def start_backend() -> subprocess.Popen:
    env = dict(os.environ)
    env.update({
        # The real .env holds a live API key. Skipping it is what makes a
        # billed call impossible from this process rather than merely unlikely.
        "CAS_DISABLE_DOTENV": "1",
        "CAS_AI_PROVIDER": "mock",
        "COMFYUI_PROVIDER": "mock",
        "CAS_DATA_DIR": str(DATA_DIR),
        "CAS_MOCK_QUEUED_SEC": "0.2",
        "CAS_MOCK_RUNNING_SEC": "0.3",
    })
    env.pop("OPENAI_API_KEY", None)
    log = open(DATA_DIR / "backend.log", "w", encoding="utf-8")
    return subprocess.Popen(
        [python_executable(), "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT,
    )


def wait_for_health(timeout: float = 45.0) -> dict:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(HEALTH, timeout=3) as response:
                import json
                return json.loads(response.read())
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = str(exc)
            time.sleep(0.5)
    raise SystemExit(f"The walk-through backend never came up on {PORT}: {last}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true",
                        help="show the browser instead of running it headless")
    parser.add_argument("--grep", default="", help="run only matching tests")
    args = parser.parse_args()

    reset_data_dir()
    backend = start_backend()
    try:
        health = wait_for_health()
        if not health.get("comfyui", {}).get("mock"):
            raise SystemExit(
                "The walk-through backend is not in mock mode. Refusing to "
                "run, because this would submit real jobs."
            )
        print(f"Walk-through backend up on {PORT} with a fresh database "
              f"({health['ai']['default_provider_id']} author, mock ComfyUI).")

        command = ["npx", "playwright", "test"]
        if args.headed:
            command.append("--headed")
        if args.grep:
            command += ["--grep", args.grep]
        result = subprocess.run(command, cwd=FRONTEND, shell=os.name == "nt")
        return result.returncode
    finally:
        if backend.poll() is None:
            backend.send_signal(signal.SIGTERM)
            try:
                backend.wait(timeout=10)
            except subprocess.TimeoutExpired:
                backend.kill()
        print("Walk-through backend stopped.")


if __name__ == "__main__":
    raise SystemExit(main())
