# sources/lnsb_fetch.py
"""
Scraper for the LiveNotesSB front page.
• No Selenium – runs quickly inside GitHub Actions
• Produces dicts compatible with events.json builder
"""

from __future__ import annotations
import datetime as dt, re, requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"

# ── helpers ────────────────────────────────────────────────────────────────────
def _iso(d: dt.datetime, tz="-07:00") -> str:
    """Return ISO-8601 with fixed TZ offset (-07:00 = Pacific)."""
    return d.isoformat() + tz

def _make_id(day: dt.date, venue: str, artist: str) -> str:
    """
    Deterministic ID: lnsb-YYYYMMDD-venue-artist   (all lower-case, dashes only)
    """
    stem = f"{day:%Y%m%d}-{venue[:12]}-{artist[:12]}"
    return "lnsb-" + re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")

HDR_RE = re.compile(r"^[A-Z][a-z]+day – \w+ \d", re.I)   # e.g. “TUESDAY – August 5”

# ── main ───────────────────────────────────────────────────────────────────────
def lnsb_fetch(city_filter: str | None = None) -> list[dict]:
    """
    Return a list of event dicts scraped from LiveNotesSB.
    Optionally pass `city_filter="Goleta"` to keep only matching rows.
    """
    print("• LiveNotesSB fetch")
    html = requests.get(
        SITE, headers={"User-Agent": "Mozilla/5.0"}, timeout=20
    ).text
    soup = BeautifulSoup(html, "html.parser")

    events: list[dict] = []

    # Each daily section is an <h4> heading followed by several <p>s
    for h4 in soup.find_all("h4"):
        hdr = h4.get_text(" ", strip=True).replace("\u00a0", " ")
        if not HDR_RE.match(hdr):
            continue

        # Parse date from heading, assume current year if not present
        _, _, when = hdr.partition("–")                   # “TUESDAY – August 5”
        day = dt.datetime.strptime(when.strip() + " 2025", "%B %d %Y").date()

        # Walk subsequent <p> siblings until the next heading
        ptr = h4.find_next_sibling()
        while ptr and ptr.name == "p":
            txt = ptr.get_text(" ", strip=True)

            # Expected pattern:  *Venue – Artist – 5-8 pm   (dashes or asterisks vary)
            m = re.match(
                r".*?[*–]\s*(.+?)\s*–\s*(.+?)\s*–\s*(\d+)(?::(\d+))?\s*([ap]m)",
                txt,
                re.I,
            )
            if m:
                venue, artist, hr, minute, ampm = m.groups()
                minute = minute or "00"
                hr = int(hr) % 12 + (12 if ampm.lower() == "pm" else 0)
                start_dt = dt.datetime.combine(day, dt.time(hr, int(minute)))
                end_dt = start_dt + dt.timedelta(hours=2)

                # crude city guess: text before “– …” in venue line
                city = "Santa Barbara"
                if "–" in venue:
                    city = venue.split("–")[0].strip()

                if city_filter and city_filter.lower() not in city.lower():
                    ptr = ptr.find_next_sibling()
                    continue

                events.append(
                    {
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
                    }
                )
            ptr = ptr.find_next_sibling()

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events


