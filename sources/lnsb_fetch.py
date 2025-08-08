# sources/lnsb_fetch.py
# Strict LiveNotesSB scraper: only /events-style pages, no homepage junk.
# ASCII-only.

from __future__ import annotations

import re
import html
import logging
import datetime as dt
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

LOG = logging.getLogger("lnsb")
LOG.setLevel(logging.INFO)

SITE = "https://livenotessb.com"

# ---------- helpers ----------

def _tz_offset(d: dt.datetime) -> str:
    return "-07:00" if 3 <= d.month <= 11 else "-08:00"

def _iso(d: dt.datetime) -> str:
    return d.replace(microsecond=0).isoformat() + _tz_offset(d)

def _clean(s: Optional[str]) -> str:
    if not s:
        return ""
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\s+", " ", s).strip()

def _slug(s: str) -> str:
    s = _clean(s).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "event"

def _parse_date(text: str) -> Optional[dt.date]:
    text = _clean(text)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%a, %b %d, %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except Exception:
            pass
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?", text)
    if m:
        mon, day, year = m.group(1), m.group(2), m.group(3) or str(dt.date.today().year)
        for fmt in ("%B %d, %Y", "%b %d, %Y"):
            try:
                return dt.datetime.strptime(f"{mon} {day}, {year}", fmt).date()
            except Exception:
                pass
    return None

def _parse_time(text: str) -> Optional[dt.time]:
    t = _clean(text).lower().replace(".", "")
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", t)
    if not m:
        return None
    h = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return dt.time(h, mm)
    return None

def _compose_start(day: Optional[dt.date], time_: Optional[dt.time]) -> Optional[str]:
    if not day:
        return None
    t = time_ or dt.time(19, 0)  # default 7:00 PM
    return _iso(dt.datetime.combine(day, t))

def _addr_zip(text: str) -> (str, str):
    text = _clean(text)
    # try to pull a plausible address and zip
    mzip = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
    zip_code = mzip.group(1) if mzip else ""
    # crude address capture (street + city/state optional)
    maddr = re.search(r"\b\d{2,5}\s+[A-Za-z0-9 .'-]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Way|Place|Pl|Dr|Drive)\b.*", text)
    addr = maddr.group(0) if maddr else ""
    return addr, zip_code

def _bad_title(title: str) -> bool:
    t = title.strip().lower()
    if not t or len(t) < 4:
        return True
    blacklist = {
        "skip to content", "home", "about", "contact", "menu",
        "search", "events", "calendar", "venue", "venues"
    }
    return t in blacklist

def _event_dict(day: Optional[dt.date],
                title: str,
                venue: Optional[str],
                address: Optional[str],
                zip_code: Optional[str],
                time_text: Optional[str]) -> Optional[Dict]:
    title = _clean(title)
    if not title or _bad_title(title) or not day:
        return None
    start = _compose_start(day, _parse_time(time_text or ""))
    if not start:
        return None
    vid = _slug(venue or "")
    eid = f"lnsb-{day.isoformat()}-{vid}-{_slug(title)}"
    ev = {
        "id": eid,
        "title": title,
        "category": "Music",
        "start": start,
        "city": "Santa Barbara",
    }
    if venue:
        ev["venue_name"] = _clean(venue)
    if address:
        ev["address"] = _clean(address)
    if zip_code:
        ev["zip"] = _clean(zip_code)
    return ev

# ---------- scraping ----------

MONTHS = "(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"\b{MONTHS}\s+\d{{1,2}}(?:,\s*\d{{4}})?\b", re.I)
TIME_RE = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(am|pm)\b", re.I)

def _fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SVB/1.0; +https://soundvision.buzz)"
        })
        if r.status_code == 200 and r.text:
            return r.text
    except Exception as e:
        LOG.warning("Fetch failed for %s: %s", url, e)
    return None

def _extract_from_cards(soup: BeautifulSoup) -> List[Dict]:
    out: List[Dict] = []

    # Likely event card containers
    candidates = soup.select(
        ".tribe-events-calendar-list__event, .tec-event, "
        ".mec-event-article, .mec-event-list-item, "
        "article, li.event, div.event"
    )

    def txt(el: Optional[Tag]) -> str:
        return _clean(el.get_text(" ")) if el else ""

    for card in candidates:
        text = txt(card)

        # Require both a date and a time within the card
        if not (DATE_RE.search(text) and TIME_RE.search(text)):
            continue

        # Title
        title_el = (
            card.select_one(".tribe-events-calendar-list__event-title a")
            or card.select_one(".tribe-events-calendar-list__event-title")
            or card.select_one(".mec-event-title a")
            or card.select_one(".mec-event-title")
            or card.find(["h3", "h2", "a"])
        )
        title = txt(title_el)
        if _bad_title(title):
            continue

        # Date (prefer <time datetime>)
        day = None
        time_text = ""
        dt_el = card.select_one("time[datetime]")
        if dt_el and dt_el.has_attr("datetime"):
            iso = dt_el["datetime"]
            if re.match(r"\d{4}-\d{2}-\d{2}", iso):
                try:
                    day = dt.datetime.fromisoformat(iso[:10]).date()
                except Exception:
                    day = None
            time_text = txt(dt_el)
        if not day:
            mdate = DATE_RE.search(text)
            if mdate:
                day = _parse_date(mdate.group(0))
        if not time_text:
            mtime = TIME_RE.search(text)
            if mtime:
                time_text = mtime.group(0)

        # Venue/address (best-effort)
        venue = txt(
            card.select_one(".tribe-events-venue, .venue, .location, .mec-venue-name")
        )
        address_el = (
            card.select_one(".tribe-events-address, .address, .mec-address")
            or card
        )
        address_raw = txt(address_el)
        address, zip_code = _addr_zip(address_raw)

        ev = _event_dict(day, title, venue or None, address or None, zip_code or None, time_text or "")
        if ev:
            out.append(ev)

    return out

def lnsb_fetch() -> List[Dict]:
    # Only event-like pages; do not scrape the homepage to avoid nav junk
    urls = [
        urljoin(SITE, "/events"),
        urljoin(SITE, "/calendar"),
        urljoin(SITE, "/upcoming"),
    ]

    events: List[Dict] = []
    seen = set()

    for url in urls:
        html_text = _fetch(url)
        if not html_text:
            continue
        soup = BeautifulSoup(html_text, "html.parser")

        for ev in _extract_from_cards(soup):
            # keep only future-ish
            try:
                start_dt = dt.datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
                if start_dt < dt.datetime.now() - dt.timedelta(days=1):
                    continue
            except Exception:
                pass
            if ev["id"] in seen:
                continue
            seen.add(ev["id"])
            events.append(ev)

        if len(events) >= 30:
            break

    # sort by start
    def _k(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_k)
    return events
