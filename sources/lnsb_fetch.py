# sources/lnsb_fetch.py
"""
Scraper for the “Live Notes SB” front-page listings.
 ──> returns a list of normalised event-dicts ready for events.json
No Selenium; works in GitHub Actions.
"""

from __future__ import annotations

import datetime as dt
import re, unicodedata, hashlib
from typing import Tuple, List

import requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
MONTHS = {m.lower(): i + 1 for i, m in enumerate(
    ("January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"))}

HDR_RE = re.compile(
    r"^[A-Z][a-z]+day\s+–\s+([A-Z][a-z]+)\s+(\d{1,2})$", re.A)

TIME_RE = re.compile(
    r"""
      (?P<start>\d{1,2}(:\d{2})?)          # 5   OR 5:30
      \s*-\s*
      (?P<end>\d{1,2}(:\d{2})?)?
      \s*(?P<ampm>[ap]m)
    """, re.I | re.X)

def _slug(txt: str, maxlen: int = 24) -> str:
    out = unicodedata.normalize("NFKD", txt).encode("ascii", "ignore")
    out = re.sub(rb"[^a-z0-9]+", b"-", out.lower()).strip(b"-")
    return out.decode()[:maxlen] or hashlib.md5(out).hexdigest()[:10]

def _iso(dt_: dt.datetime, tz="-07:00") -> str:
    return dt_.strftime("%Y-%m-%dT%H:%M:%S") + tz

def _parse_time(rng: str, base_date: dt.date) -> Tuple[dt.datetime, dt.datetime]:
    """
    '5-8 pm'          -> 17:00 – 20:00
    '5:30-7 pm'       -> 17:30 – 19:00
    '8 pm-12 am'      -> 20:00 – 00:00 (next day)
    '8 pm'            -> 20:00 – 22:00 (default 2 h)
    """
    rng = rng.lower()
    m = TIME_RE.search(rng)
    if not m:
        raise ValueError(f"time not recognised: {rng!r}")

    ampm = m["ampm"]
    def _as_24(hm: str, ap: str) -> Tuple[int, int]:
        if ":" in hm:
            h, mi = map(int, hm.split(":"))
        else:
            h, mi = int(hm), 0
        if ap == "pm" and h != 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        return h, mi

    sh, sm = _as_24(m["start"], ampm)
    eh, em = _as_24(m["end"] or m["start"], ampm)  # if single-time we’ll add +2 h

    start = dt.datetime.combine(base_date, dt.time(sh, sm))
    end   = dt.datetime.combine(base_date, dt.time(eh, em))

    if m["end"] is None:          # “8 pm”
        end += dt.timedelta(hours=2)
    elif end <= start:            # crossed midnight (e.g. 9 pm-1 am)
        end += dt.timedelta(days=1)

    return start, end

def _make_id(date: dt.date, venue: str, artist: str) -> str:
    return f"lnsb-{date.strftime('%Y%m%d')}-{_slug(venue)}-{_slug(artist)}"

# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def lnsb_fetch(city_filter: str | None = None) -> List[dict]:
    """
    Scrape LiveNotesSB front page and return a list of event dicts.
    """
    print("• LiveNotesSB fetch")

    html = requests.get(SITE, headers=HEADERS, timeout=25).text
    soup = BeautifulSoup(html, "html.parser")

    page = soup.select_one("div.page-content")
    if not page:
        print("  ↳ page-content block not found!")
        return []

    today = dt.date.today()
    year  = today.year

    events: List[dict] = []
    current_date: dt.date | None = None

    ptr = page.find("h4")
    while ptr:
        if ptr.name == "h4":
            hdr = ptr.get_text(" ", strip=True).replace("\xa0", " ")
            m = HDR_RE.match(hdr)
            if m:
                month_name, day = m.groups()
                month = MONTHS[month_name.lower()]
                day   = int(day)
                # if month has already passed keep it in next year
                yy = year if month >= today.month else year + 1
                current_date = dt.date(yy, month, day)

        elif ptr.name == "p" and current_date:
            txt = ptr.get_text(" ", strip=True).replace("\xa0", " ")
            # pattern: "*Venue — Artist (genre) – 5-8 pm"
            if "–" not in txt:
                ptr = ptr.find_next_sibling();  continue
            chunks = [t.strip(" -*") for t in txt.split("–", 2)]
            if len(chunks) < 3:
                ptr = ptr.find_next_sibling();  continue

            venue, rest = chunks[0], chunks[1:]
            artist_part, time_part = rest if len(rest) == 2 else (rest[0], rest[0])
            artist = re.sub(r"\s*\([^)]*\)", "", artist_part).strip()
            city   = "Santa Barbara"  # default fallback
            # crude city guess from heading blocks like '– GOLETA/I.V –'
            upward = ptr.find_previous("p")
            if upward and "–" in upward.text and upward.text.strip().startswith("–"):
                city = upward.text.split("–")[1].split("–")[0].strip()

            try:
                start_dt, end_dt = _parse_time(time_part, current_date)
            except Exception:
                ptr = ptr.find_next_sibling();  continue

            if city_filter and city_filter.lower() not in city.lower():
                ptr = ptr.find_next_sibling();  continue

            events.append({
                "id"        : _make_id(start_dt.date(), venue, artist),
                "title"     : f"{venue}: {artist}",
                "category"  : "Music",
                "genre"     : "",
                "city"      : city,
                "zip"       : "",
                "start"     : _iso(start_dt),
                "end"       : _iso(end_dt),
                "venue"     : venue,
                "address"   : "",
                "popularity": 50,
            })
        ptr = ptr.find_next_sibling()

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events

