# sources/livenotessb.py
"""
Tiny scraper for LiveNotesSB.com – no Selenium, runs in GitHub Action.
Adds public music events for Santa Barbara / Montecito.
"""

from __future__ import annotations
import datetime as dt, re, requests
from bs4 import BeautifulSoup

BASE = "https://livenotessb.com"

def _iso(raw: str, tz="-07:00") -> str:
    # 'Aug 23 2025 8:00 pm' -> '2025-08-23T20:00:00-07:00'
    d = dt.datetime.strptime(raw, "%b %d %Y %I:%M %p")
    return d.isoformat() + tz

def fetch(city_filter: str | None = None) -> list[dict]:
    print("• LiveNotesSB fetch")
    html = requests.get(BASE, timeout=10).text
    soup = BeautifulSoup(html, "html.parser")
    events: list[dict] = []

    for art in soup.select("article.post"):
        try:
            title = art.select_one("h2 a").text.strip()
            raw_dt = art.select_one("time").text.strip()
            start  = _iso(raw_dt)
            end    = _iso(raw_dt).replace("T", "T23:00:00")  # dummy 3 h window
            venue  = art.select_one(".venue").text.strip()
            city   = "Santa Barbara" if "Santa Barbara" in venue else "Montecito"
            if city_filter and city != city_filter:
                continue

            events.append({
                "id": "lnsb-" + re.sub(r"\W+", "-", title.lower())[:30],
                "title": title,
                "category": "Music",
                "genre": None,
                "city": city,
                "zip": "93101",
                "start": start,
                "end": end,
                "venue": venue,
                "address": venue,
                "popularity": 50,
            })
        except Exception:
            continue

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events
