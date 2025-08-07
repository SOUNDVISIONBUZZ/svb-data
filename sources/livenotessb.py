# sources/livenotessb.py
"""
Scraper for LiveNotesSB.com   (Santa Barbara live-music listing)

* zero dependencies beyond requests + beautifulsoup4
* designed to run inside GitHub Actions (no Selenium)

Returns a list[dict] compatible with events.json.
"""

from __future__ import annotations
import datetime as dt, re, requests, hashlib
from bs4 import BeautifulSoup
from typing import List, Dict

BASE          = "https://livenotessb.com"
UA            = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/125.0 Safari/537.36"}
DAY_HDR_RE    = re.compile(r"^[A-Z]+DAY – (\w+) (\d{1,2})$", re.I)
TIME_RE       = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
MONTHS        = {m.lower(): i for i,  m in enumerate(
                 ["January","February","March","April","May","June",
                  "July","August","September","October","November","December"], 1)}

def _iso(d: dt.datetime) -> str:
    """return ISO-8601 string with TZ offset for Pacific (-07:00 summer, -08:00 winter)"""
    return d.isoformat(timespec="seconds") + ("-07:00" if d.dst() else "-08:00")

def _make_id(date: dt.date, venue: str, artist: str) -> str:
    """stable, human-readable ID"""
    slug = re.sub(r"[^a-z0-9]+", "", f"{venue}-{artist}".lower())[:32]
    return f"lnsb-{date:%Y%m%d}-{slug}"

def fetch(city_filter: str | None = None, timeout: int = 45) -> List[Dict]:
    print("• LiveNotesSB fetch")
    html = requests.get(BASE, headers=UA, timeout=timeout).text
    soup = BeautifulSoup(html, "html.parser")

    events: List[Dict] = []
    now_year = dt.date.today().year

    # Walk through each heading
    for h4 in soup.find_all("h4"):
        hdr_txt = h4.get_text(" ", strip=True).replace("\xa0", " ")
        m = DAY_HDR_RE.match(hdr_txt)
        if not m:
            continue                       # not a day header we recognise

        month_name, day_str = m.groups()
        month = MONTHS[month_name.lower()]
        day   = int(day_str)

        # Each <p> until the next <h4> (or <hr>) belongs to this date
        ptr = h4.find_next_sibling()
        while ptr and ptr.name not in ("h4", "hr"):
            if ptr.name == "p" and "–" in ptr.text:
                # crude parse “– Venue – Artist (genre) – 5-8 pm”
                parts = [seg.strip(" –") for seg in ptr.stripped_strings]
                if len(parts) < 2:
                    ptr = ptr.find_next_sibling()
                    continue

                venue, rest = parts[0], " ".join(parts[1:])
                time_m = TIME_RE.search(rest)
                if not time_m:
                    ptr = ptr.find_next_sibling()
                    continue

                hr, min_, ampm = int(time_m.group(1)), time_m.group(2), time_m.group(3).lower()
                minute = int(min_) if min_ else 0
                if ampm == "pm" and hr < 12:
                    hr += 12
                date_obj = dt.datetime(now_year, month, day, hr, minute)

                # very rough 2-hour default
                end_obj  = date_obj + dt.timedelta(hours=2)

                artist = rest.split("–")[0].strip()
                city   = "Santa Barbara" if "Santa Barbara" in venue else ""

                if city_filter and city_filter.lower() not in city.lower():
                    ptr = ptr.find_next_sibling()
                    continue

                events.append({
                    "id"      : _make_id(date_obj.date(), venue, artist),
                    "title"   : f"{venue}: {artist}",
                    "category": "Music",
                    "genre"   : "",
                    "city"    : city or "Santa Barbara",
                    "zip"     : "",
                    "start"   : _iso(date_obj),
                    "end"     : _iso(end_obj),
                    "venue"   : venue,
                    "address" : "",
                    "popularity": 50   # arbitrary
                })
            ptr = ptr.find_next_sibling()

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events


