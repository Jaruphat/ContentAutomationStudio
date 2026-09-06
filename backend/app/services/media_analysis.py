"""Bounded, reproducible motion measurements; never an automatic approval.

Sampling at a fixed rate makes the result independent of delivery FPS. Luma
change detects near-static output, but also responds to cuts and flicker. The
report states this limitation and remains separate from a human review score.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SAMPLE_FPS = 8
MAX_SECONDS = 60
NEAR_STATIC_THRESHOLD = 1.0
METHOD = "luma-difference-8fps-144px-v1"


def unavailable(reason: str) -> dict:
    return {"status": "unavailable", "method": METHOD, "reason": reason, "warnings": []}


def summarize(values: list[float]) -> dict:
    values = [value for value in values if math.isfinite(value) and value >= 0]
    if len(values) < 2:
        return unavailable("At least three sampled frames are needed to measure motion.")
    ordered = sorted(values)
    fraction = sum(v < NEAR_STATIC_THRESHOLD for v in values) / len(values)
    warnings = []
    if fraction >= 0.90:
        warnings.append(
            "Very little visual change was detected. Watch whether the intended "
            "action occurs before approving this clip."
        )
    return {
        "status": "measured", "method": METHOD, "sample_fps": SAMPLE_FPS,
        "sampled_frames": len(values) + 1,
        "analyzed_duration_sec": round((len(values) + 1) / SAMPLE_FPS, 3),
        "mean_luma_change": round(sum(values) / len(values), 3),
        "p90_luma_change": round(ordered[min(len(ordered) - 1, int(len(ordered) * .9))], 3),
        "near_static_fraction": round(fraction, 4),
        "near_static_threshold": NEAR_STATIC_THRESHOLD,
        "warnings": warnings,
        "interpretation": (
            "Measured visual change, not a quality score. Camera motion, edits "
            "and flicker also affect it. Near-static means below the stated "
            "threshold, not identical pixels. Inspect the action and continuity."
        ),
        "window_limit_sec": MAX_SECONDS,
    }


def analyze_video(file_path: str) -> dict:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return unavailable("FFmpeg is not installed; the clip has not been measured.")
    source = Path(file_path)
    if not source.is_file():
        return unavailable("The video file is missing.")
    try:
        digest = hashlib.sha256()
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        result = subprocess.run(
            [ffmpeg, "-nostdin", "-v", "info", "-threads", "2", "-i", str(source),
             "-t", str(MAX_SECONDS), "-an", "-filter_threads", "1", "-vf",
             f"fps={SAMPLE_FPS},scale=-2:144,format=gray,"
             "tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
             "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
        )
    except subprocess.TimeoutExpired:
        return unavailable("Motion analysis exceeded 90 seconds; inspect this file manually.")
    except OSError as exc:
        return unavailable(f"Motion analysis could not read the video: {exc.__class__.__name__}.")
    if result.returncode != 0:
        return unavailable("FFmpeg could not decode the video for motion analysis.")
    values = [float(v) for v in re.findall(r"lavfi\.signalstats\.YAVG=([0-9.eE+-]+)", result.stderr)]
    report = summarize(values)
    report.update(file_sha256=digest.hexdigest(), measured_at=datetime.now(timezone.utc).isoformat())
    return report
