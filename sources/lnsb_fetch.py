"""Fetch events from LiveNotesSB HTML feed."""
from __future__ import annotations
import requests, datetime as dt
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com/"   # adjust if needed

def lnsb_fetch() -> list[dict]:
    html = requests.get(SITE, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    events: list[dict] = []
    for card in soup.select("div.post"):            # TODO: right selector
        try:
            title = card.select_one("h2").text.strip()
            date  = card.select_one("time").text.strip()
            dt_obj = dt.datetime.strptime(date, "%B %d, %Y")
            events.append({
                "id":  f"lnsb-{dt_obj:%Y%m%d}-{len(events):02}",
                "title": title,
                "category": "Music & Art",
                "genre": None,
                "city": "Santa Barbara",
                "zip": "93101",
                "start": dt_obj.isoformat(),
                "end":   (dt_obj + dt.timedelta(hours=2)).isoformat(),
                "venue": "See description",
                "address": "Santa Barbara, CA",
                "popularity": 50,
            })
        except Exception:
            continue
    return events
