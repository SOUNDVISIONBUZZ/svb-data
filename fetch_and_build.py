# fetch_and_build.py
import json
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
    events = lnsb_fetch()
    print(f"Found {len(events)} LiveNotesSB events")

    if not events:
        msg = "No events found."
        if allow_empty:
            print("WARNING:", msg)
            OUT.write_text("[]", encoding="utf-8")
            return 0
        else:
            print("ERROR:", msg)
            return 2

    def _key(ev):
        try:
            return datetime.fromisoformat(ev["start"].replace("Z","+00:00"))
        except Exception:
            return datetime.max
    events.sort(key=_key)

    OUT.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Built events.json with {len(events)} events")

    if debug:
        for i, ev in enumerate(events[:5], start=1):
            print(f"{i}. {ev.get('title')}")
            loc = ev.get('address') or ev.get('venue_name') or ev.get('city', '')
            print(f"   📍 {loc}")
            print(f"   🕐 {ev.get('start')}")

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
    ap.add_argument("--allow-empty", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    sys.exit(build(allow_empty=args.allow_empty, debug=args.debug))

if __name__ == "__main__":
    main()
