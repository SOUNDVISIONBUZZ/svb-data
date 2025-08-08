# sources/lnsb_fetch.py
# Clean, ASCII-only LiveNotesSB scraper with defensive parsing.
# Returns a list of event dicts expected by the pipeline.
#
# Fields produced:
# - id (str, starts with "lnsb-")
# - title (str)
# - category (str)  -> default "Music"
# - start (ISO-8601 string with -07:00 or -08:00)
# - city (str)      -> default "Santa Barbara"
# Optional:
# - venue_name (str)
# - address (str)
# - zip (str)
#
# Notes:
# - This uses multiple selector strategies to be robust across layout changes.
# - If the site cannot be parsed, it fails gracefully and returns [].
# - Tweak the SELECTOR_PATTERNS list below if LiveNotesSB changes HTML.
#
# Usage:
# from sources.lnsb_fetch import lnsb_fetch
# events = lnsb_fetch()

from __future__ import annotations

import re
import json
import time
import math
import html
import logging
import datetime as dt
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger("lnsb")
LOG.setLevel(logging.INFO)

SITE = "https://livenotessb.com"

# Choose PST/PDT offset by date. Simple rule: Mar-Nov ~ DST (-07:00), else -08:00.
def _tz_offset(date: dt.datetime) -> str:
    m = date.month
    return "-07:00" if 3 <= m <= 11 else "-08:00"

def _iso(d: dt.datetime) -> str:
    return d.replace(microsecond=0).isoformat() + _tz_offset(d)

def _slug(s: str) -> str:
    s = html.unescape(s or "")
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "event"

def _clean_text(x: Optional[str]) -> str:
    if not x:
        return ""
    x = html.unescape(x)
    x = x.replace("\xa0", " ").strip()
    return re.sub(r"\s+", " ", x)

def _parse_date(text: str) -> Optional[dt.date]:
    """
    Try multiple date formats commonly seen on event cards.
    """
    text = _clean_text(text)
    # Common patterns: "Aug 5, 2025", "August 5, 2025", "08/05/2025", "2025-08-05"
    for fmt in ["%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d", "%a, %b %d, %Y"]:
        try:
            return dt.datetime.strptime(text, fmt).date()
        except Exception:
            pass
    # Fallback: try to extract Month Day[, Year]
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?", text)
    if m:
        mon, day, year = m.group(1), m.group(2), m.group(3) or str(dt.date.today().year)
        try:
            return dt.datetime.strptime(f"{mon} {day}, {year}", "%B %d, %Y").date()
        except Exception:
            try:
                return dt.datetime.strptime(f"{mon[:3]} {day}, {year}", "%b %d, %Y").date()
            except Exception:
                pass
    return None

def _parse_time(text: str) -> Optional[dt.time]:
    """
    Accepts "7:00 PM", "19:30", "7 PM", "7pm", etc.
    """
    text = _clean_text(text).lower().replace(".", "")
    # "7pm", "7:30pm", "19:30", "19"
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", text)
    if not m:
        return None
    h = int(m.group(1))
    mm = int(m.group(2) or 0)
    ap = m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if not ap and h == 24:
        h = 0
    if 0 <= h <= 23 and 0 <= mm <= 59:
        return dt.time(hour=h, minute=mm)
    return None

def _compose_start(date: Optional[dt.date], time_: Optional[dt.time]) -> Optional[str]:
    if not date:
        return None
    t = time_ or dt.time(hour=19, minute=0)  # default 7:00 PM if time missing
    start_dt = dt.datetime.combine(date, t)
    return _iso(start_dt)

def _event_dict(day: dt.date,
                title: str,
                venue: Optional[str],
                city: Optional[str],
                address: Optional[str],
                zip_code: Optional[str],
                time_text: Optional[str]) -> Optional[Dict]:
    title = _clean_text(title)
    if not title:
        return None
    tm = _parse_time(time_text or "")
    start = _compose_start(day, tm)
    if not start:
        return None

    vid = _slug(venue or "")
    tid = _slug(title)
    eid = f"lnsb-{day.isoformat()}-{vid}-{tid}"

    ev = {
        "id": eid,
        "title": title,
        "category": "Music",
        "start": start,
        "city": _clean_text(city or "Santa Barbara"),
    }
    if venue:
        ev["venue_name"] = _clean_text(venue)
    if address:
        ev["address"] = _clean_text(address)
    if zip_code:
        ev["zip"] = _clean_text(zip_code)
    return ev

