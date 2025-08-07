# sources/lnsb_fetch.py
"""
Scraper for LiveNotesSB front page.
No Selenium; suitable for GitHub Actions.
"""

from __future__ import annotations
import datetime as dt, re, requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"

def _iso(d: dt.datetime, tz="-07:00") -> str:
    return d.isoformat() + tz

def _make_id(day: dt.date, venue: str, artist: str) -> str:
    stem = f"{day:%Y%m%d}-{venue[:10]}-{artist[:10]}"
    return "lnsb-" + re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")

HDR_RE = re.compile(r"^[A-Z][a-z]+day\s+–\s+\w+\s+\d{1,2}", re.I)  # e.g. "TUESDAY – August 5"

def lnsb_fetch(city_filter: str | None = None) -> list[dict]:
    print("• LiveNotesSB fetch")
    html = requests.get(SITE, headers={"User-Agent": "Mozilla/5.0"}, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    events: list[dict] = []
    this_year = dt.date.today().year

    for h4 in soup.find_all("h4"):
        hdr = h4.get_text(" ", strip=True).replace("\xa0", " ")
        if not HDR_RE.search(hdr):
            continue

        # hdr like "TUESDAY – August 5"
        _, _, when = hdr.partition("–")
        when = when.strip()
        try:
            day = dt.datetime.strptime(f"{when} {this_year}", "%B %d %Y").date()
        except ValueError:
            continue

        ptr = h4.find_next_sibling()
        while ptr and ptr.name == "p":
            txt = ptr.get_text(" ", strip=True)

            # Capture: venue — artist — time (supports 5-8 pm, 7 pm, 8 pm-12 am, etc.)
            m = re.search(
                r"^[\*\-]?\s*([^–-]+?)\s*[-–]\s*([^–-]+?)\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)"
                r"(?:\s*[-–]\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m))?",
                txt, re.I
            )
            if not m:
                ptr = ptr.find_next_sibling()
                continue

            venue, artist, h1, m1, ap1, h2, m2, ap2 = m.groups()
            venue = venue.strip()
            artist = artist.strip()

            m1 = m1 or "00"
            h1_i = int(h1) % 12 + (12 if ap1 and ap1.lower() == "pm" else 0)
            start_dt = dt.datetime.combine(day, dt.time(h1_i, int(m1)))

            end_dt = start_dt + dt.timedelta(hours=2)
            if h2 and ap2:
                m2 = m2 or "00"
                h2_i = int(h2) % 12 + (12 if ap2.lower() == "pm" else 0)
                end_dt = dt.datetime.combine(day, dt.time(h2_i, int(m2)))

            city = "Santa Barbara"
            if city_filter and city_filter.lower() not in city.lower():
                ptr = ptr.find_next_sibling()
                continue

            events.append({
                "id": _make_id(day, venue, artist),
                "title": f"{venue}: {artist}",
                "category": "Music",
                "genre": "",
                "city": city,
                "zip": "",
                "start": _iso(start_dt),
                "end": _iso(end_dt),
                "venue": venue,
                "address": "",
                "popularity": 50,
            })

            ptr = ptr.find_next_sibling()

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events
