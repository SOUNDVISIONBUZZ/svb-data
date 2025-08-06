#!/usr/bin/env python3
"""
Auto-update events.json for SOUND VISION BUZZ.

1. Load the existing events.json (tolerant UTF-8).
2. TODO: fetch new events from APIs / feeds.
3. Merge / de-dupe and write back in clean UTF-8.
"""

import json
import datetime as dt
from pathlib import Path

DATA_PATH = Path(__file__).parent / "events.json"


# ─────────────────────────── Helpers ────────────────────────────────
def load_events() -> list[dict]:
    """Load events.json, forgiving any stray bytes."""
    raw = DATA_PATH.read_bytes()                 # read as bytes
    text = raw.decode("utf-8", errors="replace") # replace bad bytes with �
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"JSON decode failed: {e}") from None


def save_events(events: list[dict]) -> None:
    """Pretty-print JSON in strict UTF-8."""
    DATA_PATH.write_text(
        json.dumps(events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─────────────────────────── Main entry ─────────────────────────────
def main() -> None:
    events = load_events()

    # TODO: replace with real fetch / merge logic
    # new_events = fetch_ticketmaster(...) + fetch_eventbrite(...)
    # events = merge_dedupe(events, new_events)

    # prepend a generation timestamp so we know the workflow ran
    events.insert(
        0,
        {"generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"},
    )

    save_events(events)
    print("events.json updated with timestamp at top")


if __name__ == "__main__":
    main()

