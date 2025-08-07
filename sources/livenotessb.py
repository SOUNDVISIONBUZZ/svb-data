# sources/livenotessb.py
"""
Light-weight scraper for https://livenotessb.com/

• Finds each <h4> DAY – Month DD header.
• Grabs following <p> lines that look like   *Venue – Artist (genre) – 7-9 pm
• Builds events lasting 2 h starting at the first time mentioned.
"""

from __future__ import annotations
import datetime as dt, re, unicodedata, hashlib
from bs4 import BeautifulSoup
import requests

URL   = "https://livenotessb.com/"
HEAD  = {"User-Agent": "Mozilla/5.0"}
TZ    = dt.timezone(dt.timedelta(hours=-7))          # PDT
DLASH = r"[–—\-]"                                    # en/em/normal hyphen
SP_DASH_SP = re.compile(rf"\s+{DLASH}\s+")

MONTH_NUM = {m.lower(): i for i, m in enumerate(
    "January February March April May June July August September October November December".split(), 1)
}

def slug(txt: str, limit: int = 32) -> str:
    txt = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-z0-9]+", "-", txt.lower()).strip("-")
    return (txt[:limit].rsplit("-", 1)[0] or txt) if len(txt) > limit else txt

def next_date(month: str, day: int) -> dt.date:
    today = dt.date.today()
    for add_year in (0, 1):
        try:
            d = dt.date(today.year + add_year, MONTH_NUM[month.lower()], day)
        except ValueError:
            continue
        if d >= today - dt.timedelta(days=2):   # tolerate slight past
            return d
    raise ValueError("date out of range")

TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*([ap]m)", re.I)

# ───────────────────────── scrape ──────────────────────────────────
def fetch() -> list[dict]:
    html = requests.get(URL, headers=HEAD, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    events: list[dict] = []

    for h4 in soup.find_all("h4"):
        header = h4.get_text(" ", strip=True).replace("\u00a0", " ")
        m = re.search(rf"\b([A-Za-z]+)\s*{DLASH}\s*([A-Za-z]+)\s+(\d{{1,2}})", header)
        if not m:
            continue
        month, day = m.group(2), int(m.group(3))
        e_date = next_date(month, day)

        for p in h4.find_next_siblings():
            if p.name in ("h4", "hr"):
                break
            if p.name != "p":
                continue

            text = p.get_text(" ", strip=True).replace("\u00a0", " ")
            parts = SP_DASH_SP.split(text, maxsplit=2)
            if len(parts) < 3:
                continue            # not a “Venue – Artist – Time” line

            venue, artist_part, time_part = map(str.strip, parts[:3])

            # genre?
            g = re.search(r"\(([^)]+)\)", artist_part)
            genre = g.group(1).strip() if g else ""
            title = re.sub(r"\s*\(.*", "", artist_part).strip()

            # first time in the chunk (handles “5-8 pm”)
            t = TIME_RE.search(time_part)
            if not t:
                continue
            hour = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "pm" else 0)
            minute = int(t.group(2) or 0)
            start = dt.datetime.combine(e_date, dt.time(hour, minute), TZ)
            end   = start + dt.timedelta(hours=2)

            ev_id = f"lnsb-{start:%Y%m%d}-{slug(title or venue)}"
            events.append({
                "id": ev_id,
                "title": title or venue,
                "category": "Music",
                "genre": genre or None,
                "city": "Santa Barbara",
                "zip": "",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "venue": venue,
                "address": "",
                "popularity": 60,
            })

    print(f"• LiveNotesSB fetch\n  ↳ {len(events)} LiveNotesSB events")
    return events

# alias for fetch_and_build.py
lnsb_fetch = fetch



