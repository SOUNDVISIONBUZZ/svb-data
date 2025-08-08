# fetch_and_build.py
import argparse
import json
import shutil
from pathlib import Path
from sources.lnsb_fetch import lnsb_fetch

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "events.json"
IOS_COPY_1 = Path.home() / "Desktop" / "sound_vision_buzz_app" / "events.json"
IOS_COPY_2 = Path.home() / "Desktop" / "SOUND VISION BUZZ" / "events.json"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-empty", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    if args.debug:
        print("Building Santa Barbara events data...")
        print("Fetching LiveNotesSB events...")

    try:
        events = lnsb_fetch()
    except Exception as ex:
        if args.debug:
            print("Error fetching LNSB:", ex)
        events = []

    if not events and not args.allow_empty:
        print("ERROR: No events found. Refusing to write sample/empty output.")
        return 2

    OUT.write_text(json.dumps(events, indent=2), encoding="utf-8")

    if args.debug:
        print(f"✅ Built events.json with {len(events)} events")
        for i, e in enumerate(events[:3], 1):
            venue = e.get("venue_name") or e.get("venueName") or "?"
            print(f"{i}. {e['title']}\n   📍 {venue}\n   🕐 {e['start']}")

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
