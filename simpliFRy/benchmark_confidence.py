"""
Real-time confidence benchmark: watches the live /api/frResults stream for a chosen name and
reports distance-score statistics over a fixed window. Run this while standing in front of the
camera, toggle a setting on the Settings page, and run it again to compare the two reports.

Usage:
    python benchmark_confidence.py --name "YOUR NAME" [--duration 10] [--host http://localhost:1333]

Requires the app to already be running with the camera stream started and your face enrolled.
"""

import argparse
import json
import time

import requests


def run_benchmark(name: str, duration: float, host: str):
    name = name.strip().upper()

    settings = requests.get(f"{host}/api/get_settings", timeout=5).json()
    threshold = settings.get("threshold", 0.5)

    print(f"Watching for '{name}' for {duration:.0f}s (threshold={threshold})...")
    print("Toggles active:", {
        k: v for k, v in settings.items()
        if k.startswith("use_")
    })

    scores = []
    total_frames_with_person = 0
    start = time.monotonic()

    resp = requests.get(f"{host}/api/frResults", stream=True, timeout=duration + 10)
    try:
        for line in resp.iter_lines():
            if time.monotonic() - start > duration:
                break
            if not line:
                continue
            try:
                detections = json.loads(line).get("data", [])
            except json.JSONDecodeError:
                continue

            for det in detections:
                if det.get("label", "").strip().upper() == name:
                    scores.append(det["score"])
                    total_frames_with_person += 1
                    break
    finally:
        resp.close()

    print()
    if not scores:
        print(f"No detections matching '{name}' were seen in {duration:.0f}s.")
        print("Check: is the stream running, is this name enrolled exactly as spelled, "
              "and were you in frame?")
        return

    below_threshold = sum(1 for s in scores if s < threshold)
    pct_identified = 100 * below_threshold / len(scores)

    print(f"=== Results for '{name}' ===")
    print(f"Frames captured:      {len(scores)}")
    print(f"Mean distance:        {sum(scores)/len(scores):.4f}")
    print(f"Min distance (best):  {min(scores):.4f}")
    print(f"Max distance (worst): {max(scores):.4f}")
    print(f"% frames identified (distance < {threshold}): {pct_identified:.1f}%")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time FR confidence benchmark")
    parser.add_argument("--name", required=True, help="Enrolled name to watch for (as in the namelist JSON)")
    parser.add_argument("--duration", type=float, default=10, help="Seconds to watch the stream (default: 10)")
    parser.add_argument("--host", default="http://localhost:1333", help="Base URL of the running app")
    args = parser.parse_args()

    run_benchmark(args.name, args.duration, args.host)
