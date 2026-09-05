"""How much a clip actually moves, as a number.

"It looks static" and "it looks animated" are the sort of judgements that
drift between viewings, and the first film in this repository looked static
for a reason nobody could point at until it was measured: every prompt asked
for "slow gentle camera drift" and the model obliged.

This reports the mean absolute difference between consecutive frames. A held
painting with a slow push scores low everywhere; real character animation
scores high and, more tellingly, scores *unevenly* - things start and stop.
So the spread matters as much as the average.

Usage:
    python scripts/measure_motion.py FILE [FILE ...]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def frame_differences(path: str, height: int = 144) -> list[float]:
    """Mean absolute luma change from each frame to the next."""
    result = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path, "-filter_complex",
         f"[0:v]scale=-1:{height},format=gray,tblend=all_mode=difference,"
         "signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return [
        float(line.split("=")[-1])
        for line in result.stderr.splitlines()
        if "YAVG" in line
    ]


def summarise(path: str) -> dict[str, float | str]:
    values = frame_differences(path)
    if not values:
        return {"file": Path(path).name, "error": "no frames measured"}
    values.sort()
    middle = len(values) // 2
    median = (
        values[middle] if len(values) % 2
        else (values[middle - 1] + values[middle]) / 2
    )
    mean = sum(values) / len(values)
    # The top decile is where real action lives: a clip that never exceeds its
    # own average is drifting, not animating.
    peak = values[int(len(values) * 0.9)]
    return {
        "file": Path(path).name,
        "frames": len(values) + 1,
        "mean": round(mean, 2),
        "median": round(median, 2),
        "peak_decile": round(peak, 2),
        "still_share": round(sum(1 for v in values if v < 1.0) / len(values), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    rows = [summarise(path) for path in args.files]
    width = max(len(str(row["file"])) for row in rows)
    print(f"{'file':{width}}  {'mean':>6} {'median':>7} {'peak10%':>8} {'still':>6}")
    for row in rows:
        if "error" in row:
            print(f"{row['file']:{width}}  {row['error']}")
            continue
        print(f"{row['file']:{width}}  {row['mean']:6.2f} {row['median']:7.2f} "
              f"{row['peak_decile']:8.2f} {row['still_share']:6.1%}")
    print()
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
