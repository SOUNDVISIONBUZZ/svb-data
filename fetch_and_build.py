# fetch_and_build.py
# Build events.json with real LiveNotesSB data. No sample injection.

import json
import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

from sources.lnsb_fetch import lnsb_fetch

ROOT = Path(__file__).parent.resolve()
OUT = ROOT / "events.json"

IOS_PATHS = [
    Path.home() / "Desktop" / "sound_vision_buzz_app" / "events.json",
    Path.home() / "Desktop" / "SOUND VISION BUZZ" / "events.json",
]

def build(allow_empty: bool = False, debug: bool = False) -> int:
    print("Building Santa Barbara events data...")

    print("Fetching LiveNotesSB events...")
    lnsb = lnsb_fetch()
    print(f"Found {len(lnsb)} LiveNotesSB events")

    all_events = lnsb

    if not all_events:
        msg = "No events found. Refusing to write sample/empty output."
        if allow_empty:
            print("WARNING:", msg)
        else:
            print("ERROR:", msg)
            return 2

    # Sort by start
    def _key(ev):
        try:
            return datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
        except Exception:
            return datetime.max
    all_events.sort(key=_key)

    # Write file
    with OUT.open("w", encoding="utf-8") as f:
        json.dump(all_events, f, ensure_ascii=False, indent=2)

    print(f"✅ Successfully built events.json with {len(all_events)} events")
    if debug:
        for i, ev in enumerate(all_events[:3], start=1):
            print(f"{i}. {ev.get('title')}")
            print(f"   📍 {ev.get('address','') or ev.get('venue_name','') or ev.get('city','')}")
            print(f"   🕐 {ev.get('start')}")

    # Try to copy to iOS working dirs (if present)
    for p in IOS_PATHS:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(OUT.read_text(encoding="utf-8"), encoding="utf-8")
            print(f"✅ Copied to {p}")
        except Exception as e:
            print(f"⚠️  Could not copy to {p}: {e}")

    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-empty", action="store_true", help="Write even if no events found")
    ap.add_argument("--debug", action="store_true", help="Print first few events")
    args = ap.parse_args()

    rc = build(allow_empty=args.allow_empty, debug=args.debug)
    sys.exit(rc)

if __name__ == "__main__":
    main()
