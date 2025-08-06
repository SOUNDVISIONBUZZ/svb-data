"""
Ticketmaster Discovery API → SOUND VISION BUZZ event schema
-----------------------------------------------------------
fetch(["Santa Barbara", "Montecito", "93101"])  →  List[dict]
"""

from __future__ import annotations
import os, requests, datetime as dt
from dateutil import parser as date_parse

API_KEY = os.getenv("TM_API_KEY")
BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
PER_PAGE = 200       # max allowed

def _tm_params(city_or_zip: str, page: int) -> dict:
    return {
        "apikey":      API_KEY,
        "size":        PER_PAGE,
        "page":        page,
        "sort":        "date,asc",
        "locale":      "*",
        "city":        city_or_zip if city_or_zip.isalpha() else "",
        "postalCode":  city_or_zip if city_or_zip.isdigit() else "",
        "classificationName": "music,arts&theatre",
        "countryCode": "US",
    }

def _map(ev: dict) -> dict | None:
    try:
        venue = ev["_embedded"]["venues"][0]
        start = date_parse.isoparse(ev["dates"]["start"]["dateTime"])
        end   = start + dt.timedelta(hours=3)          # rough guess
        return {
            "id":        ev["id"],
            "title":     ev["name"],
            "category":  "Music" if "Music" in ev["classifications"][0]["segment"]["name"] else "Art",
            "genre":     ev["classifications"][0]["genre"]["name"],
            "city":      venue["city"]["name"],
            "zip":       venue.get("postalCode", ""),
            "start":     start.isoformat(),
            "end":       end.isoformat(),
            "venue":     venue["name"],
            "address":   f'{venue.get("address", {}).get("line1", "")}, {venue["city"]["name"]}, {venue.get("state", {}).get("stateCode", "")}',
            "popularity": int(float(ev.get("popularity", 0)) * 100),
            "url":       ev["url"],
        }
    except Exception as e:
        print("ticketmaster: could not map event:", e)
        return None

def fetch(cities_or_zips: list[str]) -> list[dict]:
    if not API_KEY:
        print("ticketmaster: TM_API_KEY missing; skipping")
        return []

    out: list[dict] = []
    for loc in cities_or_zips:
        page = 0
        while True:
            r = requests.get(BASE_URL, params=_tm_params(loc, page), timeout=30)
            if r.status_code != 200:
                print("ticketmaster HTTP", r.status_code, r.text[:80])
                break
            data = r.json()
            events = data.get("_embedded", {}).get("events", [])
            out.extend(filter(None, map(_map, events)))
            if page >= data.get("page", {}).get("totalPages", 0) - 1:
                break
            page += 1
    return out
