#!/usr/bin/env python3
# fetch_and_build.py — builds events.json using the bullet-only LNSB scraper.
# Writes debug files to tmp_lnsb/ and optionally copies events.json to your iOS folders.

from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path
from typing import List, Dict
from sources.lnsb_fetch import lnsb_fetch

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "events.json"

IOS_COPY_PATHS = [
    Path("/Users/marlyndaggett/Desktop/sound_vision_buzz_app/events.json"),
    Path("/Users/marlyndaggett/Desktop/SOUND VISION BUZZ/events.json"),
]

def build(allow_empty: bool, debug: bool) -> int:
    print("Building Santa Barbara events data...")
    print("Fetching LiveNotesSB events...")
    events: List[Dict] = lnsb_fetch() or []

    if not events and not allow_empty:
        print("ERROR: No events found. Refusing to write empty output.")
        return 2

    with OUT.open("w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)

    print(f"✅ Built events.json with {len(events)} events")

    if debug:
        for i, e in enumerate(events[:3], 1):
            venue = e.get("venue_name") or e.get("venue") or "?"
            print(f"{i}. {e['title']}\n   📍 {venue}\n   🕐 {e['start']}")

    for dest in IOS_COPY_PATHS:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT, dest)
            print(f"✅ Copied to {dest}")
        except Exception as e:
            print(f"⚠️  Could not copy to {dest}: {e}")

    return 0

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Build events.json")
    p.add_argument("--allow-empty", action="store_true", help="Write file even if no events found")
    p.add_argument("--debug", action="store_true", help="Verbose output")
    args = p.parse_args(argv)

    return build(args.allow_empty, args.debug)

if __name__ == "__main__":
    sys.exit(main())
