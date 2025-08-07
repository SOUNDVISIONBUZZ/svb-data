# ─── LiveNotesSB scraper — sources/livenotessb.py ──────────────────────────
"""
Scraper for https://livenotessb.com   (Santa Barbara live-music listings).

✓ No Selenium — pure requests + BeautifulSoup, OK for GitHub Actions runner
✓ Emits events in the same schema used by fetch_and_build.py
"""

from __future__ import annotations
import datetime as dt, re, requests
from bs4 import BeautifulSoup

BASE      = "https://livenotessb.com"
HDR_RE    = re.compile(r"^(MONDAY|TUESDAY|WEDNESDAY|THURSDAY|FRIDAY|SATURDAY|SUNDAY)\s+–", re.I)
UTC_OFF   = "-07:00"          # PDT; tweak if site changes to PST

# ── helpers ────────────────────────────────────────────────────────────────
def _iso(raw_date: str, raw_time: str) -> str:
    """
    >>> _iso("Aug 23 2025", "8 pm")
    '2025-08-23T20:00:00-07:00'
    """
    stamp = f"{raw_date} {raw_time.upper()}"
    d = dt.datetime.strptime(stamp, "%b %d %Y %I %p")
    return d.isoformat() + UTC_OFF

def _download(timeout: int = 25) -> str:
    """Return raw HTML from LiveNotesSB front page."""
    return requests.get(BASE, headers={"User-Agent": "Mozilla/5.0"},
                        timeout=timeout).text

# ── main entry-point ───────────────────────────────────────────────────────
def fetch(city_filter: str | None = None) -> list[dict]:
    """
    Return a list of event-dicts.  Pass `city_filter="Goleta"` to keep only that city.
    """
    print("• LiveNotesSB fetch")
    html  = _download()
    soup  = BeautifulSoup(html, "html.parser")
    posts = soup.select("div.page-content > *")   # mix of <h4> and <p>

    events: list[dict] = []
    current_date = None
    for el in posts:
        if el.name == "h4":                        # date header
            hdr = el.get_text(" ", strip=True).replace("\xa0", " ")
            if HDR_RE.match(hdr):
                # "TUESDAY – August 5"  → "August 5"
                current_date = " ".join(hdr.split("–")[1:]).strip()
        elif current_date and el.name == "p" and "–" in el.text:
            try:
                # Example paragraph:
                #   “*Soho – An Evening with Henry Kapono (island rock) – 8 pm ($25)”
                parts = [t.strip(" *–") for t in el.stripped_strings]
                venue_part, detail_part = parts[0], " ".join(parts[1:])
                venue, _ = venue_part.split(" ", 1) if " " in venue_part else (venue_part, "")
                title, time_part = detail_part.rsplit(" – ", 1)
                start = _iso(f"{current_date} {dt.datetime.now().year}", time_part)
                evt_id = f"lnsb-{hash(title+start) & 0xffffffff:x}"

                event = {
                    "id":       evt_id,
                    "title":    title,
                    "category": "Music",
                    "genre":    "",           # unknown
                    "city":     "Santa Barbara",
                    "zip":      "",
                    "start":    start,
                    "end":      "",           # unknown
                    "venue":    venue,
                    "address":  "",
                    "popularity": 70
                }
                if (not city_filter) or (city_filter.lower() in event["city"].lower()):
                    events.append(event)
            except Exception:
                continue        # skip malformed paragraph

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events
# ───────────────────────────────────────────────────────────────────────────

