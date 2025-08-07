# 1 · make sure you’re in the repo root
cd ~/Documents/GitHub/svb-data          # or wherever the repo lives

# 2 · replace the file in one shot
cat > sources/livenotessb.py <<'PY'
"""
Scraper for LiveNotesSB.com  (Santa Barbara live-music listing)

* no Selenium – runs fine inside GitHub Actions
* builds entries compatible with events.json
"""

from __future__ import annotations
import datetime as dt, re, requests
from bs4 import BeautifulSoup
from typing import List, Dict

BASE = "https://livenotessb.com"
UA   = {"User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/125.0 Safari/537.36")}

DAY_HDR = re.compile(r"^[A-Z]+DAY – (\w+) (\d{1,2})$", re.I)
TIME_RE = re.compile(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", re.I)
MONTHS  = {m.lower(): i for i, m in enumerate(
           ["January","February","March","April","May","June",
            "July","August","September","October","November","December"], 1)}

def _iso(d: dt.datetime) -> str:
    return d.isoformat(timespec="seconds") + "-07:00"   # summer TZ

def _make_id(date: dt.date, venue: str, artist: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "", f"{venue}-{artist}".lower())[:32]
    return f"lnsb-{date:%Y%m%d}-{slug}"

def fetch(city_filter: str | None = None, timeout: int = 45) -> List[Dict]:
    print("• LiveNotesSB fetch")
    html = requests.get(BASE, headers=UA, timeout=timeout).text
    soup = BeautifulSoup(html, "html.parser")

    events: List[Dict] = []
    this_year = dt.date.today().year

    for h4 in soup.find_all("h4"):
        m = DAY_HDR.match(h4.get_text(" ", strip=True).replace("\xa0", " "))
        if not m:
            continue
        month_name, day_str = m.groups()
        month, day = MONTHS[month_name.lower()], int(day_str)

        # gather <p> siblings until next header
        ptr = h4.find_next_sibling()
        while ptr and ptr.name not in ("h4", "hr"):
            if ptr.name == "p" and "–" in ptr.text:
                parts = [s.strip(" –") for s in ptr.stripped_strings]
                if len(parts) < 2:
                    ptr = ptr.find_next_sibling();  continue

                venue, rest = parts[0], " ".join(parts[1:])
                tm = TIME_RE.search(rest)
                if not tm:
                    ptr = ptr.find_next_sibling();  continue

                hr, mn, ampm = int(tm.group(1)), tm.group(2), tm.group(3).lower()
                minute = int(mn) if mn else 0
                if ampm == "pm" and hr < 12:
                    hr += 12

                start_dt = dt.datetime(this_year, month, day, hr, minute)
                end_dt   = start_dt + dt.timedelta(hours=2)   # default length

                artist = rest.split("–")[0].strip()
                city   = "Santa Barbara"   # fallback

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
                    "popularity": 50
                })
            ptr = ptr.find_next_sibling()

    print(f"  ↳ {len(events)} LiveNotesSB events")
    return events
PY



