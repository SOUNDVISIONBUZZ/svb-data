#!/usr/bin/env python3
"""Stub that will soon fetch real events, then overwrite events.json."""
import json, datetime, pathlib

DATA_PATH = pathlib.Path(__file__).parent / "events.json"

with DATA_PATH.open() as f:
    data = json.load(f)

# prepend a timestamp object so we can see updates happening
data.insert(0, {"generated": datetime.datetime.utcnow().isoformat()})

with DATA_PATH.open("w") as f:
    json.dump(data, f, indent=2)

print("events.json updated at", datetime.datetime.utcnow())
