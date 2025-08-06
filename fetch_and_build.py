#!/usr/bin/env python3
"""
Auto-update events.json for SOUND VISION BUZZ
--------------------------------------------
1. Load current events (UTF-8, drop legacy {generated} rows).
2. Pull fresh events from external sources (Ticketmaster first).
3. Merge / de-dupe / tag.
4. Write back in wrapped JSON:
   { "generated": "...Z", "events": [ … ] }
"""

from __future__ import annotations
import json, datetime as dt
from pathlib import Path

# ── external source modules ──────────────────────────────────────────
from sources import ticketmaster   # NEW ▶ pulls Discovery API events

DATA_PATH = Path(__file__).parent / "events.json"

# ─────────────────────────── Helpers ────────────────────────────────
def load_events() -> list[dict]:
    """Return clean list of real events (no stray {generated})."""
    if not DATA_PATH.exists():
        return []
    text = DATA_PATH.read_bytes().decode("utf-8", errors="replace")
    try:                                    # wrapped form
        events = json.loads(text).get("events", [])
    except Exception:                       # maybe flat array
        events = json.loads(text) if text.lstrip().startswith("[") else []
    return [ev for ev in events if not (ev.keys() == {"generated"})]


def save_feed(stamp_iso: str, events: list[dict]) -> None:
    feed = {"generated": stamp_iso, "events": events}
    DATA_PATH.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("events.json written:", DATA_PATH.absolute())


# ─────────────────────────── Source aggregation ─────────────────────
def fetch_from_sources() -> list[dict]:
    """
    Pull fresh events from all external providers.
    Extend the list (or make it dynamic) as needed.
    """
    santa_barbara_cluster = ["Santa Barbara", "Montecito", "93101", "93108"]
    return ticketmaster.fetch(santa_barbara_cluster)
    # + eventbrite.fetch(...)  (add later)


def merge_dedupe(existing: list[dict], new: list[dict]) -> list[dict]:
    """Simple de-dupe by unique 'id'. Override for fuzzy matching later."""
    by_id: dict[str, dict] = {ev["id"]: ev for ev in existing if "id" in ev}
    for ev in new:
        by_id[ev["id"]] = ev
    return list(by_id.values())


# ─────────────────────────── Main entry ─────────────────────────────
def main() -> None:
    base_events  = load_events()
    fresh_events = fetch_from_sources()
    events       = merge_dedupe(base_events, fresh_events)

    stamp = dt.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    save_feed(stamp, events)
    print(f"✓ Feed updated ({len(events)} events) @ {stamp}")


if __name__ == "__main__":
    main()





