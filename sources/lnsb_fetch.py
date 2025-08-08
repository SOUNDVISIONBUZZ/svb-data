#!/usr/bin/env python3
"""
Enhanced build script for Santa Barbara events data.
Combines LiveNotesSB events with sample events and handles formatting.
"""

import json
import datetime as dt
from pathlib import Path
from typing import Dict, List, Any

# Import the scraper
try:
    from sources.lnsb_fetch import lnsb_fetch
except ImportError:
    print("Warning: Could not import lnsb_fetch. Using sample events only.")
    def lnsb_fetch():
        return []

def load_sample_events() -> List[Dict[str, Any]]:
    """Load sample events as fallback."""
    return [
        {
            "id": "sb001",
            "title": "Summer Nights Concert: Spencer the Gardener",
            "category": "Music",
            "genre": "Rock",
            "city": "Santa Barbara",
            "zip": "93101",
            "start": "2025-08-01T18:00:00-07:00",
            "end": "2025-08-01T20:00:00-07:00",
            "venue": "SB County Courthouse Sunken Gardens",
            "address": "1100 Anacapa St, Santa Barbara, CA 93101",
            "popularity": 98
        },
        {
            "id": "sb002",
            "title": "Downtown Friday Night Concert",
            "category": "Music",
            "genre": "Folk",
            "city": "Santa Barbara",
            "zip": "93101",
            "start": "2025-08-08T19:00:00-07:00",
            "end": "2025-08-08T21:00:00-07:00",
            "venue": "Paseo Nuevo",
            "address": "651 Paseo Nuevo, Santa Barbara, CA 93101",
            "popularity": 85
        },
        {
            "id": "sb003",
            "title": "Jazz at the Bowl",
            "category": "Music",
            "genre": "Jazz",
            "city": "Santa Barbara",
            "zip": "93103",
            "start": "2025-08-15T20:00:00-07:00",
            "end": "2025-08-15T22:30:00-07:00",
            "venue": "Santa Barbara Bowl",
            "address": "1122 N Milpas St, Santa Barbara, CA 93103",
            "popularity": 92
        }
    ]

def validate_event(event: Dict[str, Any]) -> bool:
    """Validate that an event has all required fields."""
    required_fields = ["id", "title", "category", "genre", "city", "zip", 
                      "start", "end", "venue", "address", "popularity"]
    
    for field in required_fields:
        if field not in event:
            print(f"Warning: Event {event.get('id', 'unknown')} missing field: {field}")
            return False
    
    return True

def sort_events_by_date(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort events by start date."""
    try:
        return sorted(events, key=lambda x: dt.datetime.fromisoformat(x['start'].replace('Z', '+00:00')))
    except Exception as e:
        print(f"Warning: Could not sort events by date: {e}")
        return events

def main():
    """Main build function."""
    print("Building Santa Barbara events data...")
    
    # Fetch LiveNotesSB events
    print("Fetching LiveNotesSB events...")
    lnsb_events = lnsb_fetch()
    print(f"Found {len(lnsb_events)} LiveNotesSB events")
    
    # Load sample events as backup
    sample_events = load_sample_events()
    print(f"Loaded {len(sample_events)} sample events")
    
    # Combine all events
    all_events = []
    
    # Add valid LiveNotesSB events
    for event in lnsb_events:
        if validate_event(event):
            all_events.append(event)
    
    # Add sample events
    for event in sample_events:
        if validate_event(event):
            all_events.append(event)
    
    # Sort events by date
    all_events = sort_events_by_date(all_events)
    
    # Create final data structure
    events_data = {
        "generated": dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_events": len(all_events),
        "sources": {
            "livenotessb": len(lnsb_events),
            "samples": len(sample_events)
        },
        "events": all_events
    }
    
    # Write to events.json
    output_path = Path("events.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(events_data, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Successfully built events.json with {len(all_events)} events")
    print(f"   - LiveNotesSB events: {len(lnsb_events)}")
    print(f"   - Sample events: {len(sample_events)}")
    
    # Show first few events for verification
    print("\n📋 First 3 events:")
    for i, event in enumerate(all_events[:3], 1):
        print(f"{i}. {event['title']} at {event['venue']}")
        print(f"   📍 {event['address']}")
        print(f"   🕐 {event['start']}")
    
    # Copy to iOS app locations
    ios_paths = [
        Path.home() / "Desktop/sound_vision_buzz_app/events.json",
        Path.home() / "Desktop/SOUND VISION BUZZ/events.json"
    ]
    
    for ios_path in ios_paths:
        if ios_path.parent.exists():
            try:
                import shutil
                shutil.copy2(output_path, ios_path)
                print(f"✅ Copied to {ios_path}")
            except Exception as e:
                print(f"❌ Failed to copy to {ios_path}: {e}")
        else:
            print(f"⚠️  iOS app directory not found: {ios_path.parent}")

if __name__ == "__main__":
    main()
