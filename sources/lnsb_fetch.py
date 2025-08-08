# sources/lnsb_fetch.py
# LiveNotesSB scraper (homepage only). No Selenium. ASCII-only.
# Strategy:
#  - Fetch https://livenotessb.com
#  - Find blocks that contain BOTH (a date like "Aug 7, 2025") AND (a time like "7:00 PM")
#  - Grab a reasonable title from h1/h2/h3/a within that block
#  - Best-effort venue/address/zip extraction (optional)
#  - Dedup + sort + future-only

from __future__ import annotations

import re
import html
import datetime as dt
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

SITE = "https://livenotessb.com"

MONTHS = "(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:,\s*\d{{4}})?\b", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)
ZIP_RE  = re.compile(r"\b(\d{5})(?:-\d{4})?\b")
ADDR_RE = re.compile(r"\b\d{2,5}\s+[A-Za-z0-9 .'-]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Way|Place|Pl|Dr|Drive)\b.*")

BLACKLIST_TITLES = {
    "skip to content","home","about","contact","menu","search","events","calendar","venues"
}

def _clean(s: Optional[str]) -> str:
    if not s: return ""
    s = html.unescape(s).replace("\xa0"," ")
    return re.sub(r"\s+"," ",s).strip()

def _tz_offset(d: dt.datetime) -> str:
    return "-07:00" if 3 <= d.month <= 11 else "-08:00"

def _iso(dt_in: dt.datetime) -> str:
    return dt_in.replace(microsecond=0).isoformat() + _tz_offset(dt_in)

def _parse_date(s: str) -> Optional[dt.date]:
    s = _clean(s)
    for fmt in ("%b %d, %Y","%B %d, %Y","%b %d","%B %d"):
        try:
            d = dt.datetime.strptime(s, fmt)
            # if year missing, assume this year
            if d.year == 1900:
                d = d.replace(year=dt.date.today().year)
            return d.date()
        except Exception:
            pass
    # fallback: try to normalize "Aug 7, 25"
    m = re.match(rf"({MONTHS})\s+(\d{{1,2}})(?:,\s*(\d{{2,4}}))?", s, re.I)
    if m:
        mon, day, year = m.group(1), int(m.group(2)), m.group(3)
        year = int(year) if year else dt.date.today().year
        if year < 100: year += 2000
        try:
            return dt.datetime.strptime(f"{mon} {day}, {year}", "%b %d, %Y").date()
        except Exception:
            try:
                return dt.datetime.strptime(f"{mon} {day}, {year}", "%B %d, %Y").date()
            except Exception:
                return None
    return None

def _parse_time(s: str) -> Optional[dt.time]:
    s = _clean(s).lower().replace(".","")
    m = TIME_RE.search(s)
    if not m: return None
    h = int(m.group(1)); mm = int(m.group(2) or 0); ap = m.group(3)
    if ap == "pm" and h < 12: h += 12
    if ap == "am" and h == 12: h = 0
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return dt.time(h, mm)
    return None

def _make_id(day: dt.date, title: str, venue: str) -> str:
    slug = re.sub(r"[^a-z0-9]+","-", _clean(title).lower()).strip("-")
    vslug = re.sub(r"[^a-z0-9]+","-", _clean(venue).lower()).strip("-")
    return f"lnsb-{day.isoformat()}-{vslug or 'venue'}-{slug or 'event'}"

def _fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent":"Mozilla/5.0 (SVB/1.0)"})
        if r.status_code == 200 and r.text:
            return r.text
        print(f"Fetch {url} returned {r.status_code}")
    except Exception as e:
        print(f"Fetch failed for {url}: {e}")
    return None

def _title_from(block) -> str:
    # prefer explicit titles inside the block
    for sel in ["h1","h2","h3","a"]:
        el = block.find(sel)
        if el:
            t = _clean(el.get_text(" "))
            if t and t.lower() not in BLACKLIST_TITLES and len(t) > 3:
                return t
    # fallback: first 8 words of text
    words = _clean(block.get_text(" ")).split()
    return " ".join(words[:8]) if words else ""

def _venue_from(block) -> str:
    for sel in [".tribe-events-venue",".venue",".location",".mec-venue-name"]:
        el = block.select_one(sel)
        if el:
            t = _clean(el.get_text(" "))
            if t: return t
    # heuristic: look for " at <Venue>"
    txt = _clean(block.get_text(" "))
    m = re.search(r"\bat\s+([A-Z][A-Za-z0-9&' .-]{2,})", txt)
    return m.group(1).strip() if m else ""

def _addr_zip_from(block) -> tuple[str,str]:
    txt = _clean(block.get_text(" "))
    addr = ""
    maddr = ADDR_RE.search(txt)
    if maddr: addr = maddr.group(0)
    z = ""
    mz = ZIP_RE.search(txt)
    if mz: z = mz.group(1)
    return addr, z

def lnsb_fetch() -> List[Dict]:
    html = _fetch_html(SITE)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    scope = soup.select_one("main") or soup

    events: List[Dict] = []
    seen = set()

    # scan block-level containers; keep ones that clearly have date+time
    for blk in scope.find_all(["article","section","li","div"], recursive=True):
        text = _clean(blk.get_text(" "))
        if not (DATE_RE.search(text) and TIME_RE.search(text)):
            continue

        # pick the nearest reasonable title
        title = _title_from(blk)
        if not title or title.lower() in BLACKLIST_TITLES:
            continue

        # parse date/time
        dmatch = DATE_RE.search(text)
        tmatch = TIME_RE.search(text)
        if not dmatch:
            continue
        day = _parse_date(dmatch.group(0))
        tm  = _parse_time(tmatch.group(0) if tmatch else "")
        if not day:
            continue
        if not tm:
            tm = dt.time(19,0)  # default 7pm
        start_iso = _iso(dt.datetime.combine(day, tm))

        # venue/address/zip best effort
        venue = _venue_from(blk)
        addr, z = _addr_zip_from(blk)

        ev = {
            "id": _make_id(day, title, venue),
            "title": title,
            "category": "Music",
            "start": start_iso,
            "city": "Santa Barbara",
        }
        if venue: ev["venue_name"] = venue
        if addr:  ev["address"] = addr
        if z:     ev["zip"] = z

        # future-ish filter
        try:
            start_dt = dt.datetime.fromisoformat(start_iso.replace("Z","+00:00"))
            if start_dt < dt.datetime.now() - dt.timedelta(days=1):
                continue
        except Exception:
            pass

        if ev["id"] in seen:
            continue
        seen.add(ev["id"])
        events.append(ev)

    # sort by start ascending
    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z","+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_k)
    return events