# Selector strategies: try multiple common structures
SELECTOR_PATTERNS = [
    # The Events Calendar / Tribe
    {
        "card": ("div", {"class": re.compile(r"(tribe-events|tec-event|event)")}),
        "title": [("h3", {}), ("h2", {}), ("a", {})],
        "date": [("time", {"datetime": True}), ("div", {"class": re.compile(r"date")})],
        "time": [("time", {}), ("span", {"class": re.compile(r"time")})],
        "venue": [("span", {"class": re.compile(r"(venue|location)")}), ("div", {"class": re.compile(r"(venue|location)")})],
        "address": [("span", {"class": re.compile(r"address")}), ("div", {"class": re.compile(r"address")})],
    },
    # Generic card layout
    {
        "card": ("article", {"class": re.compile(r"(event|entry|card)")}),
        "title": [("h3", {}), ("h2", {}), ("a", {})],
        "date": [("span", {"class": re.compile(r"(date|day)")}), ("div", {"class": re.compile(r"(date|day)")})],
        "time": [("span", {"class": re.compile(r"(time|hours)")}), ("div", {"class": re.compile(r"(time|hours)")})],
        "venue": [("span", {"class": re.compile(r"(venue|place)")}), ("div", {"class": re.compile(r"(venue|place)")})],
        "address": [("span", {"class": re.compile(r"(address|addr)")}), ("div", {"class": re.compile(r"(address|addr)")})],
    },
]

def _extract_text(el) -> str:
    if not el:
        return ""
    # Prefer attributes like datetime if present
    if el.has_attr("datetime"):
        return _clean_text(el.get("datetime") or "")
    return _clean_text(el.get_text(" "))

def _try_pattern(soup: BeautifulSoup, pattern: dict) -> List[Dict]:
    out: List[Dict] = []
    card_tag, card_attrs = pattern["card"]
    for card in soup.find_all(card_tag, card_attrs):
        # Title
        title = ""
        for ttag, tattrs in pattern["title"]:
            h = card.find(ttag, tattrs)
            if h:
                title = _extract_text(h)
                break

        # Date
        date_text = ""
        for dtag, dattrs in pattern["date"]:
            for h in card.find_all(dtag, dattrs):
                date_text = _extract_text(h)
                if date_text:
                    break
            if date_text:
                break
        day = None
        # If <time datetime="2025-08-07T19:00">, split date part
        if date_text and re.match(r"\d{4}-\d{2}-\d{2}", date_text):
            try:
                day = dt.datetime.fromisoformat(date_text[:10]).date()
            except Exception:
                day = _parse_date(date_text)
        else:
            day = _parse_date(date_text)

        # Time
        time_text = ""
        for stag, sattrs in pattern["time"]:
            h = card.find(stag, sattrs)
            if h:
                time_text = _extract_text(h)
                break

        # Venue, Address
        venue = ""
        for vtag, vattrs in pattern["venue"]:
            h = card.find(vtag, vattrs)
            if h:
                venue = _extract_text(h)
                break

        address = ""
        for atag, aattrs in pattern["address"]:
            h = card.find(atag, aattrs)
            if h:
                address = _extract_text(h)
                break

        # Try to pull zip from address
        zip_code = ""
        mzip = re.search(r"\b(\d{5})(?:-\d{4})?\b", address)
        if mzip:
            zip_code = mzip.group(1)

        ev = _event_dict(
            day=day if day else None,
            title=title or "Live music",
            venue=venue or None,
            city="Santa Barbara",
            address=address or None,
            zip_code=zip_code or None,
            time_text=time_text or "",
        )
        if ev:
            out.append(ev)
    return out

def _fetch_html(url: str) -> Optional[str]:
    try:
        r = requests.get(url, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SVB/1.0; +https://soundvision.buzz)"
        })
        if r.status_code == 200 and r.text:
            return r.text
    except Exception as e:
        LOG.warning("Fetch failed for %s: %s", url, e)
    return None

def lnsb_fetch() -> List[Dict]:
    """
    Scrape LiveNotesSB for upcoming events. Returns a list of normalized dicts.
    """
    urls_to_try = [
        SITE,
        urljoin(SITE, "/events"),
        urljoin(SITE, "/calendar"),
        urljoin(SITE, "/upcoming"),
    ]

    seen_ids = set()
    events: List[Dict] = []

    for url in urls_to_try:
        html_text = _fetch_html(url)
        if not html_text:
            continue
        soup = BeautifulSoup(html_text, "html.parser")

        # Try patterns in order
        for pat in SELECTOR_PATTERNS:
            items = _try_pattern(soup, pat)
            for ev in items:
                # future events only
                try:
                    start_dt = dt.datetime.fromisoformat(ev["start"].replace("Z", "+00:00"))
                except Exception:
                    # If isoformat parsing fails, keep anyway to avoid dropping legitimate items
                    start_dt = None
                if start_dt and start_dt < dt.datetime.now() - dt.timedelta(days=1):
                    continue

                if ev["id"] not in seen_ids:
                    seen_ids.add(ev["id"])
                    events.append(ev)

        # If we already collected a healthy number, we can stop early
        if len(events) >= 20:
            break

    # Sort by start ascending
    def _key(e):
        try:
            return dt.datetime.fromisoformat(e["start"].replace("Z", "+00:00"))
        except Exception:
            return dt.datetime.max
    events.sort(key=_key)

    return events


