#!/usr/bin/env python3
"""
Auto-update events.json for SOUND VISION BUZZ

Output format
-------------
{
  "generated": "2025-08-06T21:04:08Z",
  "events": [ { …real events… } ]
}

Pipeline
--------
1. Load existing events (tolerant UTF-8, drop legacy {generated} rows).
2. TODO: fetch fresh events from external sources.
3. Merge / de-dupe / classify / affiliate-tag.
4. Write back in clean UTF-8.
"""

from __future__ import annotations
import json
import datetime as dt
from pathlib import Path

DATA_PATH = Path(__file__).parent / "events.json"


# ─────────────────────────── Helpers ────────────────────────────────
def load_events() -> list[dict]:
    """
    Return a clean list of real events.
    Handles both the new wrapped format and the old flat array,
    and drops stray `{ "generated": ... }` rows inside the list.
    """
    if not DATA_PATH.exists():
        return []

    text = DATA_PATH.read_bytes().decode("utf-8", errors="replace")

    # Try wrapped form first
    try:
        data = json.loads(text)
        events = data.get("events", [])       # when wrapped
    except Exception:
        # Fallback: maybe the whole file is a flat array
        events = json.loads(text) if text.lstrip().startswith("[") else []

    # Filter out any legacy metadata-only objects
    return [ev for ev in events if not (ev.keys() == {"generated"})]


def save_feed(generated_iso: str, events: list[dict]) -> None:
    feed = {
        "generated": generated_iso,
        "events": events,
    }
    DATA_PATH.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("events.json written:", DATA_PATH.absolute())


# ─────────────────────────── TODO: External sources stubs ────────────
def fetch_from_sources() -> list[dict]:
    """
    Placeholder aggregator.
    Add real calls to Ticketmaster, Eventbrite, etc. here.
    Must return a list of event dicts in the canonical schema.
    """
    # Example: return ticketmaster.fetch([...]) + eventbrite.fetch([...])
    return []


def merge_dedupe(existing: list[dict], new: list[dict]) -> list[dict]:
    """
    Very simple de-dupe by unique 'id'. Replace with fuzzy
    matching if needed.
    """
    by_id: dict[str, dict] = {ev["id"]: ev for ev in existing if "id" in ev}
    for ev in new:
        by_id[ev["id"]] = ev
    return list(by_id.values())


# ─────────────────────────── Main entry ─────────────────────────────
def main() -> None:
    base_events = load_events()
    fresh_events = fetch_from_sources()
    events = merge_dedupe(base_events, fresh_events)

    timestamp = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    save_feed(timestamp, events)
    print(f"✓ Wrapped feed updated ({len(events)} events) @ {timestamp}")


if __name__ == "__main__":
    main()




