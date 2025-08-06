#!/usr/bin/env python3
"""
Auto-update events.json for SOUND VISION BUZZ.

Writes a wrapped object:
{
  "generated": "2025-08-06T06:23:15Z",
  "events": [ {id: …}, … ]
}
"""

import json
import datetime as dt
from pathlib import Path

DATA_PATH = Path(__file__).parent / "events.json"


# ─────────────────────────── Helpers ────────────────────────────────
def load_events() -> list[dict]:
    """Load existing events.json; tolerate bad bytes."""
    if not DATA_PATH.exists():
        return []
    text = DATA_PATH.read_bytes().decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
        return data.get("events", [])      # when file already wrapped
    except Exception:                      # or plain array on first run
        return json.loads(text) if text.strip().startswith("[") else []


def save_feed(generated: str, events: list[dict]) -> None:
    feed = {
        "generated": generated,
        "events": events,
    }
    DATA_PATH.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─────────────────────────── Main entry ─────────────────────────────
def main() -> None:
    events = load_events()

    # TODO: fetch new events, merge, de-dupe …
    # events = merge(events, fetch_ticketmaster(), fetch_eventbrite())

    ts = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    save_feed(ts, events)
    print("events.json wrapped and timestamped:", ts)


if __name__ == "__main__":
    main()



