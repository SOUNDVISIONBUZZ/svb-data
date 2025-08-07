#!/usr/bin/env python3
"""
Auto-update events.json for SOUND VISION BUZZ
--------------------------------------------

* Wraps the feed as:
    {
      "generated": "2025-08-06T22:34:18Z",
      "events": [ … ]
    }

* Sources merged today:
    • Ticketmaster  (optional – returns 0 for Santa Barbara now)
    • LiveNotesSB   (custom scraper you just added)

Future sources can be added by dropping `sources/xyz.py` with a
`fetch(**kwargs)` function and wiring it into `fetch_from_sources()`.

The script is idempotent and safe to run locally or in GitHub Actions.
"""

from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from typing import List, Dict

# ───────────────────────────── Config ────────────────────────────────
DATA_PATH = Path(__file__).parent / "events.json"

# Attempt to import optional source modules.
# They each expose a `fetch(**kwargs) -> list[dict]`.
try:
    from sources import ticketmaster  # type: ignore
except ModuleNotFoundError:
    ticketmaster = None  # still expands cleanly

try:
    from sources import lnsb_fetch          # LiveNotesSB
except ModuleNotFoundError:                 # if __init__.py missing
    lnsb_fetch = lambda *_, **__: []        # noqa: E731


# ─────────────────────────── Helpers ────────────────────────────────
def load_events() -> List[Dict]:
    """Return current events (handles wrapped / legacy formats)."""
    if not DATA_PATH.exists():
        return []

    text = DATA_PATH.read_bytes().decode("utf-8", errors="replace")

    # Wrapped form {generated, events:[…]}
    if text.lstrip().startswith("{"):
        try:
            obj = json.loads(text)
            events = obj.get("events", [])
        except Exception:
            events = []
    else:  # Legacy flat array
        events = json.loads(text)

    # Drop any stray {"generated": …} rows inside the list
    return [ev for ev in events if not (ev.keys() == {"generated"})]


def save_feed(events: List[Dict]) -> None:
    feed = {
        "generated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "events": events,
    }
    DATA_PATH.write_text(
        json.dumps(feed, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ Wrote {len(events)} events to {DATA_PATH.name}")


# ─────────────────────────── Sources ────────────────────────────────
def fetch_from_sources() -> List[Dict]:
    """Aggregate events from every enabled source module."""
    events: List[Dict] = []

    # 1 ▸ Ticketmaster (returns [] if module missing or no SB data)
    if ticketmaster:
        try:
            events += ticketmaster.fetch(city="Santa Barbara")
        except Exception as e:
            print("⚠️  Ticketmaster fetch failed:", e)

    # 2 ▸ LiveNotesSB (always present after lnsb_fetch import)
    try:
        events += lnsb_fetch()
    except Exception as e:
        print("⚠️  LiveNotesSB fetch failed:", e)

    return events


def merge_dedupe(existing: List[Dict], new: List[Dict]) -> List[Dict]:
    """Very simple de-dupe by unique 'id'."""
    by_id: Dict[str, Dict] = {ev["id"]: ev for ev in existing if "id" in ev}
    for ev in new:
        by_id[ev["id"]] = ev
    return list(by_id.values())


# ─────────────────────────── Main ───────────────────────────────────
def main() -> None:
    base_events   = load_events()
    fresh_events  = fetch_from_sources()
    combined      = merge_dedupe(base_events, fresh_events)

    # Optional: sort soonest first
    combined.sort(key=lambda ev: ev.get("start", "9999"))

    save_feed(combined)


if __name__ == "__main__":
    main()






