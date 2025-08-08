# fetch_and_build.py
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from sources.lnsb_fetch import lnsb_fetch

OUT = Path("events.json")

# Where to mirror the file for your iOS project(s). Change if paths differ.
IOS_COPY_1 = Path("/Users/marlyndaggett/Desktop/sound_vision_buzz_app/events.json")
IOS_COPY_2 = Path("/Users/marlyndaggett/Desktop/SOUND VISION BUZZ/events.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--allow-empty", action="store_true")
    args = ap.parse_args()

    if args.debug:
        print("Building Santa Barbara events data...")
        print("Fetching LiveNotesSB events...")

    events = lnsb_fetch()

    if not events and not args.allow_empty:
        print("ERROR: No events found. Refusing to write sample/empty output.")
        return 2

    OUT.write_text(json.dumps(events, indent=2), encoding="utf-8")

    if args.debug:
        print(f"✅ Built events.json with {len(events)} events")
        for i, e in enumerate(events[:3], 1):
            venue = e.get("venue_name") or e.get("venueName") or "?"
            print(f"{i}. {e['title']}\n   📍 {venue}\n   🕐 {e['start']}")

    # Copy to iOS app locations (best-effort)
    for dest in (IOS_COPY_1, IOS_COPY_2):
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT, dest)
            if args.debug:
                print(f"✅ Copied to {dest}")
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
