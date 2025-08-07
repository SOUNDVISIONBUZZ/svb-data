# sources/livenotessb.py
"""
Light-weight scraper for https://livenotessb.com/

• Looks at every <h4> “DAY – Month DD” header
• Reads the <p> blocks that follow until the next header/hr
• Splits each <p> on the first two dashes (-, – or —)
"""

from __future__ import annotations
import datetime as dt, re, unicodedata, html
from bs4 import BeautifulSoup
import requests

URL   = "https://livenotessb.com/"
UA    = {"User-Agent": "Mozilla/5.0"}
TZ    = dt.timezone(dt.timedelta(hours=-7))          # PDT
DASH  = r"[-–—\-]"                                  # all dash chars

# ───────────────────────── helpers ─────────────────────────
MONTHS = {m.lower(): i for i, m in enumerate(
    ("January February March April May June July August September October November December").split(), 1)
}

def slug(txt: str, limit: int = 32) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")
    return (txt[:limit].rsplit("-", 1)[0] or txt) if len(txt) > limit else txt

def parse_date(month: str, day: int) -> dt.date:
    today = dt.date.today()
    for year in (today.year, today.year + 1):
        try:
            d = dt.date(year, MONTHS[month.lower()], day)
        except ValueError:
            continue
        if d >= today - dt.timedelta(days=2):
            return d
    raise ValueError

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)
HDR_RE  = re.compile(rf"\b([A-Za-z]+)\s*{DASH}\s*([A-Za-z]+)\s+(\d{{1,2}})", re.I)

def fetch() -> list[dict]:
    soup = BeautifulSoup(requests.get(URL, headers=UA, timeout=20).text, "html.parser")
    events: list[dict] = []

    for h4 in soup.find_all("h4"):
        hdr = h4.get_text(" ", strip=True).replace("\xa0", " ")
        m = HDR_RE.search(hdr)
        if not m:
            continue
        month, day = m.group(2), int(m.group(3))
        ev_date = parse_date(month, day)

        for p in h4.find_next_siblings():
            if p.name in ("h4", "hr"):
                break
            if p.name != "p":
                continue

            txt = html.unescape(p.get_text(" ", strip=True).replace("\xa0", " "))
            parts = re.split(rf"\s*{DASH}\s*", txt, maxsplit=2)
            if len(parts) < 3:
                continue

            venue, artist, rest = map(str.strip, parts[:3])

            genre = None
            g = re.search(r"\(([^)]+)\)", artist)
            if g:
                genre = g.group(1).strip()
                artist = artist[:g.start()].strip()

            t = TIME_RE.search(rest)
            if not t:
                continue
            hr = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "pm" else 0)
            mn = int(t.group(2) or 0)
            start = dt.datetime.combine(ev_date, dt.time(hr, mn), TZ)
            end   = start + dt.timedelta(hours=2)

            events.append({
                "id"      : f"lnsb-{start:%Y%m%d}-{slug(artist or venue)}",
                "title"   : artist or venue,
                "category": "Music",
                "genre"   : genre,
                "city"    : "Santa Barbara",
                "zip"     : "",
                "start"   : start.isoformat(),
                "end"     : end.isoformat(),
                "venue"   : venue,
                "address" : "",
                "popularity": 60,
            })

    print(f"• LiveNotesSB fetch — {len(events)} events")
    return events

lnsb_fetch = fetch





